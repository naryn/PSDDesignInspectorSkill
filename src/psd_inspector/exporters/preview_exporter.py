"""Composite preview rendering and measured-geometry annotation."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from ..analysis.geometry_engine import layer_rect


KIND_COLORS = {
    "pixel": (47, 128, 237),       # blue
    "text": (39, 174, 96),         # green
    "shape": (242, 153, 74),       # orange
    "smart_object": (155, 81, 224),  # purple
    "group": (127, 140, 141),      # gray
    "adjustment": (192, 57, 43),   # red
    "fill": (41, 128, 185),
    "stroke": (142, 68, 173),
}
DEFAULT_COLOR = (52, 73, 94)
SPACING_COLOR = (230, 126, 34)
LABEL_TEXT_COLOR = (255, 255, 255)

FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


def _font(size: int = 12):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_composite(psd_path: Path) -> Image.Image:
    """Render the composite preview from layer data.

    ``force=True`` ignores the PSD's embedded merged preview so the result
    always matches the parsed layer stack instead of a possibly stale image.
    """
    from psd_tools import PSDImage

    psd = PSDImage.open(psd_path)
    image = psd.composite(force=True)
    if image is None:
        raise ValueError("psd-tools did not return a composite image")
    return image.convert("RGBA")


def _scaled(box: Tuple[float, float, float, float], sx: float, sy: float) -> Tuple[float, float, float, float]:
    x, y, width, height = box
    return (x * sx, y * sy, (x + width) * sx, (y + height) * sy)


def _dashed_rectangle(
    draw: ImageDraw.ImageDraw,
    box: Tuple[float, float, float, float],
    color: Tuple[int, int, int, int],
    dash: int = 5,
    gap: int = 3,
    width: int = 1,
) -> None:
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return
    step = dash + gap
    for x in range(int(x1), int(x2), step):
        draw.line([(x, y1), (min(x + dash, x2), y1)], fill=color, width=width)
        draw.line([(x, y2), (min(x + dash, x2), y2)], fill=color, width=width)
    for y in range(int(y1), int(y2), step):
        draw.line([(x1, y), (x1, min(y + dash, y2))], fill=color, width=width)
        draw.line([(x2, y), (x2, min(y + dash, y2))], fill=color, width=width)


def _label(
    draw: ImageDraw.ImageDraw,
    anchor: Tuple[float, float],
    text: str,
    color: Tuple[int, int, int, int],
    font,
) -> None:
    x, y = anchor
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    pad = 2
    draw.rectangle(
        [left - pad, top - pad, right + pad, bottom + pad],
        fill=(*color[:3], 220),
    )
    draw.text((x, y), text, font=font, fill=LABEL_TEXT_COLOR)


def _overlap_interval(
    a_start: float, a_end: float, b_start: float, b_end: float
) -> Optional[Tuple[float, float]]:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return (start, end) if end > start else None


def draw_annotations(
    image: Image.Image,
    layers: Sequence[Dict[str, Any]],
    show: Sequence[str] = ("bounds",),
    relationships: Optional[Sequence[Dict[str, Any]]] = None,
    document_width: Optional[float] = None,
    document_height: Optional[float] = None,
    include_hidden: bool = False,
) -> Image.Image:
    """Draw layer bounds, IDs and measured gaps over a composite image.

    All coordinates come from the IR and are scaled when the supplied preview
    differs in size from the document canvas.
    """
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(12)

    doc_w = float(document_width or base.width)
    doc_h = float(document_height or base.height)
    sx = base.width / doc_w if doc_w else 1.0
    sy = base.height / doc_h if doc_h else 1.0

    by_id = {layer.get("id"): layer for layer in layers}
    draw_layers = [
        layer
        for layer in layers
        if (include_hidden or layer.get("visible", True)) and layer.get("kind") != "adjustment"
    ]

    if "bounds" in show:
        for layer in draw_layers:
            rect = layer_rect(layer)
            if rect[2] <= 0 or rect[3] <= 0:
                continue
            box = _scaled(rect, sx, sy)
            color = KIND_COLORS.get(layer.get("kind"), DEFAULT_COLOR)
            if layer.get("kind") == "group":
                _dashed_rectangle(draw, box, (*color, 220))
            else:
                draw.rectangle(box, outline=(*color, 235), width=1)

    if "ids" in show:
        for index, layer in enumerate(draw_layers):
            rect = layer_rect(layer)
            if rect[2] <= 0 or rect[3] <= 0:
                continue
            box = _scaled(rect, sx, sy)
            color = KIND_COLORS.get(layer.get("kind"), DEFAULT_COLOR)
            name = layer.get("name") or layer.get("id")
            text = f"{name[:32]} · {layer.get('id')}"
            # Alternate above/below so labels on adjacent layers do not collide.
            anchor_y = max(0.0, box[1] - 15) if index % 2 == 0 else box[3] + 2
            _label(draw, (box[0], anchor_y), text, (*color, 235), font)

    if "spacing" in show and relationships:
        for rel in relationships:
            if not rel.get("projection_overlap"):
                continue
            position = rel.get("relative_position")
            if position not in ("left", "right", "above", "below"):
                continue
            source = by_id.get(rel.get("source_layer_id"))
            target = by_id.get(rel.get("target_layer_id"))
            if source is None or target is None:
                continue
            if not source.get("visible", True) or not target.get("visible", True):
                continue

            source_rect = layer_rect(source)
            target_rect = layer_rect(target)
            gap = float(rel.get("distance_px") or 0.0)
            if gap <= 0:
                continue

            if position in ("left", "right"):
                interval = _overlap_interval(
                    source_rect[1], source_rect[1] + source_rect[3],
                    target_rect[1], target_rect[1] + target_rect[3],
                )
                if interval is None:
                    continue
                mid_y = (interval[0] + interval[1]) / 2 * sy
                if position == "right":
                    start = (source_rect[0] + source_rect[2]) * sx
                    end = target_rect[0] * sx
                else:
                    start = (target_rect[0] + target_rect[2]) * sx
                    end = source_rect[0] * sx
                label = f"gap {gap:g}px"
                draw.line([(start, mid_y), (end, mid_y)], fill=(*SPACING_COLOR, 235), width=2)
                draw.line([(start, mid_y - 4), (start, mid_y + 4)], fill=(*SPACING_COLOR, 235), width=2)
                draw.line([(end, mid_y - 4), (end, mid_y + 4)], fill=(*SPACING_COLOR, 235), width=2)
                _label(draw, (min(start, end) + 4, mid_y - 16), label, (*SPACING_COLOR, 235), font)
            else:
                interval = _overlap_interval(
                    source_rect[0], source_rect[0] + source_rect[2],
                    target_rect[0], target_rect[0] + target_rect[2],
                )
                if interval is None:
                    continue
                mid_x = (interval[0] + interval[1]) / 2 * sx
                if position == "below":
                    start = (source_rect[1] + source_rect[3]) * sy
                    end = target_rect[1] * sy
                else:
                    start = (target_rect[1] + target_rect[3]) * sy
                    end = source_rect[1] * sy
                label = f"gap {gap:g}px"
                draw.line([(mid_x, start), (mid_x, end)], fill=(*SPACING_COLOR, 235), width=2)
                draw.line([(mid_x - 4, start), (mid_x + 4, start)], fill=(*SPACING_COLOR, 235), width=2)
                draw.line([(mid_x - 4, end), (mid_x + 4, end)], fill=(*SPACING_COLOR, 235), width=2)
                _label(draw, (mid_x + 6, min(start, end) + 2), label, (*SPACING_COLOR, 235), font)

    return Image.alpha_composite(base, overlay)
