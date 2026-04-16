from pydantic import BaseModel, EmailStr
from typing import Any, Dict, List, Optional


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    username: str
    email: str
    role: str
    is_admin: bool
    theme_mode: str
    avatar_url: Optional[str] = None


class ColorSchemeResponse(BaseModel):
    color_schema_mode: str
    theme_mode: str
    accessibility_level: str
    color1: str
    color2: str
    color3: str
    color4: str
    color5: str
    on_color1: str
    on_color2: str
    on_color3: str
    on_color4: str
    on_color5: str
    on_gradient_1_2: str
    on_gradient_2_3: str
    on_gradient_3_4: str
    on_gradient_4_5: str
    on_gradient_5_1: str


class TenantColorsPayload(BaseModel):
    color_schema_mode: str
    colors: List[ColorSchemeResponse]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    tenant_colors: TenantColorsPayload
