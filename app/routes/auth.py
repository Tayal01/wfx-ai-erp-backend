from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.services.auth_service import authenticate_user, create_access_token, get_current_user


router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthUser(BaseModel):
    email: str
    name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


@router.get("/status")
def auth_status() -> dict[str, str]:
    return {
        "service": "auth",
        "status": "ready",
        "detail": "Demo JWT login is available for protected ERP APIs.",
    }


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return LoginResponse(access_token=create_access_token(user), user=AuthUser(**user))


@router.get("/me", response_model=AuthUser)
def me(current_user: dict[str, str] = Depends(get_current_user)) -> AuthUser:
    return AuthUser(**current_user)
