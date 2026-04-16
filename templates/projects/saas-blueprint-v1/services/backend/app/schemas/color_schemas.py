from pydantic import BaseModel
from typing import Dict, List


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


class UnifiedColorsResponse(BaseModel):
    success: bool = True
    color_schema_mode: str
    colors: List[ColorSchemeResponse]


class UnifiedColorUpdate(BaseModel):
    light_colors: Dict[str, str]   # color1..color5  — sanitizados no color_service
    dark_colors: Dict[str, str]    # color1..color5


class ColorModeUpdate(BaseModel):
    mode: str   # 'default' | 'custom'
