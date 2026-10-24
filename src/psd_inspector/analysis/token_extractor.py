"""Design token extraction from Design IR.

Token names are *candidates*. Frequency is evidence, not proof of brand
intent, so every generated name carries a review note.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import math

from ..models.token import DesignToken, TokenValue


def _normalize_hex(value: Optional[str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().lstrip("#").upper()
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) == 8 and text.startswith("FF"):
        text = text[2:]
    if len(text) not in (6, 8):
        return None
    return f"#{text}"


def _rgb(hex_color: str) -> Tuple[int, int, int]:
    text = hex_color.lstrip("#")
    if len(text) == 8:
        text = text[2:]
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _luminance(rgb: Tuple[int, int, int]) -> float:
    r, g, b = (channel / 255 for channel in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _saturation(rgb: Tuple[int, int, int]) -> float:
    high, low = max(rgb), min(rgb)
    return (high - low) / high if high else 0.0


def _cluster(values: Sequence[float], tolerance: float) -> List[List[float]]:
    clusters: List[List[float]] = []
    for value in sorted(values):
        if clusters and abs(value - clusters[-1][0]) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return clusters


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


class TokenExtractor:
    """Aggregate color / typography / spacing / border / shadow token candidates."""

    def __init__(self, tolerance_px: float = 2.0, min_sampled_coverage: float = 0.5):
        self.tolerance_px = tolerance_px
        self.min_sampled_coverage = min_sampled_coverage

    def extract(
        self,
        design_ir: Dict[str, Any],
        types: Iterable[str] = ("colors", "typography", "spacing", "borders", "shadows"),
    ) -> Dict[str, Any]:
        requested = set(types)
        layers = design_ir.get("source", {}).get("rawLayers", [])
        measurements = design_ir.get("analysis", {}).get("measurements", [])

        color_tokens = self._color_tokens(layers, measurements) if "colors" in requested else []
        typography_tokens = self._typography_tokens(layers) if "typography" in requested else []
        spacing_tokens = self._spacing_tokens(layers, measurements) if "spacing" in requested else []
        border_tokens = self._border_tokens(layers) if "borders" in requested else []
        shadow_tokens = self._shadow_tokens(layers) if "shadows" in requested else []

        all_tokens = color_tokens + typography_tokens + spacing_tokens + border_tokens + shadow_tokens
        return {
            "colorTokens": color_tokens,
            "typographyTokens": typography_tokens,
            "spacingTokens": spacing_tokens,
            "borderTokens": border_tokens,
            "shadowTokens": shadow_tokens,
            "componentPatterns": [],
            "recommendedCount": sum(1 for token in all_tokens if token.get("is_recommended")),
            "totalCount": len(all_tokens),
        }

    # -- colors ----------------------------------------------------------

    def _color_tokens(
        self,
        layers: Sequence[Dict[str, Any]],
        measurements: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        aggregated: Dict[str, Dict[str, Any]] = {}

        def add(color: Optional[str], layer_id: str, origin: str, weight: float = 1.0) -> None:
            normalized = _normalize_hex(color)
            if normalized is None:
                return
            entry = aggregated.setdefault(
                normalized,
                {"count": 0, "coverage": 0.0, "layer_ids": set(), "origins": set()},
            )
            entry["count"] += 1
            entry["coverage"] += weight
            entry["layer_ids"].add(layer_id)
            entry["origins"].add(origin)

        for layer in layers:
            appearance = layer.get("appearance", {})
            for fill in appearance.get("fills", []):
                if not fill.get("visible", True):
                    continue
                solid = fill.get("solid_color") or fill.get("color")
                if solid:
                    add(solid, layer["id"], "native_fill")
                for stop in fill.get("gradient_stops") or []:
                    add(stop.get("color"), layer["id"], "native_gradient")
            for stroke in appearance.get("strokes", []):
                if stroke.get("visible", True):
                    add(stroke.get("color"), layer["id"], "native_stroke")
            gradient_overlay = appearance.get("gradient_overlay") or {}
            if gradient_overlay.get("enabled", True):
                for stop in gradient_overlay.get("gradient_stops") or []:
                    add(stop.get("color"), layer["id"], "native_gradient")

            typography = layer.get("typography") or {}
            for run in typography.get("character_runs") or []:
                if float(run.get("opacity", 1.0)) <= 0.05:
                    continue
                add(run.get("color"), layer["id"], "native_text")

        for measurement in measurements:
            if measurement.get("type") != "sampled_color":
                continue
            coverage = float(measurement.get("coverage", 0.0))
            if coverage < self.min_sampled_coverage:
                continue
            add(measurement.get("color"), measurement.get("layerId", ""), "pixel_measured", coverage)

        ranked = sorted(
            aggregated.items(),
            key=lambda item: (item[1]["count"], item[1]["coverage"]),
            reverse=True,
        )[:24]

        used_names: set = set()
        primary_done = text_done = background_done = False
        tokens: List[Dict[str, Any]] = []
        for index, (hex_color, stats) in enumerate(ranked):
            rgb = _rgb(hex_color)
            lum, sat = _luminance(rgb), _saturation(rgb)
            if not primary_done and sat >= 0.25 and 0.2 <= lum <= 0.85:
                name, category, primary_done = "primary", "brand", True
            elif not text_done and lum <= 0.35 and sat <= 0.2:
                name, category, text_done = "textPrimary", "text", True
            elif not background_done and lum >= 0.9:
                name, category, background_done = "backgroundPrimary", "background", True
            else:
                name, category = f"color{index + 1}", "custom"

            if name in used_names:
                name = f"{name}{index + 1}"
            used_names.add(name)

            notes = ["Candidate name, requires human review."]
            if "native_text" in stats["origins"]:
                notes.append("Color read from native text run styling.")
            if "native_gradient" in stats["origins"]:
                notes.append("Color read from a native gradient stop.")
            if "pixel_measured" in stats["origins"]:
                notes.append("Color measured from raster pixels; statistical, not native.")

            tokens.append(
                DesignToken(
                    id=f"token-color-{hex_color.lstrip('#').lower()}",
                    name=name,
                    type="color",
                    category=category,
                    value=TokenValue(base=hex_color, hex=hex_color, variants={}),
                    description=f"Aggregated from {stats['count']} appearance occurrence(s).",
                    usage_count=stats["count"],
                    source_layer_ids=sorted(stats["layer_ids"]),
                    is_recommended=stats["count"] >= 2 or stats["coverage"] >= 0.75,
                    notes=notes,
                ).model_dump(mode="json")
            )
        return tokens

    # -- typography ------------------------------------------------------

    def _typography_tokens(self, layers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        families: Dict[str, int] = {}
        sizes: Dict[float, int] = {}
        weights: Dict[str, int] = {}
        layer_ids: Dict[str, set] = {"family": set(), "size": set(), "weight": set()}

        for layer in layers:
            typography = layer.get("typography")
            if not typography:
                continue
            for run in typography.get("character_runs", []):
                family = run.get("font", {}).get("family")
                if family:
                    families[family] = families.get(family, 0) + 1
                    layer_ids["family"].add(layer["id"])
                size = run.get("effective_font_size_px")
                if isinstance(size, (int, float)):
                    sizes[float(size)] = sizes.get(float(size), 0) + 1
                    layer_ids["size"].add(layer["id"])
                weight = run.get("font", {}).get("weight")
                if weight:
                    weights[str(weight)] = weights.get(str(weight), 0) + 1
                    layer_ids["weight"].add(layer["id"])

        tokens: List[Dict[str, Any]] = []
        for family, count in sorted(families.items(), key=lambda item: item[1], reverse=True):
            tokens.append(
                self._token(
                    token_id=f"token-font-family-{family.lower().replace(' ', '-')}",
                    name="fontFamily",
                    type_="typography",
                    base=family,
                    usage_count=count,
                    layer_ids=sorted(layer_ids["family"]),
                    description="Most frequent font family in native text layers.",
                )
            )
        for size, count in sorted(sizes.items(), key=lambda item: (-item[1], item[0])):
            tokens.append(
                self._token(
                    token_id=f"token-font-size-{_number(size)}",
                    name=f"fontSize-{_number(size)}",
                    type_="typography",
                    base=_number(size),
                    usage_count=count,
                    layer_ids=sorted(layer_ids["size"]),
                    description="Font size candidate in pixels.",
                )
            )
        for weight, count in sorted(weights.items(), key=lambda item: item[1], reverse=True):
            tokens.append(
                self._token(
                    token_id=f"token-font-weight-{weight}",
                    name=f"fontWeight-{weight}",
                    type_="typography",
                    base=weight,
                    usage_count=count,
                    layer_ids=sorted(layer_ids["weight"]),
                    description="Font weight candidate from native text runs.",
                )
            )
        return tokens

    # -- spacing ---------------------------------------------------------

    def _spacing_tokens(
        self,
        layers: Sequence[Dict[str, Any]],
        measurements: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        values: List[float] = []
        layer_ids_by_value: Dict[float, set] = {}

        for measurement in measurements:
            if measurement.get("type") == "spacing_group":
                gap = measurement.get("gap_px")
                if isinstance(gap, (int, float)) and gap > 0:
                    values.append(round(float(gap), 2))
                    layer_ids_by_value.setdefault(round(float(gap), 2), set()).update(
                        measurement.get("layer_ids", [])
                    )
            elif measurement.get("type") == "group_padding":
                for padding in measurement.get("padding", {}).values():
                    if isinstance(padding, (int, float)) and padding > 0:
                        rounded = round(float(padding), 2)
                        values.append(rounded)
                        layer_ids_by_value.setdefault(rounded, set()).add(measurement.get("groupId", ""))

        tokens: List[Dict[str, Any]] = []
        for cluster in _cluster(values, self.tolerance_px):
            if not cluster:
                continue
            value = round(sum(cluster) / len(cluster), 2)
            layer_ids = set()
            for raw_value in cluster:
                layer_ids.update(layer_ids_by_value.get(raw_value, set()))
            tokens.append(
                self._token(
                    token_id=f"token-spacing-{_number(value)}",
                    name=f"space-{_number(value)}",
                    type_="spacing",
                    base=_number(value),
                    usage_count=len(cluster),
                    layer_ids=sorted(layer_ids),
                    description="Spacing candidate measured from gaps and group padding.",
                )
            )
        return tokens

    # -- borders ---------------------------------------------------------

    def _border_tokens(self, layers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        radius_counts: Dict[float, int] = {}
        width_counts: Dict[float, int] = {}
        radius_layers: Dict[float, set] = {}
        width_layers: Dict[float, set] = {}

        for layer in layers:
            appearance = layer.get("appearance", {})
            radius = appearance.get("border_radius") or {}
            for corner in ("top_left", "top_right", "bottom_right", "bottom_left"):
                value = radius.get(corner)
                if isinstance(value, (int, float)) and value > 0:
                    rounded = round(float(value), 2)
                    radius_counts[rounded] = radius_counts.get(rounded, 0) + 1
                    radius_layers.setdefault(rounded, set()).add(layer["id"])
            for stroke in appearance.get("strokes", []):
                width = stroke.get("width_px")
                if isinstance(width, (int, float)) and width > 0:
                    rounded = round(float(width), 2)
                    width_counts[rounded] = width_counts.get(rounded, 0) + 1
                    width_layers.setdefault(rounded, set()).add(layer["id"])

        tokens: List[Dict[str, Any]] = []
        for value, count in sorted(radius_counts.items()):
            tokens.append(
                self._token(
                    token_id=f"token-radius-{_number(value)}",
                    name=f"radius-{_number(value)}",
                    type_="border",
                    base=_number(value),
                    usage_count=count,
                    layer_ids=sorted(radius_layers[value]),
                    description="Border radius candidate in pixels.",
                )
            )
        for value, count in sorted(width_counts.items()):
            tokens.append(
                self._token(
                    token_id=f"token-border-width-{_number(value)}",
                    name=f"borderWidth-{_number(value)}",
                    type_="border",
                    base=_number(value),
                    usage_count=count,
                    layer_ids=sorted(width_layers[value]),
                    description="Stroke width candidate in pixels.",
                )
            )
        return tokens

    # -- shadows ---------------------------------------------------------

    def _shadow_tokens(self, layers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        counts: Dict[str, int] = {}
        layer_ids: Dict[str, set] = {}
        for layer in layers:
            appearance = layer.get("appearance", {})
            for key in ("drop_shadow", "inner_shadow"):
                shadow = appearance.get(key)
                if not shadow or shadow.get("enabled", True) is False:
                    continue
                distance = float(shadow.get("distance_px", 0.0))
                angle = math.radians(float(shadow.get("angle_deg", 90.0)))
                offset_x = round(distance * math.cos(angle), 2)
                offset_y = round(-distance * math.sin(angle), 2)
                css = (
                    f"{_number(offset_x)}px {_number(offset_y)}px "
                    f"{_number(float(shadow.get('size_px', 0.0)))}px "
                    f"{_number(float(shadow.get('spread_px', 0.0)))}px "
                    f"{shadow.get('color', '#000000')}"
                )
                counts[css] = counts.get(css, 0) + 1
                layer_ids.setdefault(css, set()).add(layer["id"])

        tokens: List[Dict[str, Any]] = []
        for index, (css, count) in enumerate(
            sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ):
            tokens.append(
                self._token(
                    token_id=f"token-shadow-{index + 1}",
                    name=f"shadow-{index + 1}",
                    type_="shadow",
                    base=css,
                    usage_count=count,
                    layer_ids=sorted(layer_ids[css]),
                    description="Box-shadow candidate derived from native layer effects.",
                )
            )
        return tokens

    # -- shared ----------------------------------------------------------

    def _token(
        self,
        token_id: str,
        name: str,
        type_: str,
        base: str,
        usage_count: int,
        layer_ids: List[str],
        description: str,
    ) -> Dict[str, Any]:
        return DesignToken(
            id=token_id,
            name=name,
            type=type_,
            category="global" if type_ != "color" else "custom",
            value=TokenValue(base=base, variants={}),
            description=description,
            usage_count=usage_count,
            source_layer_ids=layer_ids,
            is_recommended=usage_count >= 2,
            notes=["Candidate token name, requires human review."],
        ).model_dump(mode="json")
