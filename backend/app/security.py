"""Password hashing (stdlib scrypt), JWT sessions and role guards."""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, digest_b64 = stored.split("$")
        salt, digest = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
    except ValueError:
        return False
    return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1), digest)


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_ttl_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, settings.jwt_secret, "HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    payload = decode_token(creds.credentials) if creds else None
    user = db.get(User, int(payload["sub"])) if payload else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    return user


def require_operator(user: User = Depends(current_user)) -> User:
    # The role is re-read from the database on each request, never trusted from the token alone.
    if user.role != "operator":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator access only")
    return user


def require_passenger(user: User = Depends(current_user)) -> User:
    if user.role != "passenger":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Passenger access only")
    return user
