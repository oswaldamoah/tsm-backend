"""
Authentication module for the Telecom Site Backend.
Password hashing (bcrypt), JWT tokens, API key support, and user seeding.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

# ── Configuration ──────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# ── Password hashing ───────────────────────────────────────────────────────────
# PURE-STDLIB PBKDF2-HMAC-SHA256. No passlib, no bcrypt required for hashing —
# immune to the passlib/bcrypt>=4.1 incompatibility that crashes worker boot
# ("password cannot be longer than 72 bytes"). Legacy bcrypt hashes ($2b$...)
# are still verified via the pinned bcrypt library inside a try/except, so
# existing users keep working.
import base64
import hashlib
import hmac as hmac_mod

_PBKDF2_ITERATIONS = 480_000  # OWASP-recommended minimum for PBKDF2-SHA256
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_RECOGNIZED_PREFIXES = _BCRYPT_PREFIXES + ("pbkdf2_sha256$",)

# ── Security schemes ───────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
api_key_scheme = HTTPBearer(auto_error=False)
# ── Pydantic schemas ───────────────────────────────────────────────────────────


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Utility functions ──────────────────────────────────────────────────────────


def get_password_hash(password: str) -> str:
    """Hash with PBKDF2-HMAC-SHA256 (stdlib only). Format:
    pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>"""
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
            "sha256",
            password.encode("utf-8"),
            base64.b64decode(salt_b64),
            int(iterations),
        )
        return hmac_mod.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


def _verify_legacy_bcrypt(password: str, hashed: str) -> bool:
    # bcrypt silently truncated at 72 bytes historically; replicate that so
    # long inputs can't raise ValueError on modern bcrypt versions.
    try:
        import bcrypt  # pinned ==4.0.1 in requirements.txt (legacy verify only)
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


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_username(db: Session, username: str):
    from models import User
    return db.query(User).filter(User.username == username).first()


def authenticate_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user
# ── Dependency: get current user from JWT or API key ───────────────────────────


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    api_key_credentials: Optional[HTTPAuthorizationCredentials] = Depends(api_key_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Check if token is an API key (starts with tsk_)
    if token and token.startswith("tsk_"):
        valid_api_keys = os.environ.get("VALID_API_KEYS", "").split(",")
        if token in valid_api_keys:
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
        raise credentials_exception

    # Try JWT token
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception
        user = get_user_by_username(db, username)
        if user is None or not user.is_active:
            raise credentials_exception
        return user

    # Try API key from Authorization header (Bearer scheme)
    if api_key_credentials and api_key_credentials.credentials:
        api_key = api_key_credentials.credentials
        if api_key.startswith("tsk_"):
            valid_api_keys = os.environ.get("VALID_API_KEYS", "").split(",")
            if api_key in valid_api_keys:
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

    raise credentials_exception


async def get_current_active_user(user=Depends(get_current_user)):
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return user


def require_role(*allowed_roles):
    def role_checker(user=Depends(get_current_active_user)):
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {[r for r in allowed_roles]}"
            )
        return user
    return role_checker


# ── Seed default users ─────────────────────────────────────────────────────────


def create_user(db: Session, username: str, email: str, password: str, role: str):
    from models import User, UserRole
    hashed = get_password_hash(password)
    user = User(
        username=username,
        email=email,
        hashed_password=hashed,
        role=UserRole(role),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_default_users(db: Session):
    """Seed admin & manager users — NEVER crashes startup. Handles:
    - username already exists (normal case)
    - email already exists on a DIFFERENT username (create_user.py legacy data)
    - unrecognized hash formats (reset to default)
    - any other DB error (log & continue)"""
    from models import User

    def _upsert_user(username: str, email: str, default_password: str, role: str):
        """Find by username OR email. If found, ensure correct password/hash.
        If neither exists, create fresh. Any error is caught & logged."""
        try:
            # First check by username
            user = db.query(User).filter(User.username == username).first()
            # If not found, check if email is taken by another account
            if not user:
                user = db.query(User).filter(User.email == email).first()
                if user and user.username != username:
                    # Legacy collision: same email, different username.
                    # Adopt this account as the canonical one.
                    print(
                        f"[INFO] Adopting existing user '{user.username}' "
                        f"(email={email}) as '{username}'"
                    )
                    user.username = username

            if user:
                # Ensure role & active status
                from models import UserRole
                user.role = UserRole(role)
                user.is_active = True
                # ALWAYS reset hash for canonical default users to ensure
                # correct default passwords (admin123, manager123).
                # This overwrites any legacy password from create_user.py.
                print(f"[INFO] Resetting password for default user '{username}'")
                user.hashed_password = get_password_hash(default_password)
                db.commit()
                return

            # Brand new user
            create_user(db, username, email, default_password, role)
            print(f"[OK] Created {username} user")
        except Exception as e:
            # Never let seeding kill the server
            db.rollback()
            print(f"[ERROR] Seeding {username}: {type(e).__name__}: {e}")

    # Per-user isolation — one failure never blocks the other
    _upsert_user("admin", "admin@tsm.local", "admin123", "admin")
    _upsert_user("manager", "manager@tsm.local", "manager123", "manager")