"""Document-level metadata and structure."""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class PSDVersion(str, Enum):
    """Container format detected from the PSD file header."""
    PSD = "PSD"
    PSB = "PSB"
    Unknown = "Unknown"


class ColorMode(str, Enum):
    """Color mode of the document."""
    Bitmap = "Bitmap"
    Grayscale = "Grayscale"
    RGB = "RGB"
    CMYK = "CMYK"
    Lab = "Lab"
    Duotone = "Duotone"
    Indexed = "Indexed"
    MultiChannel = "MultiChannel"
    Palette = "Palette"
    Unknown = "Unknown"


class DocumentMetadata(BaseModel):
    """Document-level metadata."""
    
    filename: str = Field(..., description="Original filename")
    file_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    sha256: Optional[str] = Field(None, description="SHA256 hash of source file")
    psd_version: PSDVersion = Field(PSDVersion.Unknown, description="PSD/PSB version")
    parser_version: str = Field(..., description="Parser/skill version used")
    
    width_px: int = Field(..., description="Canvas width in pixels")
    height_px: int = Field(..., description="Canvas height in pixels")
    dpi_horizontal: float = Field(..., description="Horizontal DPI")
    dpi_vertical: float = Field(..., description="Vertical DPI")
    color_mode: ColorMode = Field(..., description="Color mode")
    bit_depth: int = Field(..., description="Bit depth (8, 16, 32)")
    icc_profile: Optional[str] = Field(None, description="ICC profile name/path")
    
    total_layers: int = Field(..., description="Total number of layers")
    total_groups: int = Field(..., description="Total number of groups/folders")
    max_depth: int = Field(..., description="Maximum layer nesting depth")
    visible_layers: int = Field(..., description="Visible layer count")
    hidden_layers: int = Field(..., description="Hidden layer count")
    smart_objects: int = Field(..., description="Smart object count")
    
    created_at: Optional[str] = Field(None, description="Document creation timestamp")
    modified_at: Optional[str] = Field(None, description="Last modification timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "filename": "home.psd",
                "file_size_bytes": 15728640,
                "sha256": "a1b2c3d4e5f6...",
                "parser_version": "1.0.0",
                "width_px": 1920,
                "height_px": 1080,
                "dpi_horizontal": 72.0,
                "dpi_vertical": 72.0,
                "color_mode": "RGB",
                "bit_depth": 8,
                "total_layers": 156,
                "total_groups": 23,
                "max_depth": 5,
                "visible_layers": 142,
                "hidden_layers": 14,
                "smart_objects": 12
            }
        }


class Artboard(BaseModel):
    """Artboard representation."""
    
    id: str = Field(..., description="Unique artboard ID")
    name: str = Field(..., description="Artboard name")
    index: int = Field(..., description="Artboard index order")
    
    x: int = Field(..., description="X position from document origin")
    y: int = Field(..., description="Y position from document origin")
    width_px: int = Field(..., description="Width in pixels")
    height_px: int = Field(..., description="Height in pixels")
    
    background_color: Optional[str] = Field(None, description="Background color hex")
    visible: bool = Field(True, description="Visibility state")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "artboard-1",
                "name": "Home Screen",
                "index": 0,
                "x": 0,
                "y": 0,
                "width_px": 1920,
                "height_px": 1080,
                "background_color": "#FFFFFF",
                "visible": True
            }
        }


class CoordinateSpace(BaseModel):
    """Coordinate space definition."""
    
    id: str = Field(..., description="Coordinate space ID reference")
    type: str = Field(..., description="Type: 'document' | 'artboard' | 'group'")
    source_id: Optional[str] = Field(None, description="Source artboard/group ID")
    
    origin_x: float = Field(..., description="Origin X in global coordinates")
    origin_y: float = Field(..., description="Origin Y in global coordinates")
    
    width_px: float = Field(..., description="Width in pixels")
    height_px: float = Field(..., description="Height in pixels")
    
    transform_matrix: List[float] = Field(default=[1, 0, 0, 1, 0, 0], 
                                           description="6-element affine transform [a,b,c,d,e,f]")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "coordinate-space-artboard-1",
                "type": "artboard",
                "source_id": "artboard-1",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "width_px": 1920.0,
                "height_px": 1080.0,
                "transform_matrix": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
            }
        }
