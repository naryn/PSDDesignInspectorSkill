"""Native typography extraction from Photoshop text engine data.

Only values present in the PSD are emitted. Derived values (pixel sizes from
point sizes, CSS letter spacing from tracking) keep their native source and
conversion basis so downstream consumers can audit them.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple


# Photoshop text engine Justification codes.
_JUSTIFICATION = {
    0: "left",
    1: "right",
    2: "center",
    3: "justified",
    4: "justified",
    5: "justified",
    6: "justified_last_line",
}

_DIRECTION = {0: "horizontal", 1: "vertical", 2: "vertical_rotated"}

_WEIGHT_KEYWORDS = (
    ("extralight", "extra_light"),
    ("ultralight", "extra_light"),
    ("semibold", "semi_bold"),
    ("demibold", "semi_bold"),
    ("extrabold", "extra_bold"),
    ("ultrabold", "extra_bold"),
    ("thin", "thin"),
    ("light", "light"),
    ("medium", "medium"),
    ("heavy", "black"),
    ("black", "black"),
    ("bold", "bold"),
    ("regular", "normal"),
    ("normal", "normal"),
    ("book", "normal"),
)


def _value(obj: Any, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, "value", obj)


def _number(obj: Any, default: float = 0.0) -> float:
    try:
        return float(_value(obj, default))
    except (TypeError, ValueError):
        return default


def _clean_font_name(name: Any) -> Optional[str]:
    name = getattr(name, "value", name)
    if not isinstance(name, str):
        return None
    text = name.strip().strip("'\"").replace("\x00", "")
    return text or None


def _split_font_name(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not name:
        return None, None
    if "-" in name:
        family, style = name.rsplit("-", 1)
        return family or name, style or None
    return name, None


def _map_weight(name: Optional[str], style: Optional[str], faux_bold: bool) -> str:
    haystack = f"{name or ''} {style or ''}".lower()
    for keyword, weight in _WEIGHT_KEYWORDS:
        if keyword in haystack:
            if faux_bold and weight in ("normal", "light", "medium"):
                return "bold"
            return weight
    return "bold" if faux_bold else "unknown"


def _merged_style(
    run: Any,
    style_sheets: Sequence[Any],
    default_data: Optional[Any],
) -> Tuple[Dict[str, Any], Optional[int]]:
    """Resolve a style run into a flat style dict.

    Photoshop stores either an inline style sheet or an index into
    ``StyleSheetSet``. Missing keys fall back to ``DefaultRunData``.
    """
    merged: Dict[str, Any] = {}
    if default_data is not None:
        for key, value in default_data.items():
            merged[key] = value

    sheet_data: Optional[Any] = None
    sheet_index: Optional[int] = None
    if hasattr(run, "get") and "StyleSheet" in run:
        sheet = run.get("StyleSheet") or {}
        sheet_data = sheet.get("StyleSheetData")
    else:
        index = int(_number(run, -1))
        if 0 <= index < len(style_sheets):
            sheet_index = index
            sheet = style_sheets[index]
            if hasattr(sheet, "get"):
                sheet_data = sheet.get("StyleSheetData")

    if sheet_data:
        for key, value in sheet_data.items():
            merged[key] = value
    return merged, sheet_index


def _merged_paragraph(
    run: Any,
    paragraph_sheets: Sequence[Any],
) -> Dict[str, Any]:
    sheet = run.get("ParagraphSheet") if hasattr(run, "get") else None
    merged: Dict[str, Any] = {}
    if sheet:
        index = int(_number(sheet.get("DefaultStyleSheet"), -1))
        if 0 <= index < len(paragraph_sheets):
            base = paragraph_sheets[index]
            if hasattr(base, "get"):
                props = base.get("Properties")
                if props:
                    for key, value in props.items():
                        merged[key] = value
        props = sheet.get("Properties")
        if props:
            for key, value in props.items():
                merged[key] = value
    return merged


def _unit_boundaries(text: str) -> List[int]:
    """Map UTF-16 code-unit offsets to Python string indices."""
    boundaries = [0]
    units = 0
    for char in text:
        units += 2 if ord(char) > 0xFFFF else 1
        boundaries.append(units)
    return boundaries


def _offsets_from_units(
    boundaries: Sequence[int], start: int, length: int
) -> Tuple[int, int]:
    total_units = boundaries[-1]

    def index_for(unit: int) -> int:
        unit = max(0, min(unit, total_units))
        for position, boundary in enumerate(boundaries):
            if boundary >= unit:
                return position
        return len(boundaries) - 1

    start = max(0, min(start, total_units))
    end = max(start, min(start + max(0, length), total_units))
    return index_for(start), index_for(end)


def _argb_color(fill: Any) -> Tuple[Optional[str], float]:
    """Convert engine FillColor (A, R, G, B in 0..1) to hex and opacity."""
    if not hasattr(fill, "get"):
        return None, 1.0
    if int(_number(fill.get("Type"), 1)) != 1:
        return None, 1.0
    values = fill.get("Values") or []
    try:
        numbers = [_number(item) for item in values]
    except TypeError:
        return None, 1.0
    if len(numbers) == 4:
        alpha, red, green, blue = numbers
    elif len(numbers) == 3:
        alpha = 1.0
        red, green, blue = numbers
    else:
        return None, 1.0

    def channel(value: float) -> int:
        return max(0, min(255, int(value * 255 + 0.5)))

    hex_color = f"#{channel(red):02X}{channel(green):02X}{channel(blue):02X}"
    return hex_color, round(max(0.0, min(1.0, alpha)), 4)


def _font_info(style: Dict[str, Any], font_name: Optional[str]) -> Dict[str, Any]:
    family, font_style = _split_font_name(font_name)
    faux_bold = bool(_value(style.get("FauxBold"), False))
    faux_italic = bool(_value(style.get("FauxItalic"), False))
    haystack = f"{font_name or ''} {font_style or ''}".lower()
    features = []
    if "Ligatures" in style:
        features.append({"tag": "liga", "enabled": bool(_value(style.get("Ligatures")))})
    if "DLigatures" in style:
        features.append({"tag": "dlig", "enabled": bool(_value(style.get("DLigatures")))})
    return {
        "family": family or "Unknown",
        "post_script_name": font_name,
        "style": font_style,
        "weight": _map_weight(font_name, font_style, faux_bold),
        "width": None,
        "is_bold": faux_bold or "bold" in haystack,
        "is_italic": faux_italic or "italic" in haystack or "oblique" in haystack,
        "is_underline": bool(_value(style.get("Underline"), False)),
        "is_strikethrough": bool(_value(style.get("Strikethrough"), False)),
        "missing": False,
        "fallback_used": None,
        "features": features,
    }


def _effect_names(layer: Any) -> List[str]:
    try:
        if layer.has_effects():
            return [type(effect).__name__ for effect in layer.effects]
    except Exception:
        pass
    return []


def _text_type_value(layer: Any) -> Optional[int]:
    text_type = getattr(layer, "text_type", None)
    if text_type is None:
        return None
    return int(getattr(text_type, "value", text_type))


def _text_box(layer: Any, is_paragraph: bool, orientation: str) -> Dict[str, Any]:
    left, top, right, bottom = layer.bbox
    transform = getattr(layer, "transform", None)
    matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    if transform:
        try:
            matrix = [float(item) for item in transform]
        except (TypeError, ValueError):
            pass
    return {
        "x": float(left),
        "y": float(top),
        "width_px": float(right - left),
        "height_px": float(bottom - top),
        "auto_wrap": bool(is_paragraph),
        "text_direction": orientation,
        "transform_matrix": matrix,
        "content_width_px": None,
        "content_height_px": None,
    }


def extract_typography(
    layer: Any, dpi: float = 72.0
) -> Tuple[Dict[str, Any], List[str]]:
    """Extract a ``Typography`` payload from a psd-tools type layer.

    Returns ``(payload, warnings)``. Warnings describe missing or ambiguous
    native data; they never replace absent values with guesses.
    """
    warnings: List[str] = []
    engine = getattr(layer, "engine_dict", None) or {}
    resource = getattr(layer, "resource_dict", None) or {}

    raw_text = getattr(layer, "text", None) or ""
    # Photoshop uses '\r' for line breaks. Replace one-for-one so run
    # offsets stay aligned.
    text = raw_text.replace("\r", "\n")

    dpi = float(dpi or 72.0)
    px_per_pt = dpi / 72.0

    font_set = list(resource.get("FontSet") or [])
    style_sheets = list(resource.get("StyleSheetSet") or [])
    paragraph_sheets = list(resource.get("ParagraphSheetSet") or [])

    style_run = engine.get("StyleRun") or {}
    default_sheet = style_run.get("DefaultRunData")
    default_data = None
    if default_sheet is not None and hasattr(default_sheet, "get"):
        style = default_sheet.get("StyleSheet") or {}
        default_data = style.get("StyleSheetData")

    boundaries = _unit_boundaries(text)
    run_lengths = list(style_run.get("RunLengthArray") or [])
    run_array = list(style_run.get("RunArray") or [])
    if not run_array and text:
        warnings.append("StyleRun data is missing; character styling is unavailable.")

    character_runs: List[Dict[str, Any]] = []
    run_meta: List[Dict[str, Any]] = []
    unit_cursor = 0
    for index, length in enumerate(run_lengths):
        run = run_array[index] if index < len(run_array) else None
        if run is None:
            unit_cursor += int(_number(length))
            continue
        style, sheet_index = _merged_style(run, style_sheets, default_data)
        start, end = _offsets_from_units(boundaries, unit_cursor, int(_number(length)))
        unit_cursor += int(_number(length))
        content = text[start:end]

        font_index = int(_number(style.get("Font"), 0))
        font_name = None
        if 0 <= font_index < len(font_set):
            entry = font_set[font_index]
            if hasattr(entry, "get"):
                font_name = _clean_font_name(entry.get("Name"))
        else:
            warnings.append(
                f"Style run {index} references missing font index {font_index}."
            )

        font_size_pt = _number(style.get("FontSize"), 0.0)
        if font_size_pt <= 0:
            warnings.append(f"Style run {index} has no native font size.")
        effective_px = round(font_size_pt * px_per_pt, 2)

        color, opacity = _argb_color(style.get("FillColor"))
        if color is None:
            color = "#000000"
            warnings.append(
                f"Style run {index} has no readable RGB fill color; "
                "the run color is a placeholder."
            )

        tracking = _number(style.get("Tracking"), 0.0)
        auto_kerning = bool(_value(style.get("AutoKerning"), True))
        kerning = None if auto_kerning else _number(style.get("Kerning"), 0.0)

        character_runs.append(
            {
                "start": start,
                "end": end,
                "content": content,
                "font": _font_info(style, font_name),
                "source_font_size": {
                    "value": round(font_size_pt, 2),
                    "unit": "pt",
                    "converted_px": effective_px,
                    "conversion_basis": f"{dpi:g} DPI (pt -> px)",
                },
                "effective_font_size_px": effective_px,
                "color": color,
                "opacity": opacity,
                "tracking": tracking,
                "kerning": kerning,
                "letter_spacing_px": round(tracking / 1000.0 * effective_px, 2),
                "paragraph_index": 0,
            }
        )
        run_meta.append(
            {
                "start": start,
                "end": end,
                "sheet_index": sheet_index,
                "auto_leading": bool(_value(style.get("AutoLeading"), False)),
                "leading_pt": _number(style.get("Leading"), 0.0),
                "size_px": effective_px,
                "direction": int(_number(style.get("CharacterDirection"), 0)),
            }
        )

    if text and unit_cursor < boundaries[-1]:
        warnings.append(
            "Style run lengths cover fewer UTF-16 units than the text content."
        )

    # -- paragraphs ------------------------------------------------------
    paragraph_run = engine.get("ParagraphRun") or {}
    para_lengths = list(paragraph_run.get("RunLengthArray") or [])
    para_array = list(paragraph_run.get("RunArray") or [])
    paragraph_runs: List[Dict[str, Any]] = []
    para_unit = 0
    for index, length in enumerate(para_lengths):
        run = para_array[index] if index < len(para_array) else None
        start, end = _offsets_from_units(boundaries, para_unit, int(_number(length)))
        para_unit += int(_number(length))
        if run is None:
            continue
        props = _merged_paragraph(run, paragraph_sheets)

        meta = next(
            (item for item in run_meta if item["start"] <= start < item["end"]),
            run_meta[0] if run_meta else None,
        )
        size_px = float(meta["size_px"]) if meta else 0.0
        auto_leading = _number(props.get("AutoLeading"), 0.0)
        line_height_px = None
        line_height_percent = None
        if meta and meta["auto_leading"] and auto_leading > 0 and size_px > 0:
            line_height_px = round(size_px * auto_leading, 2)
            line_height_percent = round(auto_leading * 100.0, 2)
        elif meta and meta["leading_pt"] > 0:
            line_height_px = round(meta["leading_pt"] * px_per_pt, 2)
            if size_px > 0:
                line_height_percent = round(line_height_px / size_px * 100.0, 2)

        justification = int(_number(props.get("Justification"), 0))
        alignment = _JUSTIFICATION.get(justification, "unknown")

        paragraph_runs.append(
            {
                "start": start,
                "end": end,
                "alignment": alignment,
                "line_height_px": line_height_px,
                "line_height_percent": line_height_percent,
                "space_before_px": round(_number(props.get("SpaceBefore")) * px_per_pt, 2),
                "space_after_px": round(_number(props.get("SpaceAfter")) * px_per_pt, 2),
                "first_line_indent_px": round(
                    _number(props.get("FirstLineIndent")) * px_per_pt, 2
                ),
                "left_indent_px": round(
                    _number(props.get("StartIndent")) * px_per_pt, 2
                ),
                "right_indent_px": round(
                    _number(props.get("EndIndent")) * px_per_pt, 2
                ),
                "direction": "ltr",
                "justified_last_line": justification == 6,
            }
        )

    for run in character_runs:
        for para_index, paragraph in enumerate(paragraph_runs):
            if paragraph["start"] <= run["start"] < paragraph["end"]:
                run["paragraph_index"] = para_index
                break

    # -- orientation and dominant values ---------------------------------
    direction_counts: Dict[int, int] = {}
    for meta in run_meta:
        direction = int(meta.get("direction", 0))
        direction_counts[direction] = direction_counts.get(direction, 0) + len(
            text[meta["start"] : meta["end"]]
        )
    dominant_direction = (
        max(direction_counts.items(), key=lambda item: item[1])[0]
        if direction_counts
        else 0
    )
    orientation = _DIRECTION.get(dominant_direction, "horizontal")
    if dominant_direction != 0:
        warnings.append(
            "Vertical text direction was detected; orientation is reported but "
            "text-box geometry remains the native bounding box."
        )

    family_counts: Dict[str, int] = {}
    size_counts: Dict[float, int] = {}
    for run in character_runs:
        count = max(1, len(run["content"]))
        family = run["font"]["family"]
        family_counts[family] = family_counts.get(family, 0) + count
        size = run["effective_font_size_px"]
        size_counts[size] = size_counts.get(size, 0) + count

    dominant_family = (
        max(family_counts.items(), key=lambda item: item[1])[0]
        if family_counts
        else None
    )
    dominant_size = (
        max(size_counts.items(), key=lambda item: item[1])[0] if size_counts else None
    )

    text_type = _text_type_value(layer)
    if text_type is None:
        warnings.append(
            "Text type (point/paragraph) could not be determined; auto-wrap "
            "defaults to paragraph behavior."
        )
    is_paragraph = text_type == 1 if text_type is not None else True

    payload = {
        "content": text,
        "orientation": orientation,
        "text_box": _text_box(layer, is_paragraph, orientation),
        "character_runs": character_runs,
        "paragraph_runs": paragraph_runs,
        "total_characters": len(text),
        "total_lines": text.count("\n") + 1 if text else 0,
        "dominant_font_family": dominant_family,
        "dominant_font_size_px": dominant_size,
        "effects": _effect_names(layer),
        "extraction_source": "psd_native",
    }
    return payload, warnings
