"""Native appearance extraction from psd-tools layer records.

Covers vector shape fill/stroke colors, live-shape corner radii, and layer
effects. Anything not representable in the Design IR is reported in
``unsupported_effects`` instead of being flattened into a guessed value.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from psd_tools.constants import Tag
except ImportError:  # pragma: no cover - psd-tools is a hard dependency
    Tag = None


_BLEND_MODES = (
    "pass through",
    "normal",
    "multiply",
    "screen",
    "overlay",
    "darken",
    "lighten",
    "color dodge",
    "color burn",
    "soft light",
    "hard light",
    "difference",
    "exclusion",
    "hue",
    "saturation",
    "color",
    "luminosity",
)

_GRADIENT_TYPES = {
    b"Lnr ": "linear",
    b"Rdl ": "radial",
    b"Angl": "angular",
    b"Dmnd": "diamond",
    b"Rflc": "symmetric",
}

_STROKE_POSITIONS = {
    b"OutF": "outside",
    b"InsF": "inside",
    b"CtrF": "center",
}

_VECTOR_STROKE_POSITIONS = {
    "inner": "inside",
    "inside": "inside",
    "outer": "outside",
    "outside": "outside",
    "center": "center",
}


def _value(obj: Any, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, "value", obj)


def _number(obj: Any, default: float = 0.0) -> float:
    try:
        return float(_value(obj, default))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", "ignore").strip()
    return str(value or "").strip()


def _blend_mode(value: Any) -> str:
    name = _text(value).lower().replace("_", " ")
    return name if name in _BLEND_MODES else "normal"


def _color(descriptor: Any) -> Optional[str]:
    """Read an RGB color from a psd-tools descriptor."""
    if not hasattr(descriptor, "get"):
        return None
    if b"Rd  " not in descriptor:
        nested = descriptor.get(b"Clr ")
        if hasattr(nested, "get"):
            descriptor = nested
        else:
            return None

    def channel(key: bytes) -> int:
        return max(0, min(255, int(_number(descriptor.get(key)) + 0.5)))

    return f"#{channel(b'Rd  '):02X}{channel(b'Grn '):02X}{channel(b'Bl  '):02X}"


def _opacity(value: Any) -> float:
    return round(max(0.0, min(1.0, _number(value, 100.0) / 100.0)), 4)


def _gradient_stops(gradient: Any) -> List[Dict[str, Any]]:
    if not hasattr(gradient, "get"):
        return []
    colors = gradient.get(b"Clrs") or []
    transparencies = gradient.get(b"Trns") or []

    def location(item: Any) -> Optional[int]:
        if not hasattr(item, "get"):
            return None
        return int(_number(item.get(b"Lctn")))

    def opacity_at(position: int) -> float:
        best = None
        for item in transparencies:
            item_position = location(item)
            if item_position is None:
                continue
            distance = abs(item_position - position)
            if best is None or distance < best[0]:
                best = (distance, item)
        if best is None:
            return 1.0
        return _opacity(best[1].get(b"Opct"))

    stops: List[Dict[str, Any]] = []
    for stop in colors:
        if not hasattr(stop, "get"):
            continue
        position = location(stop)
        color = _color(stop.get(b"Clr "))
        if position is None or color is None:
            continue
        stops.append(
            {
                "offset": round(position / 4096.0, 4),
                "color": color,
                "opacity": opacity_at(position),
            }
        )
    return stops


def _vector_fill_color(layer: Any) -> Tuple[Optional[str], bool]:
    """Read the shape fill from ``vscg`` (VECTOR_STROKE_CONTENT_DATA).

    Photoshop keeps the shape fill color in this record; the vector stroke
    settings (``vstk``) hold the stroke color. Returns ``(color, found_record)``.
    """
    tagged = getattr(layer, "tagged_blocks", None)
    if tagged is None or Tag is None:
        return None, False
    try:
        record = tagged.get_data(Tag.VECTOR_STROKE_CONTENT_DATA)
    except Exception:
        return None, False
    if record is None:
        return None, False
    return _color(record), True


def _shape_appearance(
    layer: Any,
    result: Dict[str, Any],
    warnings: List[str],
    unsupported: List[str],
) -> None:
    try:
        stroke = layer.stroke
    except Exception:
        stroke = None

    fill_color, fill_record_found = _vector_fill_color(layer)
    fill_enabled = bool(getattr(stroke, "fill_enabled", False)) if stroke else False
    stroke_enabled = bool(getattr(stroke, "enabled", False)) if stroke else False

    if fill_enabled:
        if fill_color is None and not fill_record_found and stroke is not None:
            # Older PSD files may omit vscg; the vector stroke content is the
            # only remaining native color record.
            fill_color = _color(stroke.content)
            if fill_color is not None:
                warnings.append(
                    "Shape fill color was read from vector stroke content "
                    "because the fill record is absent."
                )
        if fill_color is None:
            if fill_record_found:
                unsupported.append("vector_gradient_fill")
                warnings.append(
                    "Vector shape fill is enabled but not a solid color; gradient "
                    "and pattern vector fills are not represented."
                )
            else:
                warnings.append(
                    "Vector shape fill is enabled but has no readable color."
                )
        else:
            result["fills"].append(
                {
                    "kind": "solid",
                    "visible": True,
                    "opacity": 1.0,
                    "solid_color": fill_color,
                    "gradient_type": None,
                    "gradient_stops": None,
                    "pattern_name": None,
                    "pattern_enabled": True,
                }
            )

    if stroke_enabled and stroke is not None:
        stroke_color = _color(stroke.content)
        position = _VECTOR_STROKE_POSITIONS.get(
            _text(getattr(stroke, "line_alignment", "center")), "center"
        )
        if stroke_color is None:
            warnings.append("Vector shape stroke is enabled but has no readable color.")
        result["strokes"].append(
            {
                "width_px": _number(getattr(stroke, "line_width", 0.0)),
                "color": stroke_color or "#000000",
                "opacity": _opacity(getattr(stroke, "opacity", 100.0)),
                "position": position,
                "visible": True,
            }
        )

    _rounded_radii(layer, result)


def _rounded_radii(layer: Any, result: Dict[str, Any]) -> None:
    origination = getattr(layer, "origination", None) or []
    for item in origination:
        radii = getattr(item, "radii", None)
        if not hasattr(radii, "get"):
            continue
        corners = {
            "top_left": round(_number(radii.get(b"topLeft")), 2),
            "top_right": round(_number(radii.get(b"topRight")), 2),
            "bottom_right": round(_number(radii.get(b"bottomRight")), 2),
            "bottom_left": round(_number(radii.get(b"bottomLeft")), 2),
        }
        result["border_radius"] = {
            **corners,
            "uniform": len(set(corners.values())) == 1,
        }
        return


def _shadow(effect: Any) -> Dict[str, Any]:
    size = _number(getattr(effect, "size", 0.0))
    choke = _number(getattr(effect, "choke", 0.0))
    return {
        "shadow_type": "drop"
        if type(effect).__name__ == "DropShadow"
        else "inner",
        "color": _color(getattr(effect, "color", None)) or "#000000",
        "opacity": _opacity(getattr(effect, "opacity", 100.0)),
        "angle_deg": _number(getattr(effect, "angle", 0.0)),
        "distance_px": _number(getattr(effect, "distance", 0.0)),
        "spread_px": round(size * choke / 100.0, 2),
        "size_px": size,
        "enabled": bool(getattr(effect, "enabled", True)),
        "use_global_light": bool(getattr(effect, "use_global_light", False)),
    }


def _glow(effect: Any) -> Dict[str, Any]:
    return {
        "glow_type": "outer" if type(effect).__name__ == "OuterGlow" else "inner",
        "color": _color(getattr(effect, "color", None)) or "#000000",
        "opacity": _opacity(getattr(effect, "opacity", 100.0)),
        "size_px": _number(getattr(effect, "size", 0.0)),
        "noise": _number(getattr(effect, "noise", 0.0)),
        "enabled": bool(getattr(effect, "enabled", True)),
    }


def _effect_appearance(
    effect: Any,
    result: Dict[str, Any],
    warnings: List[str],
    unsupported: List[str],
) -> None:
    name = type(effect).__name__

    if name in ("DropShadow", "InnerShadow"):
        key = "drop_shadow" if name == "DropShadow" else "inner_shadow"
        result[key] = _shadow(effect)
        if _number(getattr(effect, "choke", 0.0)) > 0:
            warnings.append(
                f"{name} choke is a percentage; spread_px is approximated as "
                "size x choke / 100."
            )
        return

    if name in ("OuterGlow", "InnerGlow"):
        key = "outer_glow" if name == "OuterGlow" else "inner_glow"
        result[key] = _glow(effect)
        return

    if name == "ColorOverlay":
        color = _color(getattr(effect, "color", None))
        if color is None:
            warnings.append("ColorOverlay has no readable color and was skipped.")
            return
        result["color_overlay"] = {
            "color": color,
            "opacity": _opacity(getattr(effect, "opacity", 100.0)),
            "blend_mode": _blend_mode(getattr(effect, "blend_mode", b"normal")),
            "enabled": bool(getattr(effect, "enabled", True)),
        }
        return

    if name == "GradientOverlay":
        gradient = getattr(effect, "gradient", None)
        stops = _gradient_stops(gradient)
        if not stops:
            warnings.append("GradientOverlay has no readable gradient stops and was skipped.")
            return
        gradient_type = _GRADIENT_TYPES.get(
            getattr(effect, "type", b"Lnr "), "linear"
        )
        result["gradient_overlay"] = {
            "gradient_type": gradient_type,
            "opacity": _opacity(getattr(effect, "opacity", 100.0)),
            "blend_mode": _blend_mode(getattr(effect, "blend_mode", b"normal")),
            "angle_deg": _number(getattr(effect, "angle", 0.0)),
            "scale": _number(getattr(effect, "scale", 100.0), 100.0),
            "gradient_stops": stops,
            "enabled": bool(getattr(effect, "enabled", True)),
        }
        return

    if name == "PatternOverlay":
        result["pattern_overlay"] = {
            "blend_mode": _blend_mode(getattr(effect, "blend_mode", b"normal")),
            "opacity": _opacity(getattr(effect, "opacity", 100.0)),
            "scale": _number(getattr(effect, "scale", 100.0), 100.0),
            "linked_to_layer": bool(getattr(effect, "linked", True)),
            "enabled": bool(getattr(effect, "enabled", True)),
        }
        warnings.append(
            "PatternOverlay is represented without the pattern name; psd-tools "
            "does not expose the referenced pattern asset for this effect."
        )
        return

    if name == "Stroke":
        fill_type = _text(getattr(effect, "fill_type", b"SClr"))
        if fill_type != "SClr":
            unsupported.append("Stroke(gradient/pattern)")
            warnings.append(
                "Layer-style stroke uses a gradient or pattern fill; only solid "
                "strokes are represented."
            )
            return
        color = _color(getattr(effect, "color", None))
        if color is None:
            warnings.append("Layer-style stroke has no readable color and was skipped.")
            return
        position = _STROKE_POSITIONS.get(
            getattr(effect, "position", b"OutF"), "outside"
        )
        result["strokes"].append(
            {
                "width_px": _number(getattr(effect, "size", 0.0)),
                "color": color,
                "opacity": _opacity(getattr(effect, "opacity", 100.0)),
                "position": position,
                "visible": bool(getattr(effect, "enabled", True)),
            }
        )
        return

    unsupported.append(name)
    warnings.append(
        f"Layer effect {name} is not representable in the current Design IR."
    )


def extract_appearance(
    layer: Any,
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Extract fills, strokes, radii and effects from a psd-tools layer.

    Returns ``(appearance, warnings, unsupported_effects)``.
    """
    warnings: List[str] = []
    unsupported: List[str] = []
    result: Dict[str, Any] = {
        "fills": [],
        "strokes": [],
        "border_radius": {},
        "drop_shadow": None,
        "inner_shadow": None,
        "outer_glow": None,
        "inner_glow": None,
        "color_overlay": None,
        "gradient_overlay": None,
        "pattern_overlay": None,
    }

    if getattr(layer, "kind", None) == "shape":
        try:
            _shape_appearance(layer, result, warnings, unsupported)
        except Exception as error:
            warnings.append(f"Vector shape appearance extraction failed: {error}")

    try:
        effects: Sequence[Any] = (
            list(layer.effects) if layer.has_effects() else []
        )
    except Exception as error:
        effects = []
        warnings.append(f"Layer effects could not be read: {error}")

    for effect in effects:
        try:
            _effect_appearance(effect, result, warnings, unsupported)
        except Exception as error:
            warnings.append(
                f"{type(effect).__name__} extraction failed: {error}"
            )

    return result, warnings, unsupported
