"""
Authentication for the Telecom Site Backend.

- Email + password sign-in (PBKDF2-SHA256, stdlib only)
- Self sign-up gated by an access phrase (SIGNUP_ACCESS_CODE) so only your
  clients/staff can create accounts; a separate ADMIN_SIGNUP_ACCESS_CODE
  creates admins
- Forgot / reset password with single-use, 30-minute links emailed via Resend
- JWTs that are revoked automatically when the password changes
- API keys (tsk_...) for machine access, unchanged
"""
import base64
import hashlib
import hmac as hmac_mod
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db

# ── Configuration ──────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))  # 7 days
RESET_TOKEN_TTL_MINUTES = 30
MIN_PASSWORD_LENGTH = 8

_PBKDF2_ITERATIONS = 480_000
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")

# The insecure accounts older versions created and reset on every boot.
LEGACY_DEFAULT_ACCOUNTS = (("admin", "admin@tsm.local"), ("manager", "manager@tsm.local"))


@lru_cache(maxsize=1)
def get_secret_key() -> str:
    """SECRET_KEY from the environment, or a key generated once and stored in
    the database. A per-process random key (the old fallback) meant each
    gunicorn worker signed tokens differently and users were logged out at
    random."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key

    from models import AppConfig

    db = SessionLocal()
    try:
        row = db.get(AppConfig, "jwt_secret")
        if row:
            return row.value
        candidate = secrets.token_urlsafe(48)
        db.add(AppConfig(key="jwt_secret", value=candidate))
        try:
            db.commit()
            print("[WARN] SECRET_KEY not set - generated one and stored it in the database.")
            return candidate
        except Exception:
            # Another worker won the race; use theirs.
            db.rollback()
            return db.get(AppConfig, "jwt_secret").value
    finally:
        db.close()


# ── Security schemes ───────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
api_key_scheme = HTTPBearer(auto_error=False)


# ── Pydantic schemas ───────────────────────────────────────────────────────────


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    email: Optional[str] = None
    role: str


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    username: str
    password: str
    accessCode: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


# ── Password hashing ───────────────────────────────────────────────────────────


def get_password_hash(password: str) -> str:
    """pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return (
        f"pbkdf2_sha256${_PBKDF2_ITERATIONS}"
        f"${base64.b64encode(salt).decode('ascii')}"
        f"${base64.b64encode(dk).decode('ascii')}"
    )


def _verify_pbkdf2(password: str, hashed: str) -> bool:
    try:
        _, iterations, salt_b64, hash_b64 = hashed.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iterations)
        )
        return hmac_mod.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


def _verify_legacy_bcrypt(password: str, hashed: str) -> bool:
    try:
        import bcrypt  # pinned ==4.0.1 (legacy verify only)
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("ascii"))
    except Exception:
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    if hashed_password.startswith("pbkdf2_sha256$"):
        return _verify_pbkdf2(plain_password, hashed_password)
    if hashed_password.startswith(_BCRYPT_PREFIXES):
        return _verify_legacy_bcrypt(plain_password, hashed_password)
    return False


# Run one hash against a dummy so "no such email" takes as long as "wrong
# password" - otherwise response timing reveals which emails have accounts.
@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return get_password_hash(secrets.token_hex(8))


# ── Validation ─────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    email = normalize_email(email)
    if len(email) > 255 or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def validate_password(password: str) -> str:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if len(password) > 256:
        raise HTTPException(status_code=422, detail="Password is too long.")
    return password


def validate_username(username: str) -> str:
    username = (username or "").strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(
            status_code=422,
            detail="Username must be 3-32 characters: letters, numbers, dots, dashes or underscores.",
        )
    return username


# ── Rate limiting (per process, sliding window) ────────────────────────────────


class RateLimiter:
    def __init__(self, max_hits: int, window_seconds: int):
        self.max_hits = max_hits
        self.window = window_seconds
        self.hits: dict = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str):
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_hits:
                raise HTTPException(
                    status_code=429, detail="Too many attempts. Wait a few minutes and try again."
                )
            q.append(now)


