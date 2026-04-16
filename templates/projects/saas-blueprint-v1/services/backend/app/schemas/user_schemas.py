from pydantic import BaseModel
from typing import Literal, Optional


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
    # Preferências de acessibilidade
    accessibility_level: str = 'regular'          # 'regular' | 'AA' | 'AAA'
    high_contrast_mode: bool = False
    reduce_motion: bool = False
    colorblind_safe_palette: bool = False


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


class UserPreferencesRequest(BaseModel):
    theme_mode: Optional[Literal['light', 'dark']] = None
    accessibility_level: Optional[Literal['regular', 'AA', 'AAA']] = None
    high_contrast_mode: Optional[bool] = None
    reduce_motion: Optional[bool] = None
    colorblind_safe_palette: Optional[bool] = None
