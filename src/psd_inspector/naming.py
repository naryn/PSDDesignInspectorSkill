"""AI-assisted naming pack and merge.

AI naming is opt-in and lives outside the deterministic Design IR. ``pack``
builds a compact context file for a host agent; ``apply`` validates the agent's
suggestions and writes an independent ``names.json``. The native layer ``name``
is never modified.
"""

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

NAMING_VERSION = "1.0.0"
VISUAL_VERSION = "1.0.0"
MAX_TEXT_CHARS = 160
MAX_CHILD_SUMMARIES = 20
DEFAULT_MAX_EDGE = 512
DEFAULT_PADDING = 32

SEMANTIC_VOCABULARY = {
    "regions": [
        "header", "navigation", "sidebar", "main-content", "hero", "banner",
        "footer", "toolbar", "modal", "dialog", "drawer", "overlay", "toast",
        "breadcrumb", "pagination", "tabs",
    ],
    "elements": [
        "button", "icon", "logo", "avatar", "badge", "card", "list",
        "list-item", "form", "input", "search", "dropdown", "checkbox",
        "radio", "switch", "slider", "table", "carousel", "gallery",
        "thumbnail", "tooltip", "tag", "progress", "skeleton",
    ],
}

_ROLE_KEYWORDS = (
    ("header", ("header", "top", "top bar", "topbar", "toolbar")),
    ("navigation", ("nav", "navigation", "menu", "tabbar", "tab bar")),
    ("sidebar", ("sidebar", "side bar", "left menu", "right menu", "drawer")),
    ("footer", ("footer",)),
    ("hero", ("hero", "banner", "cover")),
    ("modal", ("modal", "dialog", "popup", "popover", "overlay")),
    ("card", ("card", "tile")),
    ("button", ("button", "btn", "cta")),
    ("form", ("form", "input", "search", "field", "login")),
    ("list", ("list", "queue", "grid", "item", "row")),
    ("media", ("image", "photo", "video", "thumbnail", "poster", "art")),
    ("icon", ("icon", "logo", "avatar", "badge")),
)


class NamingError(ValueError):
    """Raised when a naming pack or candidate file is invalid."""


