from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import get_settings


bearer_scheme = HTTPBearer(auto_error=False)


def authenticate_user(email: str, password: str) -> dict[str, str] | None:
    settings = get_settings()

    if email != settings.demo_user_email or password != settings.demo_user_password:
        return None

    return {
        "email": settings.demo_user_email,
        "name": settings.demo_user_name,
        "role": settings.demo_user_role,
    }


def create_access_token(user: dict[str, str]) -> str:
    settings = get_settings()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user["email"],
        "name": user["name"],
        "role": user["role"],
        "exp": expires_at,
        "iat": datetime.utcnow(),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    payload = decode_access_token(credentials.credentials)
    return {
        "email": str(payload["sub"]),
        "name": str(payload.get("name", "")),
        "role": str(payload.get("role", "")),
    }
