"""Layer asset export.

Exports individual layer renderings as PNG files. Pixels come from
psd-tools' own rendering, so the output is a raster fallback rather than a
reconstruction of native vector data. Identical images are stored once and
linked from every layer that produced them.
"""

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple
import hashlib
import json
import re

from psd_tools import PSDImage

from ..adapters.psd_tools_adapter import PsdToolsAdapter

ASSET_VERSION = "1.0.0"
ASSET_DIRNAME = "layer-previews"


def export_layer_assets(
    input_path: Path,
    raw_layers: List[Dict[str, Any]],
    output_dir: Path,
) -> Dict[str, Any]:
    """Render every non-group layer to PNG under ``output_dir/layer-previews``.

    Args:
        input_path: Source PSD/PSB file (read-only).
        raw_layers: Layer records from the adapter, used for stable IDs.
        output_dir: Directory that receives ``layer-previews/`` and
            ``asset-index.json``.

    Returns:
        Asset index payload plus the written relative file paths under the
        ``files`` key.
    """
    output_dir = Path(output_dir)
    preview_dir = output_dir / ASSET_DIRNAME
    preview_dir.mkdir(parents=True, exist_ok=True)

    native_ids = {
        raw["source_layer_id"]: raw["id"]
        for raw in raw_layers
        if raw.get("source_layer_id") is not None
    }
    known_ids = {raw["id"] for raw in raw_layers}

    assets: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    by_hash: Dict[str, Dict[str, Any]] = {}
    files: List[str] = []
    total_bytes = 0

    with open(input_path, "rb") as handle:
        psd = PSDImage.open(handle)
        for layer, path_key in _iter_layers(list(psd)):
            layer_id = native_ids.get(getattr(layer, "layer_id", None))
            if layer_id is None:
                layer_id = PsdToolsAdapter._layer_id(layer, path_key)
            if layer_id not in known_ids:
                skipped.append({
                    "layerId": layer_id,
                    "layerName": layer.name,
                    "reason": "layer_id_not_present_in_ir",
                })
                continue
            if layer.is_group():
                continue

            try:
                image = layer.topil()
            except Exception as error:
                skipped.append({
                    "layerId": layer_id,
                    "layerName": layer.name,
                    "reason": f"render_failed: {error}",
                })
                continue
            if image is None:
                skipped.append({
                    "layerId": layer_id,
                    "layerName": layer.name,
                    "reason": "no_raster_output",
                })
                continue

            image = image.convert("RGBA")
            # psd-tools attaches a freshly generated ICC profile whose header
            # carries the current time. Keeping it would make PNG hashes and
            # deduplication differ between identical runs.
            image.info.clear()
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=False)
            payload = buffer.getvalue()
            digest = hashlib.sha256(payload).hexdigest()

            left, top, right, bottom = layer.bbox
            entry: Dict[str, Any] = {
                "layerId": layer_id,
                "layerName": layer.name,
                "kind": PsdToolsAdapter.KIND_MAP.get(layer.kind, "pixel"),
                "format": "png",
                "sha256": digest,
                "sizeBytes": len(payload),
                "widthPx": int(image.width),
                "heightPx": int(image.height),
                "bounds": {
                    "x": int(left),
                    "y": int(top),
                    "width": int(right - left),
                    "height": int(bottom - top),
                },
                "documentOffset": {"x": int(left), "y": int(top)},
                "visible": layer.is_visible(),
                "mask": {
                    "hasMask": bool(layer.has_mask()),
                    "hasVectorMask": bool(layer.has_vector_mask()),
                },
            }

            existing = by_hash.get(digest)
            if existing is not None:
                entry["file"] = existing["file"]
                entry["duplicatedFrom"] = existing["layerId"]
                assets.append(entry)
                continue

            relative = f"{ASSET_DIRNAME}/{_asset_filename(layer_id, layer.name)}"
            path = output_dir / relative
            path.write_bytes(payload)
            entry["file"] = relative
            by_hash[digest] = entry
            assets.append(entry)
            files.append(relative)
            total_bytes += len(payload)

    index = {
        "schemaVersion": ASSET_VERSION,
        "basis": "rendered_layer_pixels",
        "note": (
            "PNG files are psd-tools raster renderings of individual layers. "
            "They are not native vector exports and may differ from Photoshop "
            "for unsupported effects. Identical images are stored once."
        ),
        "summary": {
            "exportedLayers": len(assets),
            "uniqueFiles": len(files),
            "deduplicatedLayers": len(assets) - len(files),
            "skippedLayers": len(skipped),
            "totalBytes": total_bytes,
        },
        "assets": assets,
        "skipped": skipped,
    }

    index_path = output_dir / "asset-index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    files.append("asset-index.json")
    index["files"] = files
    return index


def _iter_layers(
    siblings: List[Any], path_key: str = ""
) -> Iterator[Tuple[Any, str]]:
    """Yield layers with the same deterministic path keys as the adapter."""
    for index, layer in enumerate(siblings):
        child_key = f"{path_key}{index}" if not path_key else f"{path_key}-{index}"
        yield layer, child_key
        if layer.is_group():
            yield from _iter_layers(list(layer), child_key)


def _asset_filename(layer_id: str, name: str) -> str:
    identifier = re.sub(r"[^A-Za-z0-9_-]+", "-", layer_id).strip("-") or "layer"
    slug = re.sub(r"[^\w-]+", "_", name or "", flags=re.UNICODE).strip("_")
    slug = slug[:48]
    return f"{identifier}-{slug}.png" if slug else f"{identifier}.png"