login_limiter = RateLimiter(max_hits=10, window_seconds=300)
signup_limiter = RateLimiter(max_hits=8, window_seconds=900)
reset_limiter = RateLimiter(max_hits=5, window_seconds=900)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Tokens ─────────────────────────────────────────────────────────────────────


def password_fingerprint(hashed_password: str) -> str:
    """Changes whenever the password changes, so embedding it in the JWT
    revokes every existing session after a reset."""
    return hashlib.sha256((hashed_password or "").encode("utf-8")).hexdigest()[:16]


def create_access_token(user, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    payload = {
        "sub": user.id,
        "role": role,
        "pv": password_fingerprint(user.hashed_password),
        "exp": expire,
    }
    return jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM)


def token_response(user) -> Token:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return Token(
        access_token=create_access_token(user),
        username=user.username,
        email=user.email,
        role=role,
    )


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── User lookups ───────────────────────────────────────────────────────────────


def get_user_by_email(db: Session, email: str):
    from models import User
    return db.query(User).filter(func.lower(User.email) == normalize_email(email)).first()


def get_user_by_username(db: Session, username: str):
    from models import User
    return db.query(User).filter(func.lower(User.username) == (username or "").strip().lower()).first()


def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ── Dependency: current user from JWT or API key ───────────────────────────────


def _api_key_user():
    from models import User, UserRole
    return User(
        id="api-system",
        username="api",
        email="api@system.local",
        hashed_password="",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _is_valid_api_key(key: str) -> bool:
    valid = [k.strip() for k in os.environ.get("VALID_API_KEYS", "").split(",") if k.strip()]
    return any(hmac_mod.compare_digest(key, v) for v in valid)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    api_key_credentials: Optional[HTTPAuthorizationCredentials] = Depends(api_key_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session has expired. Sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token and api_key_credentials:
        token = api_key_credentials.credentials
    if not token:
        raise credentials_exception

    if token.startswith("tsk_"):
        if _is_valid_api_key(token):
            return _api_key_user()
        raise credentials_exception

    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
    except JWTError:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    from models import User
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    if payload.get("pv") != password_fingerprint(user.hashed_password):
        raise credentials_exception
    return user


async def get_current_active_user(user=Depends(get_current_user)):
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled.")
    return user


def require_role(*allowed_roles):
    def role_checker(user=Depends(get_current_active_user)):
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {[r for r in allowed_roles]}",
            )
        return user
    return role_checker


# ── Sign-up access codes ───────────────────────────────────────────────────────


def role_for_access_code(code: str) -> Optional[str]:
    """Return the role an access code grants, or None if it is wrong."""
    code = (code or "").strip()
    if not code:
        return None
    admin_code = os.environ.get("ADMIN_SIGNUP_ACCESS_CODE", "").strip()
    member_code = os.environ.get("SIGNUP_ACCESS_CODE", "").strip()
    if admin_code and hmac_mod.compare_digest(code, admin_code):
        return "admin"
    if member_code and hmac_mod.compare_digest(code, member_code):
        return "manager"
    return None


def signup_enabled() -> bool:
    return bool(
        os.environ.get("SIGNUP_ACCESS_CODE", "").strip()
        or os.environ.get("ADMIN_SIGNUP_ACCESS_CODE", "").strip()
    )


# ── User creation & legacy cleanup ─────────────────────────────────────────────


def create_user(db: Session, username: str, email: str, password: str, role: str):
    from models import User, UserRole
    user = User(
        username=username,
        email=normalize_email(email),
        hashed_password=get_password_hash(password),
        role=UserRole(role),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def disable_legacy_default_users(db: Session):
    """Older versions created admin/admin123 and manager/manager123 and reset
    those passwords on every boot. Switch those accounts off. Never raises."""
    from models import User
    try:
        changed = 0
        for username, email in LEGACY_DEFAULT_ACCOUNTS:
            user = (
                db.query(User)
                .filter(User.username == username, func.lower(User.email) == email)
                .first()
            )
            if user and user.is_active:
                user.is_active = False
                changed += 1
        if changed:
            db.commit()
            print(f"[OK] Disabled {changed} legacy default account(s) (admin/manager).")
    except Exception as e:
        db.rollback()
        print(f"[WARN] Could not disable legacy default accounts: {type(e).__name__}: {e}")
