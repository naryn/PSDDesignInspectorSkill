"""Typography and text formatting models."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class TextOrientation(str, Enum):
    """Text orientation."""
    Horizontal = "horizontal"
    Vertical = "vertical"
    VerticalRotated = "vertical_rotated"


class TextAlign(str, Enum):
    """Paragraph alignment."""
    Left = "left"
    Right = "right"
    Center = "center"
    Justified = "justified"
    JustifiedLastLine = "justified_last_line"
    Unknown = "unknown"


class FontWeight(str, Enum):
    """Font weight category."""
    Thin = "thin"
    ExtraLight = "extra_light"
    Light = "light"
    Normal = "normal"
    Medium = "medium"
    SemiBold = "semi_bold"
    Bold = "bold"
    ExtraBold = "extra_bold"
    Black = "black"
    Variable = "variable"
    Unknown = "unknown"


class FontFeature(BaseModel):
    """OpenType font feature."""
    tag: str = Field(..., description="4-char feature tag like 'liga', 'kern'")
    enabled: bool = Field(..., description="Whether feature is enabled")
    
    class Config:
        json_schema_extra = {
            "example": {"tag": "liga", "enabled": True}
        }


class Font(BaseModel):
    """Font information."""
    
    family: str = Field(..., description="Font family name (e.g., 'PingFang SC')")
    post_script_name: Optional[str] = Field(None, description="Adobe PostScript name")
    style: Optional[str] = Field(None, description="Font style (e.g., 'Medium', 'Bold Italic')")
    
    weight: FontWeight = Field(FontWeight.Unknown, description="Weight category")
    width: Optional[str] = Field(None, description="Width category (condensed, expanded)")
    
    is_bold: bool = Field(False, description="Is bold face")
    is_italic: bool = Field(False, description="Is italic face")
    is_underline: bool = Field(False, description="Has underline")
    is_strikethrough: bool = Field(False, description="Has strikethrough")
    
    missing: bool = Field(False, description="Font file not found on system")
    fallback_used: Optional[str] = Field(None, description="Fallback font used")
    
    features: List[FontFeature] = Field(
        default_factory=list,
        description="OpenType features"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "family": "PingFang SC",
                    "post_script_name": None,
                    "style": "Medium",
                    "weight": "medium",
                    "width": None,
                    "is_bold": False,
                    "is_italic": False,
                    "is_underline": False,
                    "is_strikethrough": False,
                    "missing": False,
                    "fallback_used": None,
                    "features": []
                },
                {
                    "family": "Unknown Font",
                    "post_script_name": None,
                    "style": None,
                    "weight": "unknown",
                    "width": None,
                    "is_bold": True,
                    "is_italic": False,
                    "is_underline": False,
                    "is_strikethrough": False,
                    "missing": True,
                    "fallback_used": "SF Pro CN",
                    "features": []
                }
            ]
        }


class SourceFontSize(BaseModel):
    """Original font size with unit."""
    
    value: float = Field(..., description="Font size value")
    unit: str = Field("pt", description="Original unit: pt, px, mm, cm, in")
    converted_px: float = Field(..., description="Converted to pixels")
    conversion_basis: Optional[str] = Field(
        None, 
        description="Basis of conversion (e.g., '72 DPI')"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "value": 24.0,
                "unit": "pt",
                "converted_px": 32.0,
                "conversion_basis": "72 DPI"
            }
        }


class CharacterRun(BaseModel):
    """Character run with distinct typography attributes."""
    
    start: int = Field(..., description="Start character index (Unicode code point)")
    end: int = Field(..., description="End character index (exclusive)")
    
    content: str = Field(..., description="Text content of this run")
    
    font: Font = Field(..., description="Font information")
    source_font_size: SourceFontSize = Field(..., description="Original PSD font size")
    effective_font_size_px: float = Field(..., description="Effective size in CSS pixels")
    
    color: str = Field(..., description="Color hex #AARRGGBB")
    opacity: float = Field(1.0, description="Opacity (0.0-1.0)")
    
    tracking: float = Field(0.0, description="Tracking in thousandths of em (-1000 to 1000)")
    kerning: Optional[float] = Field(None, description="Kerning override")
    letter_spacing_px: Optional[float] = Field(None, description="Letter spacing in pixels")
    
    paragraph_index: int = Field(0, description="Parent paragraph index")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "start": 0,
                    "end": 2,
                    "content": "欢迎",
                    "font": {},
                    "source_font_size": {},
                    "effective_font_size_px": 32.0,
                    "color": "#FFFFFF",
                    "opacity": 1.0,
                    "tracking": 0.0,
                    "kerning": None,
                    "letter_spacing_px": None,
                    "paragraph_index": 0
                }
            ]
        }


class ParagraphRun(BaseModel):
    """Paragraph-level formatting."""
    
    start: int = Field(..., description="Start character index")
    end: int = Field(..., description="End character index (exclusive)")
    
    alignment: TextAlign = Field(TextAlign.Left, description="Text alignment")
    
    line_height_px: Optional[float] = Field(None, description="Line height in pixels")
    line_height_percent: Optional[float] = Field(None, description="Line height percentage")
    
    space_before_px: Optional[float] = Field(None, description="Space before paragraph")
    space_after_px: Optional[float] = Field(None, description="Space after paragraph")
    
    first_line_indent_px: Optional[float] = Field(None, description="First line indent")
    left_indent_px: Optional[float] = Field(None, description="Left indent")
    right_indent_px: Optional[float] = Field(None, description="Right indent")
    
    direction: str = Field("ltr", description="'ltr' | 'rtl'")
    justified_last_line: bool = Field(False, description="Justified last line")
    
    class Config:
        json_schema_extra = {
            "example": {
                "start": 0,
                "end": 6,
                "alignment": "left",
                "line_height_px": 48.0,
                "line_height_percent": 150.0,
                "space_before_px": 0.0,
                "space_after_px": 0.0,
                "first_line_indent_px": 0.0,
                "left_indent_px": 0.0,
                "right_indent_px": 0.0,
                "direction": "ltr",
                "justified_last_line": False
            }
        }


class TextBox(BaseModel):
    """Text bounding box information."""
    
    x: float = Field(..., description="X position from document origin")
    y: float = Field(..., description="Y position from document origin")
    width_px: float = Field(..., description="Text box width")
    height_px: float = Field(..., description="Text box height")
    
    auto_wrap: bool = Field(True, description="Auto-wrap enabled")
    text_direction: TextOrientation = Field(TextOrientation.Horizontal, description="Text direction")
    
    transform_matrix: List[float] = Field(
        default=[1, 0, 0, 1, 0, 0],
        description="Affine transform matrix"
    )
    
    content_width_px: Optional[float] = Field(None, description="Actual content width (if smaller than box)")
    content_height_px: Optional[float] = Field(None, description="Actual content height")
    
    class Config:
        json_schema_extra = {
            "example": {
                "x": 120.0,
                "y": 80.0,
                "width_px": 320.0,
                "height_px": 60.0,
                "auto_wrap": True,
                "text_direction": "horizontal",
                "transform_matrix": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                "content_width_px": 315.0,
                "content_height_px": 48.0
            }
        }


class Typography(BaseModel):
    """Complete typography information for a text layer."""
    
    content: str = Field(..., description="Full text content")
    orientation: TextOrientation = Field(TextOrientation.Horizontal, description="Orientation")
    
    text_box: TextBox = Field(..., description="Text box geometry")
    
    character_runs: List[CharacterRun] = Field(
        default_factory=list,
        description="Per-character-style runs"
    )
    paragraph_runs: List[ParagraphRun] = Field(
        default_factory=list,
        description="Per-paragraph styles"
    )
    
    total_characters: int = Field(..., description="Total character count")
    total_lines: int = Field(..., description="Estimated line count")
    
    dominant_font_family: Optional[str] = Field(None, description="Most common font")
    dominant_font_size_px: Optional[float] = Field(None, description="Most common size")
    
    effects: List[str] = Field(
        default_factory=list,
        description="Reference to layer effects on text"
    )
    
    extraction_source: str = Field("psd_native", description="Extraction source")
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "欢迎使用系统",
                "orientation": "horizontal",
                "text_box": {},
                "character_runs": [],
                "paragraph_runs": [],
                "total_characters": 6,
                "total_lines": 1,
                "dominant_font_family": "PingFang SC",
                "dominant_font_size_px": 32.0,
                "effects": ["drop_shadow"],
                "extraction_source": "psd_native"
            }
        }
