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
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

# ── Configuration ──────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# ── Password hashing (bcrypt_sha256) ───────────────────────────────────────────
# bcrypt_sha256 pre-hashes with SHA-256, avoiding bcrypt's 72-byte input limit.

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

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


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


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
    admin = get_user_by_username(db, "admin")
    if not admin:
        create_user(db, "admin", "admin@tsm.local", "admin123", "admin")
        print("[OK] Created admin user")
    manager = get_user_by_username(db, "manager")
    if not manager:
        create_user(db, "manager", "manager@tsm.local", "manager123", "manager")
        print("[OK] Created manager user")
    db.commit()