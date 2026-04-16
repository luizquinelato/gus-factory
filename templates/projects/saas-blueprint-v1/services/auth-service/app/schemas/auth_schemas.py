from pydantic import BaseModel, EmailStr
from typing import Literal, Optional


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenValidateRequest(BaseModel):
    token: str


class UserPayload(BaseModel):
    id: int
    tenant_id: int
    name: str
    username: str
    email: str
    role: str
    is_admin: bool
    theme_mode: str
    avatar_url: Optional[str] = None
    # Preferências de acessibilidade
    accessibility_level: str = 'regular'
    high_contrast_mode: bool = False
    reduce_motion: bool = False
    colorblind_safe_palette: bool = False


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str                  # opaque token — armazenar em localStorage
    token_type: str = "bearer"
    expires_in: int                     # segundos até expirar o access token (ex: 300)
    user: UserPayload


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str                  # token rotacionado
    token_type: str = "bearer"
    expires_in: int


class TokenValidateResponse(BaseModel):
    valid: bool
    payload: dict | None = None
    detail: str | None = None
