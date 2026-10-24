"""Semantic component detection models."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class ComponentKind(str, Enum):
    """Semantic component type."""
    Button = "button"
    Input = "input"
    Card = "card"
    Dialog = "dialog"
    Navigation = "navigation"
    Menu = "menu"
    Icon = "icon"
    Image = "image"
    Table = "table"
    Tag = "tag"
    Header = "header"
    Footer = "footer"
    Sidebar = "sidebar"
    List = "list"
    Item = "item"
    Tab = "tab"
    Badge = "badge"
    Custom = "custom"


class ComponentState(str, Enum):
    """Component state variant."""
    Normal = "normal"
    Hover = "hover"
    Active = "active"
    Disabled = "disabled"
    Focus = "focus"
    Loading = "loading"


class ComponentAppearance(BaseModel):
    """Component visual appearance summary."""
    
    dominant_color: Optional[str] = Field(None, description="Primary color hex")
    secondary_colors: List[str] = Field(
        default_factory=list,
        description="Secondary colors"
    )
    
    has_gradient: bool = Field(False, description="Uses gradient background")
    has_shadow: bool = Field(False, description="Has shadow effect")
    has_border: bool = Field(False, description="Has border/stroke")
    border_radius_px: Optional[float] = Field(None, description="Corner radius")
    
    class Config:
        json_schema_extra = {
            "example": {
                "dominant_color": "#246BFD",
                "secondary_colors": ["#1851CD"],
                "has_gradient": False,
                "has_shadow": True,
                "has_border": True,
                "border_radius_px": 8.0
            }
        }


class ComponentStructure(BaseModel):
    """Component internal structure."""
    
    child_component_ids: List[str] = Field(
        default_factory=list,
        description="Child semantic component IDs"
    )
    total_layers: int = Field(..., description="Total layers involved")
    
    is_nested: bool = Field(False, description="Is nested component")
    nesting_level: int = Field(0, description="Nesting depth")
    
    class Config:
        json_schema_extra = {
            "example": {
                "child_component_ids": ["component-icon-1", "component-text-1"],
                "total_layers": 3,
                "is_nested": True,
                "nesting_level": 1
            }
        }


class ComponentHint(BaseModel):
    """Hint or suggestion about component."""
    
    hint_type: str = Field(..., description="'naming' | 'label' | 'interaction' | 'accessibility'")
    severity: str = Field("info", description="'info' | 'warning' | 'error'")
    message: str = Field(..., description="Suggestion message")
    
    suggestion: Optional[str] = Field(None, description="Recommended fix or improvement")
    
    class Config:
        json_schema_extra = {
            "example": {
                "hint_type": "naming",
                "severity": "warning",
                "message": "Button lacks descriptive text content",
                "suggestion": "Add visible text or ARIA label for accessibility"
            }
        }


class SemanticComponent(BaseModel):
    """Detected semantic component (independent from layer tree)."""
    
    id: str = Field(..., description="Unique component ID")
    kind: ComponentKind = Field(ComponentKind.Custom, description="Component type")
    
    # Reference to source layers (does NOT modify original layer tree)
    source_layer_ids: List[str] = Field(..., description="Original PSD layer IDs this component uses")
    
    name: str = Field("", description="Suggested component name")
    confidence: float = Field(0.0, description="Detection confidence 0.0-1.0")
    
    bounds: Dict[str, Any] = Field(
        ...,
        description="Component bounding box {x, y, width, height}"
    )
    
    appearance: Optional[ComponentAppearance] = Field(
        None,
        description="Visual appearance summary"
    )
    structure: Optional[ComponentStructure] = Field(
        None,
        description="Internal component structure"
    )
    
    state: Optional[ComponentState] = Field(None, description="Variant state")
    
    accessibility: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Accessibility properties {aria-label, role, etc.}"
    )
    
    hints: List[ComponentHint] = Field(
        default_factory=list,
        description="Improvement suggestions"
    )
    
    extraction_info: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extraction metadata and reasoning"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "id": "component-login-button",
                    "kind": "button",
                    "source_layer_ids": ["layer-1038", "layer-1039", "layer-1040"],
                    "name": "loginBtn",
                    "confidence": 0.92,
                    "bounds": {"x": 420, "y": 580, "width": 240, "height": 48},
                    "appearance": {},
                    "structure": {},
                    "state": "normal",
                    "accessibility": {"role": "button"},
                    "hints": [],
                    "extraction_info": {}
                },
                {
                    "id": "component-card-1",
                    "kind": "card",
                    "source_layer_ids": ["layer-1050", "layer-1051", "layer-1052", "layer-1053"],
                    "name": "productCard",
                    "confidence": 0.87,
                    "bounds": {"x": 100, "y": 200, "width": 280, "height": 350},
                    "appearance": {},
                    "structure": {},
                    "state": None,
                    "accessibility": {},
                    "hints": [],
                    "extraction_info": {}
                }
            ]
        }
