"""PSD Design Inspector - Main package."""

from .pipeline import DesignIRPipeline, ExtractorProfile
from .adapters.psd_tools_adapter import PsdToolsAdapter
from .models.document import (
    DocumentMetadata, 
    Artboard, 
    CoordinateSpace,
    PSDVersion,
    ColorMode
)
from .models.layer import (
    Layer,
    Geometry,
    Appearance,
    ExtractionInfo,
    Fill,
    Stroke,
    Shadow,
    Glow,
    BorderRadii
)
from .models.typography import (
    Typography,
    CharacterRun,
    ParagraphRun,
    Font,
    TextOrientation
)
from .models.geometry import (
    SpatialRelationship,
    LayoutHypothesis,
    AlignmentGroup,
    SpacingGroup
)
from .models.component import SemanticComponent, ComponentKind
from .models.token import DesignToken, TokenType
from .adapters.base import ParseError, UnsupportedFeatureError

__version__ = "0.1.0"

__all__ = [
    # Pipeline and adapters
    "DesignIRPipeline",
    "ExtractorProfile",
    "PsdToolsAdapter",
    "ParseError",
    "UnsupportedFeatureError",
    
    # Models - Document
    "DocumentMetadata",
    "Artboard",
    "CoordinateSpace",
    "PSDVersion",
    "ColorMode",
    
    # Models - Layer
    "Layer",
    "Geometry",
    "Appearance",
    "ExtractionInfo",
    "Fill",
    "Stroke",
    "Shadow",
    "Glow",
    "BorderRadii",
    
    # Models - Typography
    "Typography",
    "CharacterRun",
    "ParagraphRun",
    "Font",
    "TextOrientation",
    
    # Models - Geometry
    "SpatialRelationship",
    "LayoutHypothesis",
    "AlignmentGroup",
    "SpacingGroup",
    
    # Models - Component
    "SemanticComponent",
    "ComponentKind",
    
    # Models - Token
    "DesignToken",
    "TokenType",
]
