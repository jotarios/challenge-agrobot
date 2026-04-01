"""FastAPI dependencies for authentication and authorization."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from src.shared.config import settings

pwd_hasher = PasswordHash((BcryptHasher(),))
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_hasher.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_hasher.verify(plain, hashed)


def create_access_token(user_id: int, is_admin: bool = False) -> str:
    payload = {
        "sub": str(user_id),
        "is_admin": is_admin,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    payload = decode_token(credentials.credentials)
    return int(payload["sub"])


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    payload = decode_token(credentials.credentials)
    if not payload.get("is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return int(payload["sub"])
