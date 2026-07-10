from __future__ import annotations

"""Authentication via Supabase Auth.

The frontend signs in directly against Supabase and sends the resulting access
token as a bearer credential. Here we verify that token by asking Supabase Auth
who it belongs to (`auth.get_user`), with a short in-memory cache so we don't hit
Supabase on every request.
"""

import time
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.supabase_service import get_supabase_client


bearer_scheme = HTTPBearer(auto_error=False)

_TOKEN_CACHE_TTL_SECONDS = 300
_token_cache: dict[str, tuple[dict[str, str], float]] = {}


def _map_supabase_user(supabase_user: Any) -> dict[str, str]:
    metadata = getattr(supabase_user, "user_metadata", None) or {}
    email = getattr(supabase_user, "email", "") or ""
    return {
        "id": str(getattr(supabase_user, "id", "")),
        "email": email,
        "name": metadata.get("name") or metadata.get("full_name") or email or "User",
        "role": metadata.get("role") or "Merchandiser",
    }


def verify_supabase_token(token: str) -> dict[str, str]:
    now = time.time()
    cached = _token_cache.get(token)
    if cached and cached[1] > now:
        return cached[0]

    try:
        response = get_supabase_client().auth.get_user(token)
    except Exception as exc:  # noqa: BLE001 - any failure means the token is not usable
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from exc

    supabase_user = getattr(response, "user", None)
    if supabase_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    user = _map_supabase_user(supabase_user)
    _token_cache[token] = (user, now + _TOKEN_CACHE_TTL_SECONDS)
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    return verify_supabase_token(credentials.credentials)
