"""Spatial relationships and layout analysis models."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class AlignmentAxis(str, Enum):
    """Axis for alignment."""
    Vertical = "vertical"
    Horizontal = "horizontal"


class AlignmentType(str, Enum):
    """Type of alignment."""
    Top = "top"
    Bottom = "bottom"
    Left = "left"
    Right = "right"
    CenterHorizontal = "center_horizontal"
    CenterVertical = "center_vertical"
    Baseline = "baseline"


class LayoutType(str, Enum):
    """Detected layout type."""
    Flex = "flex"
    Grid = "grid"
    Absolute = "absolute"
    Unknown = "unknown"


class SpacingDirection(str, Enum):
    """Direction of spacing relationship."""
    Horizontal = "horizontal"
    Vertical = "vertical"


class AlignmentGroup(BaseModel):
    """Aligned elements group."""
    
    id: str = Field(..., description="Unique group ID")
    axis: AlignmentAxis = Field(..., description="Alignment axis")
    alignment_type: AlignmentType = Field(..., description="Type of alignment")
    
    layer_ids: List[str] = Field(..., description="Member layer IDs")
    tolerance_px: float = Field(2.0, description="Tolerance in pixels")
    
    reference_position: float = Field(..., description="Reference position value")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "align-top-1",
                "axis": "vertical",
                "alignment_type": "top",
                "layer_ids": ["layer-1001", "layer-1002", "layer-1003"],
                "tolerance_px": 2.0,
                "reference_position": 180.0
            }
        }


class SpacingGroup(BaseModel):
    """Evenly spaced elements group."""
    
    id: str = Field(..., description="Unique group ID")
    direction: SpacingDirection = Field(..., description="Spacing direction")
    
    layer_ids: List[str] = Field(..., description="Sequential layer IDs")
    
    gap_px: float = Field(..., description="Gap size in pixels")
    gap_variance_px: float = Field(0.0, description="Variance in gaps (lower is better)")
    
    padding_start_px: Optional[float] = Field(None, description="Padding before first element")
    padding_end_px: Optional[float] = Field(None, description="Padding after last element")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "spacing-horizontal-6",
                "direction": "horizontal",
                "layer_ids": ["layer-1010", "layer-1011", "layer-1012"],
                "gap_px": 24.0,
                "gap_variance_px": 0.5,
                "padding_start_px": 16.0,
                "padding_end_px": 16.0
            }
        }


class SpatialRelationship(BaseModel):
    """Measured spatial relationship between layers."""
    
    source_layer_id: str = Field(..., description="Source layer ID")
    target_layer_id: str = Field(..., description="Target layer ID")
    
    distance_px: float = Field(..., description="Distance between edges")
    vector_x: float = Field(..., description="X component of vector")
    vector_y: float = Field(..., description="Y component of vector")
    
    overlap_ratio: float = Field(0.0, description="Overlap ratio 0.0-1.0")
    projection_overlap: bool = Field(False, description="Orthogonal projection overlaps")
    
    relative_position: str = Field(
        ..., 
        description="'left' | 'right' | 'above' | 'below' | 'diagonal'"
    )
    
    is_neighbor: bool = Field(False, description="Are they immediate neighbors")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_layer_id": "layer-1038",
                "target_layer_id": "layer-1039",
                "distance_px": 12.0,
                "vector_x": 12.0,
                "vector_y": 0.0,
                "overlap_ratio": 0.15,
                "projection_overlap": True,
                "relative_position": "right",
                "is_neighbor": True
            }
        }


class LayoutEvidence(BaseModel):
    """Evidence supporting a layout hypothesis."""
    
    evidence_type: str = Field(..., description="'alignment' | 'spacing' | 'size_consistency' | 'repetition'")
    strength: float = Field(..., description="Strength 0.0-1.0")
    
    contributing_groups: List[str] = Field(..., description="ID of alignment/spacing groups")
    contributing_layers: List[str] = Field(default_factory=list, description="Layer IDs")
    
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metrics like cluster counts, variance, etc."
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "evidence_type": "spacing",
                "strength": 0.85,
                "contributing_groups": ["spacing-horizontal-6", "spacing-vertical-8"],
                "contributing_layers": ["layer-1010", "layer-1011", "layer-1012"],
                "metrics": {"group_count": 3, "avg_gap_var": 0.5}
            }
        }


class LayoutHypothesis(BaseModel):
    """Hypothetical layout model with evidence."""
    
    id: str = Field(..., description="Unique hypothesis ID")
    layout_type: LayoutType = Field(LayoutType.Unknown, description="Inferred layout type")
    
    confidence: float = Field(0.0, description="Confidence score 0.0-1.0")
    
    layers_involved: List[str] = Field(..., description="Layer IDs this hypothesis covers")
    coverage_ratio: float = Field(0.0, description="Ratio of covered layers")
    
    evidence: List[LayoutEvidence] = Field(
        default_factory=list,
        description="Supporting evidence"
    )
    
    conflicts: List[str] = Field(
        default_factory=list,
        description="Conflicting evidence or exceptions"
    )
    
    css_recommendation: Optional[Dict[str, Any]] = Field(
        None,
        description="CSS/Flexbox/Grid recommendation"
    )
    
    # Flex-specific
    flex_direction: Optional[str] = Field(None, description="'row' | 'column'")
    flex_wrap: Optional[str] = Field(None, description="'nowrap' | 'wrap' | 'wrap-reverse'")
    justify_content: Optional[str] = Field(None, description="Justify content value")
    align_items: Optional[str] = Field(None, description="Align items value")
    
    # Grid-specific
    grid_columns: Optional[int] = Field(None, description="Number of columns")
    grid_rows: Optional[int] = Field(None, description="Number of rows")
    gap_x_px: Optional[float] = Field(None, description="Column gap")
    gap_y_px: Optional[float] = Field(None, description="Row gap")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "layout-flex-nav-1",
                "layout_type": "flex",
                "confidence": 0.87,
                "layers_involved": ["layer-1020", "layer-1021", "layer-1022"],
                "coverage_ratio": 0.9,
                "evidence": [],
                "conflicts": [],
                "css_recommendation": {
                    "display": "flex",
                    "flex-direction": "row",
                    "justify-content": "space-between",
                    "align-items": "center"
                },
                "flex_direction": "row",
                "flex_wrap": "nowrap",
                "justify_content": "space-between",
                "align_items": "center",
                "grid_columns": None,
                "grid_rows": None,
                "gap_x_px": None,
                "gap_y_px": None
            }
        }


class RelativePosition(BaseModel):
    """Relative position to parent container."""
    
    x: int = Field(..., description="X offset from parent left")
    y: int = Field(..., description="Y offset from parent top")
    width_px: int = Field(..., description="Width")
    height_px: int = Field(..., description="Height")
    
    padding_from_parent: Optional[Dict[str, int]] = Field(
        None,
        description="Padding from parent sides {top, right, bottom, left}"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "x": 20,
                "y": 180,
                "width_px": 240,
                "height_px": 48,
                "padding_from_parent": {"top": 160, "right": 360, "bottom": 280, "left": 20}
            }
        }


class NearNeighbor(BaseModel):
    """Nearby neighbor with distance information."""
    
    layer_id: str = Field(..., description="Neighbor layer ID")
    distance_px: float = Field(..., description="Distance in pixels")
    direction: SpacingDirection = Field(..., description="Primary direction")
    
    angle_deg: float = Field(..., description="Angle from source")
    
    class Config:
        json_schema_extra = {
            "example": {
                "layer_id": "layer-1039",
                "distance_px": 12.0,
                "direction": "horizontal",
                "angle_deg": 0.0
            }
        }


class SpatialGraph(BaseModel):
    """Complete spatial analysis result."""
    
    coordinate_space_id: str = Field(..., description="Coordinate space reference")
    
    alignment_groups: List[AlignmentGroup] = Field(
        default_factory=list,
        description="Detected alignment groups"
    )
    spacing_groups: List[SpacingGroup] = Field(
        default_factory=list,
        description="Detected spacing groups"
    )
    
    pairwise_relationships: List[SpatialRelationship] = Field(
        default_factory=list,
        description="All pairwise relationships"
    )
    
    layout_hypotheses: List[LayoutHypothesis] = Field(
        default_factory=list,
        description="Inferred layout models"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "coordinate_space_id": "document",
                "alignment_groups": [],
                "spacing_groups": [],
                "pairwise_relationships": [],
                "layout_hypotheses": []
            }
        }
