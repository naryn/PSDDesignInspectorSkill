"""Design tokens extraction models."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class TokenType(str, Enum):
    """Token category type."""
    Color = "color"
    Typography = "typography"
    Spacing = "spacing"
    Border = "border"
    Shadow = "shadow"
    Size = "size"
    Composition = "composition"
    Animation = "animation"
    Custom = "custom"


class TokenCategory(str, Enum):
    """Usage category for token."""
    Global = "global"
    Brand = "brand"
    Interactive = "interactive"
    Text = "text"
    Background = "background"
    Surface = "surface"
    Error = "error"
    Success = "success"
    Warning = "warning"
    Info = "info"
    Custom = "custom"


class TokenValue(BaseModel):
    """Token value with variants."""
    
    base: str = Field(..., description="Base value")
    hex: Optional[str] = Field(None, description="Hex representation")
    
    variants: Dict[str, str] = Field(
        default_factory=dict,
        description="Variant values {light, dark, hover, etc.}"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {"base": "#246BFD", "hex": "#246BFD", "variants": {"hover": "#1851CD"}},
                {"base": "16", "hex": None, "variants": {"small": "8", "large": "24"}}
            ]
        }


class DesignToken(BaseModel):
    """Single design token definition."""
    
    id: str = Field(..., description="Unique token ID")
    name: str = Field(..., description="Suggested token name (e.g., 'primaryColor', 'text-lg')")
    
    type: TokenType = Field(TokenType.Custom, description="Token category type")
    category: TokenCategory = Field(TokenCategory.Custom, description="Usage category")
    
    value: TokenValue = Field(..., description="Token value(s)")
    
    description: Optional[str] = Field(None, description="Token usage description")
    
    usage_count: int = Field(0, description="How many times this appears in design")
    source_layer_ids: List[str] = Field(
        default_factory=list,
        description="Source layer IDs for reference"
    )
    
    is_recommended: bool = Field(False, description="Recommended as official token")
    
    notes: List[str] = Field(
        default_factory=list,
        description="Additional notes or concerns"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "id": "token-color-primary-1",
                    "name": "primaryColor",
                    "type": "color",
                    "category": "brand",
                    "value": {},
                    "description": "Primary brand color used for buttons and links",
                    "usage_count": 15,
                    "source_layer_ids": ["layer-1038", "layer-1045"],
                    "is_recommended": True,
                    "notes": []
                },
                {
                    "id": "token-spacing-md-1",
                    "name": "spaceMd",
                    "type": "spacing",
                    "category": "global",
                    "value": {"base": "16", "hex": None, "variants": {"sm": "8", "lg": "24"}},
                    "description": "Medium spacing unit for components",
                    "usage_count": 42,
                    "source_layer_ids": [],
                    "is_recommended": True,
                    "notes": []
                }
            ]
        }


class TypographyTokenSet(BaseModel):
    """Typography token set."""
    
    font_family: str = Field(..., description="Primary font family")
    font_sizes: Dict[str, int] = Field(
        default_factory=dict,
        description="Named sizes in px {xs, sm, md, lg, xl}"
    )
    font_weights: Dict[str, int] = Field(
        default_factory=dict,
        description="Named weights {normal, bold}"
    )
    line_heights: Dict[str, float] = Field(
        default_factory=dict,
        description="Named line heights {tight, relaxed}"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "font_family": "PingFang SC, SF Pro",
                "font_sizes": {"xs": 12, "sm": 14, "md": 16, "lg": 18, "xl": 24},
                "font_weights": {"normal": 400, "bold": 700},
                "line_heights": {"tight": 1.2, "normal": 1.5, "relaxed": 1.75}
            }
        }


class SpacingTokenSet(BaseModel):
    """Spacing token set."""
    
    units: List[int] = Field(default_factory=lambda: [4, 8, 16, 24, 32], 
                             description="Standard spacing units")
    scale: Dict[str, int] = Field(
        default_factory=dict,
        description="Named spacing {xxs, xs, sm, md, lg, xl}"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "units": [4, 8, 16, 24, 32],
                "scale": {"xxs": 4, "xs": 8, "sm": 16, "md": 24, "lg": 32, "xl": 48}
            }
        }


class DesignSystemTokens(BaseModel):
    """Complete design system tokens output."""
    
    colors: List[DesignToken] = Field(
        default_factory=list,
        description="Color tokens"
    )
    typography: List[DesignToken] = Field(
        default_factory=list,
        description="Typography tokens"
    )
    spacing: List[DesignToken] = Field(
        default_factory=list,
        description="Spacing tokens"
    )
    borders: List[DesignToken] = Field(
        default_factory=list,
        description="Border tokens"
    )
    shadows: List[DesignToken] = Field(
        default_factory=list,
        description="Shadow tokens"
    )
    sizes: List[DesignToken] = Field(
        default_factory=list,
        description="Size tokens"
    )
    
    typography_sets: List[TypographyTokenSet] = Field(
        default_factory=list,
        description="Typography sets"
    )
    spacing_sets: List[SpacingTokenSet] = Field(
        default_factory=list,
        description="Spacing sets"
    )
    
    recommended_count: int = Field(0, description="Number of recommended tokens")
    total_count: int = Field(0, description="Total token count")
    
    class Config:
        json_schema_extra = {
            "example": {
                "colors": [],
                "typography": [],
                "spacing": [],
                "borders": [],
                "shadows": [],
                "sizes": [],
                "typography_sets": [],
                "spacing_sets": [],
                "recommended_count": 12,
                "total_count": 25
            }
        }
