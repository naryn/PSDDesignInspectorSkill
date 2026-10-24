"""Layer representation and styling information."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

from .typography import Typography


class LayerKind(str, Enum):
    """Type of layer."""
    Pixel = "pixel"
    Shape = "shape"
    Text = "text"
    Group = "group"
    SmartObject = "smart_object"
    Adjustment = "adjustment"
    Fill = "fill"
    Stroke = "stroke"


class BlendMode(str, Enum):
    """Blend mode for layers."""
    PassThrough = "pass through"
    Normal = "normal"
    Multiply = "multiply"
    Screen = "screen"
    Overlay = "overlay"
    Darken = "darken"
    Lighten = "lighten"
    ColorDodge = "color dodge"
    ColorBurn = "color burn"
    SoftLight = "soft light"
    HardLight = "hard light"
    Difference = "difference"
    Exclusion = "exclusion"
    Hue = "hue"
    Saturation = "saturation"
    Color = "color"
    Luminosity = "luminosity"


class ShadowPosition(str, Enum):
    """Stroke position relative to edge."""
    Inside = "inside"
    Center = "center"
    Outside = "outside"


class FillType(str, Enum):
    """Fill type."""
    Solid = "solid"
    Gradient = "gradient"
    Pattern = "pattern"


class GradientType(str, Enum):
    """Gradient type."""
    Linear = "linear"
    Radial = "radial"
    Angular = "angular"
    Diamond = "diamond"
    Symmetric = "symmetric"


class ColorStop(BaseModel):
    """Color stop in gradient."""
    
    offset: float = Field(..., description="Stop position 0.0-1.0")
    color: str = Field(..., description="Color in hex format with alpha #AARRGGBB")
    opacity: float = Field(1.0, description="Opacity at this stop (0.0-1.0)")
    
    class Config:
        json_schema_extra = {
            "example": {"offset": 0.5, "color": "#FF246BFD", "opacity": 1.0}
        }


class Fill(BaseModel):
    """Fill definition."""
    
    kind: FillType = Field(FillType.Solid, description="Type of fill")
    visible: bool = Field(True, description="Whether fill is enabled")
    opacity: float = Field(1.0, description="Overall opacity (0.0-1.0)")
    
    solid_color: Optional[str] = Field(None, description="Solid color hex #AARRGGBB")
    gradient_type: Optional[GradientType] = Field(None, description="Gradient type if gradient fill")
    gradient_stops: Optional[List[ColorStop]] = Field(None, description="Color stops for gradients")
    pattern_name: Optional[str] = Field(None, description="Pattern name if pattern fill")
    pattern_enabled: bool = Field(True, description="Whether pattern is enabled")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "kind": "solid",
                    "visible": True,
                    "opacity": 1.0,
                    "solid_color": "#246BFD",
                    "gradient_type": None,
                    "gradient_stops": None,
                    "pattern_name": None,
                    "pattern_enabled": True
                },
                {
                    "kind": "gradient",
                    "visible": True,
                    "opacity": 0.8,
                    "solid_color": None,
                    "gradient_type": "linear",
                    "gradient_stops": [{"offset": 0, "color": "#FF0000FF", "opacity": 1.0}, 
                                      {"offset": 1, "color": "#FF00FFFF", "opacity": 1.0}],
                    "pattern_name": None,
                    "pattern_enabled": True
                }
            ]
        }


class Stroke(BaseModel):
    """Stroke definition."""
    
    width_px: float = Field(..., description="Stroke width in pixels")
    color: str = Field(..., description="Stroke color hex #AARRGGBB")
    opacity: float = Field(1.0, description="Stroke opacity (0.0-1.0)")
    position: ShadowPosition = Field(ShadowPosition.Outside, description="Stroke position")
    visible: bool = Field(True, description="Whether stroke is enabled")
    
    class Config:
        json_schema_extra = {
            "example": {
                "width_px": 1.0,
                "color": "#1851CD",
                "opacity": 1.0,
                "position": "outside",
                "visible": True
            }
        }


class Shadow(BaseModel):
    """Drop shadow or inner shadow definition."""
    
    shadow_type: str = Field(..., description="'drop' | 'inner'")
    color: str = Field(..., description="Shadow color hex #AARRGGBB")
    opacity: float = Field(..., description="Shadow opacity (0.0-1.0)")
    angle_deg: float = Field(..., description="Angle in degrees (-180 to 180)")
    distance_px: float = Field(..., description="Distance from source")
    spread_px: float = Field(0.0, description="Spread amount")
    size_px: float = Field(..., description="Blur radius")
    enabled: bool = Field(True, description="Whether shadow is enabled")
    use_global_light: bool = Field(False, description="Use global light setting")
    
    class Config:
        json_schema_extra = {
            "example": {
                "shadow_type": "drop",
                "color": "#000000",
                "opacity": 0.15,
                "angle_deg": -90.0,
                "distance_px": 4.0,
                "spread_px": 0.0,
                "size_px": 12.0,
                "enabled": True,
                "use_global_light": False
            }
        }


class Glow(BaseModel):
    """Outer or inner glow definition."""
    
    glow_type: str = Field(..., description="'outer' | 'inner'")
    color: str = Field(..., description="Glow color hex #AARRGGBB")
    opacity: float = Field(..., description="Glow opacity (0.0-1.0)")
    size_px: float = Field(..., description="Blur radius")
    noise: int = Field(0, description="Noise percentage")
    enabled: bool = Field(True, description="Whether glow is enabled")
    
    class Config:
        json_schema_extra = {
            "example": {
                "glow_type": "outer",
                "color": "#FFFFFF",
                "opacity": 0.3,
                "size_px": 20.0,
                "noise": 0,
                "enabled": True
            }
        }


class Geometry(BaseModel):
    """Layer geometry and coordinate information."""
    
    source_bounds: Dict[str, int] = Field(
        ..., 
        description="Native bounds: {'x': x, 'y': y, 'width': w, 'height': h}"
    )
    visible_bounds: Dict[str, int] = Field(
        ...,
        description="Visible pixel bounds excluding transparent areas"
    )
    effect_bounds: Optional[Dict[str, int]] = Field(
        None,
        description="Bounds including effects like shadows"
    )
    
    relative_to_parent: Dict[str, int] = Field(
        ...,
        description="Position relative to parent group {x, y}"
    )
    normalized: Dict[str, float] = Field(
        ...,
        description="Normalized coordinates relative to document {x, y, width, height}"
    )
    
    rotation_deg: float = Field(0.0, description="Rotation in degrees")
    scale_x: float = Field(1.0, description="Horizontal scale factor")
    scale_y: float = Field(1.0, description="Vertical scale factor")
    
    transform_matrix: List[float] = Field(
        default=[1, 0, 0, 1, 0, 0],
        description="6-element affine transform matrix [a,b,c,d,e,f]"
    )
    
    has_transform: bool = Field(False, description="Has non-identity transform")
    non_invertible_transform: bool = Field(False, description="Transform cannot be inverted")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_bounds": {"x": 420, "y": 580, "width": 240, "height": 48},
                "visible_bounds": {"x": 420, "y": 580, "width": 240, "height": 48},
                "effect_bounds": None,
                "relative_to_parent": {"x": 20, "y": 180},
                "normalized": {"x": 0.35, "y": 0.725, "width": 0.2, "height": 0.06},
                "rotation_deg": 0.0,
                "scale_x": 1.0,
                "scale_y": 1.0,
                "transform_matrix": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                "has_transform": False,
                "non_invertible_transform": False
            }
        }


class BorderRadii(BaseModel):
    """Border radius per corner."""
    
    top_left: float = Field(0.0, description="Top-left corner radius px")
    top_right: float = Field(0.0, description="Top-right corner radius px")
    bottom_right: float = Field(0.0, description="Bottom-right corner radius px")
    bottom_left: float = Field(0.0, description="Bottom-left corner radius px")
    uniform: bool = Field(True, description="All corners have same radius")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {"top_left": 8, "top_right": 8, "bottom_right": 8, "bottom_left": 8, "uniform": True},
                {"top_left": 4, "top_right": 8, "bottom_right": 12, "bottom_left": 6, "uniform": False}
            ]
        }


class ColorOverlay(BaseModel):
    """Color overlay effect."""
    color: str = Field(..., description="Overlay color #AARRGGBB")
    opacity: float = Field(1.0, description="Overlay opacity")
    blend_mode: BlendMode = Field(BlendMode.Normal, description="Blend mode")
    enabled: bool = Field(True, description="Enabled state")
    
    class Config:
        json_schema_extra = {
            "example": {
                "color": "#FF246BFD",
                "opacity": 0.5,
                "blend_mode": "multiply",
                "enabled": True
            }
        }


class GradientOverlay(BaseModel):
    """Gradient overlay effect."""
    gradient_type: GradientType = Field(..., description="Gradient type")
    opacity: float = Field(1.0, description="Overlay opacity")
    blend_mode: BlendMode = Field(BlendMode.Normal, description="Blend mode")
    angle_deg: float = Field(0.0, description="Angle for linear/angular gradients")
    scale: float = Field(100.0, description="Scale percentage")
    gradient_stops: List[ColorStop] = Field(..., description="Color stops")
    enabled: bool = Field(True, description="Enabled state")
    
    class Config:
        json_schema_extra = {
            "example": {
                "gradient_type": "linear",
                "opacity": 0.8,
                "blend_mode": "normal",
                "angle_deg": 90.0,
                "scale": 100.0,
                "gradient_stops": [],
                "enabled": True
            }
        }


class PatternOverlay(BaseModel):
    """Pattern overlay effect."""
    blend_mode: BlendMode = Field(BlendMode.Normal, description="Blend mode")
    opacity: float = Field(1.0, description="Overlay opacity")
    scale: float = Field(100.0, description="Scale percentage")
    linked_to_layer: bool = Field(True, description="Scale with layer")
    enabled: bool = Field(True, description="Enabled state")
    
    class Config:
        json_schema_extra = {
            "example": {
                "blend_mode": "normal",
                "opacity": 1.0,
                "scale": 100.0,
                "linked_to_layer": True,
                "enabled": True
            }
        }


class Appearance(BaseModel):
    """Layer visual appearance."""
    
    opacity: float = Field(1.0, description="Layer opacity (0.0-1.0)")
    fill_opacity: float = Field(1.0, description="Fill opacity (0.0-1.0)")
    blend_mode: BlendMode = Field(BlendMode.Normal, description="Blend mode")
    
    fills: List[Fill] = Field(default_factory=list, description="Fill definitions")
    strokes: List[Stroke] = Field(default_factory=list, description="Stroke definitions")
    
    border_radius: BorderRadii = Field(default_factory=BorderRadii)
    
    drop_shadow: Optional[Shadow] = Field(None, description="Drop shadow")
    inner_shadow: Optional[Shadow] = Field(None, description="Inner shadow")
    outer_glow: Optional[Glow] = Field(None, description="Outer glow")
    inner_glow: Optional[Glow] = Field(None, description="Inner glow")
    color_overlay: Optional[ColorOverlay] = Field(None, description="Color overlay")
    gradient_overlay: Optional[GradientOverlay] = Field(None, description="Gradient overlay")
    pattern_overlay: Optional[PatternOverlay] = Field(None, description="Pattern overlay")
    
    class Config:
        json_schema_extra = {
            "example": {
                "opacity": 1.0,
                "fill_opacity": 1.0,
                "blend_mode": "normal",
                "fills": [{"kind": "solid", "solid_color": "#246BFD", "visible": True, "opacity": 1.0}],
                "strokes": [{"width_px": 1, "color": "#1851CD", "opacity": 1.0, "position": "inside", "visible": True}],
                "border_radius": {"top_left": 8, "top_right": 8, "bottom_right": 8, "bottom_left": 8, "uniform": True},
                "drop_shadow": {"shadow_type": "drop", "color": "#000000", "opacity": 0.15, "angle_deg": -90.0, "distance_px": 4.0, "spread_px": 0.0, "size_px": 12.0, "enabled": True, "use_global_light": False},
                "inner_shadow": None,
                "outer_glow": None,
                "inner_glow": None,
                "color_overlay": None,
                "gradient_overlay": None,
                "pattern_overlay": None
            }
        }


class ExtractionSource(str, Enum):
    """Data source for extracted property."""
    PSD_NATIVE = "psd_native"
    PHOTOSHOP_API = "photoshop_api"
    PIXEL_MEASURED = "pixel_measured"
    GEOMETRY_COMPUTED = "geometry_computed"
    VISION_INFERRED = "vision_inferred"
    MANUAL_OVERRIDE = "manual_override"


class ExtractionStatus(str, Enum):
    """Extraction status."""
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ExtractionInfo(BaseModel):
    """Information about extraction provenance and quality."""
    
    status: ExtractionStatus = Field(ExtractionStatus.UNKNOWN, description="Extraction status")
    source: ExtractionSource = Field(ExtractionSource.PSD_NATIVE, description="Data source")
    confidence: float = Field(1.0, description="Confidence score 0.0-1.0")
    
    errors: List[str] = Field(default_factory=list, description="Error messages")
    warnings: List[str] = Field(default_factory=list, description="Warning messages")
    unsupported_properties: List[str] = Field(default_factory=list, description="Unsupported features")
    
    property_sources: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-property source info: {property_path: {source, confidence}}"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "complete",
                "source": "psd_native",
                "confidence": 1.0,
                "errors": [],
                "warnings": [],
                "unsupported_properties": [],
                "property_sources": {
                    "geometry.source_bounds": {"source": "psd_native", "confidence": 1.0},
                    "appearance.borderRadius": {"source": "psd_native", "confidence": 1.0}
                }
            }
        }


class Layer(BaseModel):
    """Complete layer representation."""
    
    id: str = Field(..., description="Internal unique ID (e.g., 'layer-1038')")
    source_layer_id: Optional[int] = Field(None, description="Original PSD layer ID")
    name: str = Field(..., description="Layer name")
    kind: LayerKind = Field(LayerKind.Pixel, description="Layer type")
    
    parent_id: Optional[str] = Field(None, description="Parent group ID or null")
    z_index: int = Field(..., description="Z-order within parent")
    depth: int = Field(0, description="Nesting depth")
    
    visible: bool = Field(True, description="Visibility state")
    locked: bool = Field(False, description="Lock state")
    
    coordinate_space_id: str = Field(..., description="Reference to coordinate space")
    
    geometry: Geometry = Field(..., description="Geometry and transforms")
    appearance: Appearance = Field(..., description="Visual appearance")
    typography: Optional[Typography] = Field(
        None, description="Native text content and styling for text layers"
    )
    
    masks: List[str] = Field(default_factory=list, description="Mask references")
    vector_masks: List[str] = Field(default_factory=list, description="Vector mask references")
    clipping_groups: List[str] = Field(default_factory=list, description="Clipping mask members")
    
    smart_object_link: Optional[str] = Field(None, description="Smart object external link path")
    smart_object_data: Optional[Dict[str, Any]] = Field(None, description="Smart object embedded data")
    
    export_paths: List[str] = Field(default_factory=list, description="Exported asset paths")
    
    extraction: ExtractionInfo = Field(default_factory=ExtractionInfo, description="Extraction metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "layer-1038",
                "source_layer_id": 1038,
                "name": "登录按钮背景",
                "kind": "shape",
                "parent_id": "group-100",
                "z_index": 12,
                "depth": 2,
                "visible": True,
                "locked": False,
                "coordinate_space_id": "document",
                "geometry": {},
                "appearance": {},
                "masks": [],
                "vector_masks": [],
                "clipping_groups": [],
                "smart_object_link": None,
                "smart_object_data": None,
                "export_paths": [],
                "extraction": {}
            }
        }
