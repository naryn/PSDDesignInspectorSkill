"""PSD parser using psd-tools library."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib

from PIL import Image
from psd_tools import PSDImage

from .base import PSDBaseAdapter, ParseError
from ..extractors import extract_appearance, extract_typography
from ..models.document import Artboard, ColorMode, CoordinateSpace, DocumentMetadata, PSDVersion


class PsdToolsAdapter(PSDBaseAdapter):
    """Adapter for parsing PSD/PSB files using psd-tools.

    Only native properties are exposed here. Anything psd-tools cannot
    provide must remain absent or `None` rather than being invented.
    """

    PSD_SIGNATURE = b"8BPS"

    # psd-tools layer.kind values -> our layer kind values
    KIND_MAP = {
        "pixel": "pixel",
        "group": "group",
        "type": "text",
        "shape": "shape",
        "smartobject": "smart_object",
        "adjustment": "adjustment",
        "fill": "fill",
        "stroke": "stroke",
    }

    COLOR_MODE_MAP = {
        "BITMAP": ColorMode.Bitmap,
        "GRAYSCALE": ColorMode.Grayscale,
        "INDEXED": ColorMode.Indexed,
        "RGB": ColorMode.RGB,
        "CMYK": ColorMode.CMYK,
        "MULTICHANNEL": ColorMode.MultiChannel,
        "DUOTONE": ColorMode.Duotone,
        "LAB": ColorMode.Lab,
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._supported_features = [
            "layers",
            "layer_hierarchy",
            "text_content",
            "text_styles",
            "font_families",
            "sizes_and_positions",
            "colors",
            "blend_modes",
            "opacities",
            "layer_masks",
            "vector_masks",
            "clipping_masks",
            "smart_objects",
            "vector_shapes",
            "shape_fill_stroke",
            "layer_effects",
            "layer_effects_presence",
        ]

        self._unsupported_features = [
            "artboards",
            "advanced_gradient_stops",
            "complex_transforms",
            "custom_brush_patterns",
            "filter_effects",
        ]

    @staticmethod
    def _is_psdsignature(header: bytes) -> bool:
        return header == PsdToolsAdapter.PSD_SIGNATURE

    def can_parse(self, file_path: Path) -> bool:
        if not self.validate_file(file_path):
            return False

        try:
            with open(file_path, "rb") as f:
                PSDImage.open(f)
            return True
        except Exception:
            return False

    def parse(self, file_path: Path) -> DocumentMetadata:
        file_path = Path(file_path)
        try:
            with open(file_path, "rb") as f:
                psd = PSDImage.open(f)
                descendants = list(psd.descendants())
                groups = [layer for layer in descendants if layer.is_group()]

                metadata = DocumentMetadata(
                    filename=file_path.name,
                    file_size_bytes=file_path.stat().st_size,
                    sha256=self._sha256(file_path),
                    psd_version=self._map_psd_version(psd.version),
                    parser_version="1.0.0",
                    width_px=int(psd.width),
                    height_px=int(psd.height),
                    dpi_horizontal=self._dpi(psd, 0),
                    dpi_vertical=self._dpi(psd, 1),
                    color_mode=self._map_color_mode(psd.color_mode),
                    bit_depth=int(psd.depth),
                    icc_profile=self._icc_profile(psd),
                    total_layers=len(descendants),
                    total_groups=len(groups),
                    max_depth=max((self._depth_of(layer) for layer in descendants), default=0),
                    visible_layers=sum(1 for layer in descendants if layer.is_visible()),
                    hidden_layers=sum(1 for layer in descendants if not layer.is_visible()),
                    smart_objects=sum(1 for layer in descendants if layer.kind == "smartobject"),
                )
            return metadata

        except Exception as e:
            raise ParseError(f"Failed to parse PSD: {e}")

    def get_layers(self, file_path: Path) -> List[Dict[str, Any]]:
        try:
            with open(file_path, "rb") as f:
                psd = PSDImage.open(f)
                layers: List[Dict[str, Any]] = []
                self._collect_layers(
                    list(psd),
                    layers,
                    parent_id=None,
                    path_key="",
                    depth=0,
                    start_z=0,
                    dpi=self._dpi(psd, 0),
                )
            return layers
        except Exception as e:
            raise ParseError(f"Failed to extract layers: {e}")

    def get_artboards(self, file_path: Path) -> List[Artboard]:
        # psd-tools 1.x does not expose artboard records; report none rather than guess.
        return []

    def get_coordinate_spaces(self, file_path: Path) -> List[CoordinateSpace]:
        try:
            with open(file_path, "rb") as f:
                psd = PSDImage.open(f)
                return [
                    CoordinateSpace(
                        id="document",
                        type="document",
                        origin_x=0.0,
                        origin_y=0.0,
                        width_px=float(psd.width),
                        height_px=float(psd.height),
                        transform_matrix=[1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                    )
                ]
        except Exception as e:
            raise ParseError(f"Failed to extract coordinate spaces: {e}")

    # -- helpers ---------------------------------------------------------

    def _collect_layers(
        self,
        siblings: List[Any],
        out: List[Dict[str, Any]],
        parent_id: Optional[str],
        path_key: str,
        depth: int,
        start_z: int,
        dpi: float,
    ) -> int:
        """Depth-first collection preserving PSD stacking order.

        `path_key` is the deterministic fallback identity path used when a layer
        has no native Photoshop ID, so IDs stay stable across runs.

        Returns the next z-index counter.
        """
        z = start_z
        for index, layer in enumerate(siblings):
            child_key = f"{path_key}{index}" if not path_key else f"{path_key}-{index}"
            layer_id = self._layer_id(layer, child_key)
            out.append(
                self._to_raw_layer(layer, layer_id, parent_id, depth, z, dpi)
            )
            z += 1
            if layer.is_group():
                z = self._collect_layers(
                    list(layer),
                    out,
                    parent_id=layer_id,
                    path_key=child_key,
                    depth=depth + 1,
                    start_z=z,
                    dpi=dpi,
                )
        return z

    def _to_raw_layer(
        self,
        layer: Any,
        layer_id: str,
        parent_id: Optional[str],
        depth: int,
        z_index: int,
        dpi: float,
    ) -> Dict[str, Any]:
        left, top, right, bottom = layer.bbox
        layer_effects = []
        try:
            if layer.has_effects():
                layer_effects = list(layer.effects)
        except Exception:
            layer_effects = []

        typography = None
        typography_warnings: List[str] = []
        if layer.kind == "type":
            try:
                typography, typography_warnings = extract_typography(layer, dpi)
            except Exception as error:
                typography_warnings = [f"Typography extraction failed: {error}"]

        appearance, appearance_warnings, unsupported_effects = extract_appearance(layer)
        smart_object_link, smart_object_data = self._smart_object_metadata(layer)

        return {
            "id": layer_id,
            "source_layer_id": layer.layer_id if layer.layer_id and layer.layer_id > 0 else None,
            "name": layer.name,
            "kind": self.KIND_MAP.get(layer.kind, "pixel"),
            "parent_id": parent_id,
            "z_index": z_index,
            "depth": depth,
            "visible": layer.is_visible(),
            "locked": self._is_locked(layer),
            "opacity": layer.opacity / 255.0,
            "fill_opacity": getattr(layer, "fill_opacity", 255) / 255.0,
            "blend_mode": self._blend_mode_name(layer.blend_mode),
            "bounds": {
                "x": int(left),
                "y": int(top),
                "width": int(right - left),
                "height": int(bottom - top),
            },
            "has_mask": bool(layer.has_mask()),
            "has_vector_mask": bool(layer.has_vector_mask()),
            "mask_data": self._mask_metadata(layer),
            "vector_mask_data": self._vector_mask_metadata(layer),
            "clipping": bool(layer.clipping),
            "smart_object_link": smart_object_link,
            "smart_object_data": smart_object_data,
            "effects": [type(effect).__name__ for effect in layer_effects],
            "appearance": appearance,
            "appearance_warnings": appearance_warnings,
            "appearance_unsupported_effects": unsupported_effects,
            "typography": typography,
            "typography_warnings": typography_warnings,
            "sampled_colors": self._sample_colors(layer),
        }

    @staticmethod
    def _smart_object_metadata(layer: Any) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Read smart object metadata without extracting or decoding its contents."""
        if layer.kind != "smartobject":
            return None, None
        try:
            smart_object = layer.smart_object
        except Exception:
            return None, None

        data: Dict[str, Any] = {}
        accessors = (
            ("kind", lambda: smart_object.kind),
            ("filename", lambda: smart_object.filename),
            ("filetype", lambda: smart_object.filetype),
            ("filesize_bytes", lambda: int(smart_object.filesize)),
            ("unique_id", lambda: smart_object.unique_id),
            ("resolution_dpi", lambda: float(smart_object.resolution)),
            ("is_psd", lambda: bool(smart_object.is_psd())),
        )
        for key, getter in accessors:
            try:
                data[key] = getter()
            except Exception:
                continue
        try:
            box = smart_object.transform_box
            data["transform_box"] = [float(value) for value in box] if box else None
        except Exception:
            pass

        link = None
        if data.get("kind") == "data":
            try:
                data["embedded_sha256"] = hashlib.sha256(smart_object.data).hexdigest()
            except Exception:
                pass
        elif data.get("kind") in ("external", "alias"):
            link = PsdToolsAdapter._external_object_path(smart_object)

        if not data:
            return None, None
        data["contents_extracted"] = False
        return link, data

    @staticmethod
    def _external_object_path(smart_object: Any) -> Optional[str]:
        # psd-tools can open external objects but exposes no public link path.
        try:
            linked_file = smart_object._data.linked_file
            for key in (b"fullPath", b"relPath"):
                entry = linked_file.get(key) if hasattr(linked_file, "get") else linked_file[key]
                value = getattr(entry, "value", entry)
                if isinstance(value, bytes):
                    value = value.decode("utf-8", "replace")
                value = value.replace("\x00", "").strip()
                if value:
                    return value[7:] if value.startswith("file://") else value
        except Exception:
            pass
        try:
            return smart_object.filename or None
        except Exception:
            return None

    @staticmethod
    def _mask_metadata(layer: Any) -> Optional[Dict[str, Any]]:
        if not layer.has_mask():
            return None
        try:
            mask = layer.mask
            left, top, right, bottom = mask.bbox
            background = mask.background_color
            return {
                "bounds": {
                    "x": int(left),
                    "y": int(top),
                    "width": int(right - left),
                    "height": int(bottom - top),
                },
                "disabled": bool(mask.disabled),
                "inverted": bool(getattr(mask.flags, "invert_mask", False)),
                "background_color": int(background) if background is not None else None,
                "has_real": bool(mask.has_real()),
            }
        except Exception:
            return None

    @staticmethod
    def _vector_mask_metadata(layer: Any) -> Optional[Dict[str, Any]]:
        if not layer.has_vector_mask():
            return None
        try:
            mask = layer.vector_mask
            if mask is None:
                return None
            left, top, right, bottom = mask.bbox
            return {
                "normalized_bounds": {
                    "x": float(left),
                    "y": float(top),
                    "width": float(right - left),
                    "height": float(bottom - top),
                },
                "disabled": bool(mask.disabled),
                "inverted": bool(mask.inverted),
                "fill_rule": int(mask.initial_fill_rule),
                "path_count": len(mask.paths or []),
            }
        except Exception:
            return None

    @staticmethod
    def _layer_id(layer: Any, fallback_key: str) -> str:
        native_id = getattr(layer, "layer_id", None)
        if native_id and native_id > 0:
            return f"layer-{native_id}"
        return f"layer-path-{fallback_key}"

    @staticmethod
    def _is_locked(layer: Any) -> bool:
        try:
            lock = getattr(layer, "lock", False)
            return bool(lock) if lock is not None else False
        except Exception:
            return False

    @staticmethod
    def _depth_of(layer: Any) -> int:
        depth = 0
        parent = layer.parent
        while parent is not None and hasattr(parent, "parent"):
            parent = getattr(parent, "parent", None)
            if parent is None or parent is layer:
                break
            depth += 1
        return depth

    def _sample_colors(self, layer: Any, top_k: int = 3) -> List[Dict[str, Any]]:
        """Sample dominant colors from a raster layer.

        This is a statistical measurement (``pixel_measured``), never a native
        property. Disabled unless ``sample_colors`` is set in the config.
        """
        if not self.config.get("sample_colors"):
            return []
        if layer.kind != "pixel" or not layer.is_visible():
            return []

        try:
            left, top, right, bottom = layer.bbox
            if (right - left) * (bottom - top) > 4_000_000:
                return []
            image = layer.topil()
            if image is None:
                return []
            image = image.convert("RGBA")
            image.thumbnail((96, 96), Image.NEAREST)

            counts: Dict[Tuple[int, int, int], int] = {}
            total = 0
            for red, green, blue, alpha in image.getdata():
                if alpha < 128:
                    continue
                key = (red, green, blue)
                counts[key] = counts.get(key, 0) + 1
                total += 1
            if total == 0:
                return []

            top_colors = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:top_k]
            return [
                {
                    "color": f"#{red:02X}{green:02X}{blue:02X}",
                    "coverage": round(count / total, 3),
                    "sampleCount": count,
                }
                for (red, green, blue), count in top_colors
            ]
        except Exception:
            return []

    @staticmethod
    def _dpi(psd: PSDImage, index: int) -> float:
        try:
            info = psd.image_resources.get_data("resolution_info")
            if info is None:
                return 72.0
            value = (
                getattr(info, "horizontal_resolution")
                if index == 0
                else getattr(info, "vertical_resolution")
            )
            # FixedPoint values expose .value; plain floats pass through.
            value = getattr(value, "value", value)
            return float(value) or 72.0
        except Exception:
            return 72.0

    @staticmethod
    def _icc_profile(psd: PSDImage) -> Optional[str]:
        try:
            profile = psd.image_resources.get_data("icc_profile")
            return profile.name if profile is not None and hasattr(profile, "name") else None
        except Exception:
            return None

    @staticmethod
    def _sha256(file_path: Path) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _blend_mode_name(mode: Any) -> str:
        name = getattr(mode, "name", None)
        if name:
            return name.lower().replace("_", " ")
        return "normal"

    def _map_psd_version(self, version: int) -> PSDVersion:
        return {1: PSDVersion.PSD, 2: PSDVersion.PSB}.get(version, PSDVersion.Unknown)

    def _map_color_mode(self, mode: Any) -> ColorMode:
        name = getattr(mode, "name", None)
        if name is None:
            return ColorMode.Unknown
        return self.COLOR_MODE_MAP.get(name, ColorMode.Unknown)
