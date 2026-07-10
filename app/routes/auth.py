from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.auth_service import get_current_user


router = APIRouter()


class AuthUser(BaseModel):
    email: str
    name: str
    role: str


@router.get("/status")
def auth_status() -> dict[str, str]:
    return {
        "service": "auth",
        "status": "ready",
        "detail": "Supabase Auth protects the ERP APIs. Sign in from the app to obtain a session.",
    }


@router.get("/me", response_model=AuthUser)
def me(current_user: dict[str, str] = Depends(get_current_user)) -> AuthUser:
    return AuthUser(
        email=current_user["email"],
        name=current_user["name"],
        role=current_user["role"],
    )