def build_naming_pack(
    ir: Dict[str, Any],
    max_text_chars: int = MAX_TEXT_CHARS,
    visual_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a deterministic context pack for a host agent to name layers."""
    layers = _layers(ir)
    metadata = ir.get("document", {}).get("metadata", {})
    document_width = metadata.get("width_px")
    document_height = metadata.get("height_px")
    ir_sha256 = ir_sha256_for(ir)
    fallbacks = _fallback_names(layers)
    name_counts = Counter(
        layer["name"].strip().casefold()
        for layer in layers
        if layer.get("name") and layer["name"].strip()
    )
    children: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    siblings: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    by_id = {layer["id"]: layer for layer in layers}
    for layer in layers:
        parent_id = layer.get("parent_id")
        siblings[parent_id].append(layer)
        if parent_id:
            children[parent_id].append(layer)

    crops = (visual_context or {}).get("crops") or {}
    crop_count = (visual_context or {}).get("cropCount")
    if crop_count is None:
        crop_count = len(crops)
    entries: List[Dict[str, Any]] = []
    for layer in layers:
        name = (layer.get("name") or "").strip()
        duplicate = bool(name) and name_counts.get(name.casefold(), 0) > 1
        parent_id = layer.get("parent_id")
        parent_name = by_id[parent_id].get("name") if parent_id in by_id else None
        sibling_names = []
        if duplicate:
            sibling_names = [
                sibling.get("name")
                for sibling in siblings.get(parent_id, [])
                if sibling["id"] != layer["id"]
            ][:8]
        entry = _pack_entry(
            layer,
            fallbacks[layer["id"]],
            name_counts,
            children.get(layer["id"], []),
            max_text_chars,
            document_width,
            document_height,
            parent_name,
            sibling_names,
            crops.get(layer["id"]),
        )
        entries.append(entry)

    duplicate_layers = sum(1 for entry in entries if entry["duplicateName"])
    return {
        "schemaVersion": NAMING_VERSION,
        "source": {
            "filename": metadata.get("filename"),
            "irSha256": ir_sha256,
        },
        "document": {
            "widthPx": document_width,
            "heightPx": document_height,
        },
        "namingConvention": (
            "Use lowercase kebab-case ASCII names with a semantic path, for example "
            "'header/nav', 'hero/primary-cta' or 'footer/legal-links'. Name from the "
            "actual visual evidence first, then hierarchy, role, text and geometry."
        ),
        "semanticVocabulary": SEMANTIC_VOCABULARY,
        "instructions": [
            "Name only layers present in this pack; copy ids exactly.",
            "Inspect visualEvidence.preview and every visual.crop before naming a "
            "group, a text layer without extracted content, or a duplicate layer.",
            "Use originalName, hierarchy, bounds, layout.regionCandidates, roleHints, "
            "childKinds, childTextSamples and siblingNames as evidence, not facts.",
            "Classify window regions (header, navigation, sidebar, hero, footer, "
            "modal, card) from position, size and actual imagery. Prefer terms in "
            "semanticVocabulary when the evidence matches.",
            "Resolve duplicate original names from parent, siblings and visual "
            "context instead of copying suffixes.",
            "Name groups from their children and role, not from their default PSD name.",
            "Never infer hidden-layer content from the composite preview; use native "
            "name, hierarchy and metadata for hidden layers.",
            "Use confidence 0.0-1.0 and omit a suggestion when confidence is below 0.5.",
            "Write candidate names to names.json and run 'names apply' to validate.",
            "Never treat suggested names as native PSD values.",
        ],
        "visualEvidence": {
            "version": VISUAL_VERSION,
            "preview": (visual_context or {}).get("preview"),
            "visualsDir": (visual_context or {}).get("root"),
            "cropCount": crop_count,
            "layersWithVisual": len(crops),
            "skipped": (visual_context or {}).get("skipped", {}),
            "note": (
                "visual.crop is a PNG crop of the composite preview around the "
                "layer, scaled down and padded. visual.asset is the rendered layer "
                "pixel fallback when exported. Hidden layers have no composite crop."
            ),
        },
        "candidateFormat": {
            "schemaVersion": NAMING_VERSION,
            "source": {"irSha256": ir_sha256},
            "names": {
                "layer-123": {
                    "suggestedName": "hero/primary-cta",
                    "confidence": 0.9,
                    "reason": "Visible button-like element below the hero headline.",
                }
            },
        },
        "summary": {
            "total": len(entries),
            "groups": sum(1 for entry in entries if entry["kind"] == "group"),
            "textLayers": sum(1 for entry in entries if entry["kind"] == "text"),
            "duplicateNameLayers": duplicate_layers,
            "hiddenLayers": sum(1 for entry in entries if not entry["visible"]),
            "visualCrops": crop_count,
        },
        "layers": entries,
    }


def render_naming_visuals(
    ir: Dict[str, Any],
    output_dir: Path,
    preview_path: Path,
    *,
    max_edge: int = DEFAULT_MAX_EDGE,
    padding: int = DEFAULT_PADDING,
) -> Dict[str, Any]:
    """Crop visual context for groups and ambiguous layers from the preview.

    The crop is taken from the composite preview, padded to include surrounding
    context and downscaled. It is evidence for a host agent, not a layer export.
    """
    from PIL import Image

    layers = _layers(ir)
    metadata = ir.get("document", {}).get("metadata", {})
    document_width = metadata.get("width_px")
    document_height = metadata.get("height_px")
    name_counts = Counter(
        layer["name"].strip().casefold()
        for layer in layers
        if layer.get("name") and layer["name"].strip()
    )
    targets = [
        layer for layer in layers if _needs_visual_crop(layer, name_counts)
    ]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = Path(preview_path)

    skipped = {"hidden": 0, "noBounds": 0, "invalidBounds": 0}
    crops: Dict[str, Dict[str, Any]] = {}
    written: List[str] = []
    by_digest: Dict[str, Dict[str, Any]] = {}
    by_bounds: Dict[Tuple[int, int, int, int], Dict[str, Any]] = {}

    with Image.open(preview_path) as preview:
        preview.load()
        if document_width and document_height:
            scale_x = preview.width / float(document_width)
            scale_y = preview.height / float(document_height)
        else:
            document_width, document_height = preview.width, preview.height
            scale_x = scale_y = 1.0

        for layer in targets:
            if not layer.get("visible", True):
                skipped["hidden"] += 1
                continue
            bounds = _source_bounds(layer)
            if bounds is None:
                skipped["noBounds"] += 1
                continue
            x, y, width, height = bounds
            if width <= 0 or height <= 0:
                skipped["invalidBounds"] += 1
                continue

            box = _crop_box(
                x, y, width, height,
                document_width, document_height,
                scale_x, scale_y, padding,
            )
            if box is None or box[2] <= box[0] or box[3] <= box[1]:
                skipped["invalidBounds"] += 1
                continue

            cached = by_bounds.get(box)
            if cached is not None:
                crops[layer["id"]] = _crop_reference(cached, layer["id"])
                continue

            crop = preview.crop(box)
            if max(crop.size) > max_edge:
                crop.thumbnail((max_edge, max_edge), Image.LANCZOS)
            crop.info.clear()
            buffer = BytesIO()
            crop.save(buffer, format="PNG", optimize=False)
            payload = buffer.getvalue()
            digest = hashlib.sha256(payload).hexdigest()

            existing = by_digest.get(digest)
            if existing is not None:
                record = _crop_reference(existing, layer["id"])
                record["duplicatedFrom"] = existing["layerId"]
                crops[layer["id"]] = record
                by_bounds[box] = record
                continue

            filename = f"{_safe_filename(layer['id'])}-{layer.get('kind') or 'layer'}.png"
            (output_dir / filename).write_bytes(payload)
            written.append(filename)
            record = {
                "layerId": layer["id"],
                "kind": layer.get("kind"),
                "file": filename,
                "sha256": digest,
                "sizeBytes": len(payload),
                "widthPx": int(crop.width),
                "heightPx": int(crop.height),
                "scale": round(min(scale_x, scale_y), 4),
                "layerBounds": {
                    "x": int(x), "y": int(y), "width": int(width), "height": int(height),
                },
                "cropBounds": {
                    "x": int(box[0] / scale_x),
                    "y": int(box[1] / scale_y),
                    "width": int((box[2] - box[0]) / scale_x),
                    "height": int((box[3] - box[1]) / scale_y),
                },
                "paddingPx": padding,
            }
            by_digest[digest] = record
            by_bounds[box] = record
            crops[layer["id"]] = _crop_reference(record, layer["id"])

    return {
        "version": VISUAL_VERSION,
        "root": str(output_dir),
        "preview": str(preview_path),
        "crops": crops,
        "cropCount": len(written),
        "targetCount": len(targets),
        "skipped": skipped,
        "files": written,
    }


def apply_names(ir: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Validate host-agent suggestions and return a complete ``names.json`` payload."""
    layers = _layers(ir)
    by_id = {layer["id"]: layer for layer in layers}
    fallbacks = _fallback_names(layers)
    expected_sha = ir_sha256_for(ir)

    source = candidate.get("source", {})
    if not isinstance(source, dict):
        raise NamingError("candidate.source must be an object")
    provided_sha = source.get("irSha256")
    if provided_sha and provided_sha != expected_sha:
        raise NamingError(
            "candidate source.irSha256 does not match the IR; regenerate the naming pack"
        )

    suggestions: Dict[str, Dict[str, Any]] = {}
    for layer_id, value in _iter_candidate_entries(candidate):
        if layer_id not in by_id:
            raise NamingError(f"unknown layer id: {layer_id}")
        if layer_id in suggestions:
            raise NamingError(f"duplicate suggestion for layer id: {layer_id}")
        suggestions[layer_id] = _normalize_suggestion(layer_id, value)

    warnings: List[str] = []
    if not provided_sha:
        warnings.append("candidate.source.irSha256 is missing; IR identity was not verified")

    used_names: Dict[str, str] = {}
    used_slugs: Dict[str, str] = {}
    output_layers: List[Dict[str, Any]] = []
    duplicates_resolved = 0

    for layer in layers:
        layer_id = layer["id"]
        suggestion = suggestions.get(layer_id)
        suggested_name = (
            suggestion["suggestedName"] if suggestion else fallbacks[layer_id]
        )
        unique_name = suggested_name
        disambiguated = False
        name_key = unique_name.casefold()
        if name_key in used_names:
            suffix = layer.get("source_layer_id") or layer_id
            unique_name = f"{suggested_name} ({suffix})"
            name_key = unique_name.casefold()
            counter = 2
            while name_key in used_names:
                unique_name = f"{suggested_name} ({suffix}-{counter})"
                name_key = unique_name.casefold()
                counter += 1
            disambiguated = True
            duplicates_resolved += 1
        used_names[name_key] = layer_id

        slug = _slugify(unique_name) or _slugify(f"{layer.get('kind')}-{layer_id}")
        slug_key = slug
        counter = 2
        while slug_key in used_slugs:
            slug_key = f"{slug}-{counter}"
            counter += 1
        used_slugs[slug_key] = layer_id

        output_layers.append({
            "id": layer_id,
            "originalName": layer.get("name"),
            "kind": layer.get("kind"),
            "parentId": layer.get("parent_id"),
            "suggestedName": suggested_name,
            "uniqueName": unique_name,
            "slug": slug_key,
            "source": "ai_inferred" if suggestion else "rule_based",
            "confidence": suggestion["confidence"] if suggestion else None,
            "reason": suggestion["reason"] if suggestion else None,
            "disambiguated": disambiguated,
        })

    metadata = ir.get("document", {}).get("metadata", {})
    return {
        "schemaVersion": NAMING_VERSION,
        "source": {
            "filename": metadata.get("filename"),
            "irSha256": expected_sha,
        },
        "namingConvention": (
            "uniqueName and slug are unique. suggestedName keeps the raw suggestion "
            "and must not be treated as a native PSD value."
        ),
        "summary": {
            "total": len(output_layers),
            "aiSuggested": len(suggestions),
            "ruleBased": len(output_layers) - len(suggestions),
            "missingSuggestions": len(output_layers) - len(suggestions),
            "duplicatesResolved": duplicates_resolved,
            "warnings": warnings,
        },
        "layers": output_layers,
    }


def ir_sha256_for(ir: Dict[str, Any]) -> str:
    """Hash the canonical IR payload so pack and apply agree across formatting."""
    payload = json.dumps(
        ir, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _layers(ir: Dict[str, Any]) -> List[Dict[str, Any]]:
    layers = ir.get("source", {}).get("rawLayers", [])
    if not isinstance(layers, list):
        raise NamingError("IR source.rawLayers must be a list")
    return [layer for layer in layers if isinstance(layer, dict) and layer.get("id")]


def _pack_entry(
    layer: Dict[str, Any],
    fallback_name: str,
    name_counts: Counter,
    children: List[Dict[str, Any]],
    max_text_chars: int,
    document_width: Optional[int],
    document_height: Optional[int],
    parent_name: Optional[str],
    sibling_names: List[str],
    visual: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    name = (layer.get("name") or "").strip()
    bounds = _source_bounds(layer) or (None, None, None, None)
    entry: Dict[str, Any] = {
        "id": layer["id"],
        "sourceLayerId": layer.get("source_layer_id"),
        "kind": layer.get("kind"),
        "originalName": layer.get("name"),
        "parentId": layer.get("parent_id"),
        "parentName": parent_name,
        "depth": layer.get("depth"),
        "zIndex": layer.get("z_index"),
        "visible": layer.get("visible", True),
        "bounds": {
            "x": bounds[0],
            "y": bounds[1],
            "width": bounds[2],
            "height": bounds[3],
        },
        "nameOccurrences": name_counts.get(name.casefold(), 0) if name else 0,
        "duplicateName": bool(name) and name_counts.get(name.casefold(), 0) > 1,
        "fallbackName": fallback_name,
    }

    layout = _layout_hints(bounds, document_width, document_height)
    if layout:
        entry["layout"] = layout
    if sibling_names:
        entry["siblingNames"] = sibling_names

    if layer.get("kind") == "text":
        typography = layer.get("typography") or {}
        entry["text"] = _truncate(typography.get("content"), max_text_chars)
        entry["fontFamily"] = typography.get("dominant_font_family")
        entry["fontSizePx"] = typography.get("dominant_font_size_px")

    fills = (layer.get("appearance") or {}).get("fills") or []
    if fills and fills[0].get("solid_color"):
        entry["fillColor"] = fills[0]["solid_color"]
    radius = (layer.get("appearance") or {}).get("border_radius") or {}
    max_radius = max(
        (float(radius.get(key) or 0) for key in (
            "top_left", "top_right", "bottom_right", "bottom_left"
        )),
        default=0.0,
    )
    if max_radius:
        entry["borderRadiusPx"] = max_radius

    export_paths = layer.get("export_paths") or []
    if export_paths:
        entry["asset"] = export_paths[0]

    if visual:
        entry["visual"] = {
            "crop": visual.get("file"),
            "cropBounds": visual.get("cropBounds"),
            "cropWidthPx": visual.get("widthPx"),
            "cropHeightPx": visual.get("heightPx"),
            "cropSha256": visual.get("sha256"),
        }
        if visual.get("duplicatedFrom"):
            entry["visual"]["duplicatedFrom"] = visual["duplicatedFrom"]

    smart_object = layer.get("smart_object_data")
    if smart_object:
        entry["smartObject"] = {
            "filename": smart_object.get("filename"),
            "isPsd": smart_object.get("is_psd"),
        }

    if layer.get("kind") == "group":
        entry["childIds"] = [child["id"] for child in children]
        entry["childCount"] = len(children)
        entry["childKinds"] = dict(Counter(child.get("kind") for child in children))
        entry["childTextSamples"] = [
            text
            for text in (
                _truncate((child.get("typography") or {}).get("content"), 80)
                for child in children
            )
            if text
        ][:5]
        entry["children"] = [
            {
                "id": child["id"],
                "kind": child.get("kind"),
                "name": child.get("name"),
                "text": _truncate(
                    (child.get("typography") or {}).get("content"), 80
                ),
            }
            for child in children[:MAX_CHILD_SUMMARIES]
        ]

    role_hints = _role_hints(layer, children)
    if role_hints:
        entry["roleHints"] = role_hints

    return entry


def _layout_hints(
    bounds: Tuple[Any, Any, Any, Any],
    document_width: Optional[int],
    document_height: Optional[int],
) -> Optional[Dict[str, Any]]:
    x, y, width, height = bounds
    if not document_width or not document_height:
        return None
    if not all(isinstance(value, (int, float)) for value in (x, y, width, height)):
        return None
    if width <= 0 or height <= 0:
        return None

    document_width = float(document_width)
    document_height = float(document_height)
    left_margin = max(0.0, float(x))
    right_margin = max(0.0, document_width - float(x + width))
    top_margin = max(0.0, float(y))
    bottom_margin = max(0.0, document_height - float(y + height))
    spans_width = width >= 0.9 * document_width
    spans_height = height >= 0.9 * document_height

    regions = []
    if spans_width and spans_height:
        regions.append("page-background")
    if y <= 0.08 * document_height and height <= 0.18 * document_height and spans_width:
        regions.append("header")
    if (
        y + height >= 0.92 * document_height
        and height <= 0.15 * document_height
        and spans_width
    ):
        regions.append("footer")
    if (
        x <= 0.15 * document_width
        and width <= 0.2 * document_width
        and height >= 0.5 * document_height
    ):
        regions.append("sidebar-left")
    if (
        x + width >= 0.85 * document_width
        and width <= 0.2 * document_width
        and height >= 0.5 * document_height
    ):
        regions.append("sidebar-right")
    if (
        0.55 * document_width <= width
        and 0.08 * document_height <= y <= 0.35 * document_height
        and 0.15 * document_height <= height <= 0.55 * document_height
    ):
        regions.append("hero")
    if not regions:
        regions.append("main-content")

    return {
        "regionCandidates": regions,
        "horizontal": _alignment(left_margin, right_margin, document_width),
        "vertical": _alignment(top_margin, bottom_margin, document_height),
        "areaRatio": min(1.0, round(
            float(width * height) / (document_width * document_height), 4
        )),
        "spansWidth": spans_width,
        "spansHeight": spans_height,
    }


def _alignment(before: float, after: float, total: float) -> str:
    if abs(before - after) <= max(4.0, 0.05 * total):
        return "center"
    return "left" if before < after else "right"


def _role_hints(
    layer: Dict[str, Any], children: List[Dict[str, Any]]
) -> List[str]:
    corpus = " ".join(
        [layer.get("name") or ""]
        + [child.get("name") or "" for child in children]
        + [
            (child.get("typography") or {}).get("content") or ""
            for child in children[:10]
        ]
    ).casefold()
    tokens = set(re.findall(r"[a-z0-9]+", corpus))
    hints: List[str] = []
    for role, keywords in _ROLE_KEYWORDS:
        if any(
            keyword in corpus if " " in keyword else keyword in tokens
            for keyword in keywords
        ):
            hints.append(role)

    if layer.get("kind") == "group":
        kinds = Counter(child.get("kind") for child in children)
        if kinds.get("text", 0) >= 3 and not kinds.get("shape"):
            hints.append("text-block")
        media = kinds.get("smart_object", 0) + kinds.get("pixel", 0)
        if media >= 3 and not kinds.get("text"):
            hints.append("media-gallery")
        icon_children = sum(
            1
            for child in children
            if any(
                keyword in (child.get("name") or "").casefold()
                for keyword in ("icon", "logo", "avatar")
            )
        )
        if children and icon_children >= max(2, len(children) // 2):
            hints.append("icon-row")

    deduplicated: List[str] = []
    for hint in hints:
        if hint not in deduplicated:
            deduplicated.append(hint)
    return deduplicated[:6]


def _needs_visual_crop(
    layer: Dict[str, Any], name_counts: Counter
) -> bool:
    kind = layer.get("kind")
    if kind == "group":
        return True
    name = (layer.get("name") or "").strip()
    if name and name_counts.get(name.casefold(), 0) > 1:
        return True
    if kind == "text":
        return not (layer.get("typography") or {}).get("content")
    return False


def _source_bounds(
    layer: Dict[str, Any]
) -> Optional[Tuple[int, int, int, int]]:
    bounds = (layer.get("geometry") or {}).get("source_bounds") or {}
    values = tuple(bounds.get(key) for key in ("x", "y", "width", "height"))
    if not all(isinstance(value, (int, float)) for value in values):
        return None
    return tuple(int(value) for value in values)


def _crop_box(
    x: int,
    y: int,
    width: int,
    height: int,
    document_width: int,
    document_height: int,
    scale_x: float,
    scale_y: float,
    padding: int,
) -> Optional[Tuple[int, int, int, int]]:
    left = max(0, x - padding)
    top = max(0, y - padding)
    right = min(document_width, x + width + padding)
    bottom = min(document_height, y + height + padding)
    if right <= left or bottom <= top:
        return None
    return (
        int(round(left * scale_x)),
        int(round(top * scale_y)),
        int(round(right * scale_x)),
        int(round(bottom * scale_y)),
    )


def _crop_reference(
    record: Dict[str, Any], layer_id: str
) -> Dict[str, Any]:
    reference = {
        key: record.get(key)
        for key in (
            "file", "sha256", "widthPx", "heightPx", "scale",
            "layerBounds", "cropBounds", "paddingPx",
        )
    }
    reference["layerId"] = layer_id
    if record.get("duplicatedFrom"):
        reference["duplicatedFrom"] = record["duplicatedFrom"]
    return reference


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "layer"


def _fallback_names(layers: List[Dict[str, Any]]) -> Dict[str, str]:
    used = set()
    names: Dict[str, str] = {}
    for layer in layers:
        base = (layer.get("name") or "").strip() or layer.get("kind") or "layer"
        candidate = base
        key = candidate.casefold()
        if key in used:
            suffix = layer.get("source_layer_id") or layer["id"]
            candidate = f"{base} ({suffix})"
            key = candidate.casefold()
            counter = 2
            while key in used:
                candidate = f"{base} ({suffix}-{counter})"
                key = candidate.casefold()
                counter += 1
        used.add(key)
        names[layer["id"]] = candidate
    return names


def _iter_candidate_entries(candidate: Dict[str, Any]) -> Iterable[Tuple[str, Any]]:
    if not isinstance(candidate, dict):
        raise NamingError("candidate must be a JSON object")
    names = candidate.get("names")
    if isinstance(names, dict):
        for layer_id, value in names.items():
            yield layer_id, value
        return
    if isinstance(names, list):
        for item in names:
            if not isinstance(item, dict):
                raise NamingError("candidate.names entries must be objects")
            layer_id = item.get("layerId")
            if not isinstance(layer_id, str) or not layer_id:
                raise NamingError("candidate.names entries require a layerId")
            yield layer_id, item
        return
    raise NamingError("candidate.names must be an object keyed by layer id or a list")


def _normalize_suggestion(layer_id: str, value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        value = {"suggestedName": value}
    if not isinstance(value, dict):
        raise NamingError(f"suggestion for {layer_id} must be an object or string")

    suggested = value.get("suggestedName")
    if not isinstance(suggested, str) or not suggested.strip():
        raise NamingError(f"suggestion for {layer_id} requires a non-empty suggestedName")
    if len(suggested) > 120:
        raise NamingError(f"suggestion for {layer_id} exceeds 120 characters")
    if any(ord(char) < 32 for char in suggested):
        raise NamingError(f"suggestion for {layer_id} contains control characters")

    confidence = value.get("confidence")
    if confidence is not None:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise NamingError(f"suggestion for {layer_id} has a non-numeric confidence")
        if not 0.0 <= float(confidence) <= 1.0:
            raise NamingError(f"suggestion for {layer_id} confidence must be 0..1")
        confidence = float(confidence)

    reason = value.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise NamingError(f"suggestion for {layer_id} reason must be a string")

    return {
        "suggestedName": suggested.strip(),
        "confidence": confidence,
        "reason": reason,
    }


def _truncate(value: Optional[str], limit: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _slugify(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
