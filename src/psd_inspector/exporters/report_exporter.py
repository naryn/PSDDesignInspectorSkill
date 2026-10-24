"""Extraction reports.

``extraction-summary.json`` is written on every run. The ``--report`` flag
also enables the human-readable markdown reports and ``validation.json``.
All report values are projections of the Design IR; nothing is inferred.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

TOKEN_GROUPS = (
    ("colorTokens", "color"),
    ("typographyTokens", "typography"),
    ("spacingTokens", "spacing"),
    ("borderTokens", "border"),
    ("shadowTokens", "shadow"),
)

EFFECT_FIELDS = (
    "drop_shadow",
    "inner_shadow",
    "outer_glow",
    "inner_glow",
    "color_overlay",
    "gradient_overlay",
    "pattern_overlay",
)


def write_reports(
    output_dir: Path,
    ir: Dict[str, Any],
    manifest: Dict[str, Any],
    assets: Optional[Dict[str, Any]] = None,
    validation: Optional[Dict[str, Any]] = None,
    detailed: bool = False,
) -> List[str]:
    """Write ``reports/`` and return the written relative file paths."""
    reports_dir = Path(output_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary = build_extraction_summary(ir, manifest, assets, validation)
    written = ["reports/extraction-summary.json"]
    _write_json(reports_dir / "extraction-summary.json", summary)

    if not detailed:
        return written

    _write_text(reports_dir / "unsupported.md", _unsupported_markdown(ir, summary))
    written.append("reports/unsupported.md")

    _write_text(reports_dir / "layer-inventory.md", _layer_inventory_markdown(ir))
    written.append("reports/layer-inventory.md")

    _write_text(reports_dir / "design-spec.md", _design_spec_markdown(ir, summary))
    written.append("reports/design-spec.md")

    validation_payload = validation or {
        "status": "unavailable",
        "schemaPath": None,
        "errors": [],
        "warning": "No validation report was produced.",
    }
    _write_json(reports_dir / "validation.json", validation_payload)
    written.append("reports/validation.json")
    return written


def build_extraction_summary(
    ir: Dict[str, Any],
    manifest: Dict[str, Any],
    assets: Optional[Dict[str, Any]] = None,
    validation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    layers = ir.get("source", {}).get("rawLayers", [])
    metadata = ir.get("document", {}).get("metadata", {})
    analysis = ir.get("analysis", {})
    design_system = ir.get("designSystem", {})
    diagnostics = ir.get("diagnostics", {})

    by_kind = Counter(layer.get("kind", "unknown") for layer in layers)
    by_status = Counter(
        (layer.get("extraction") or {}).get("status", "unknown") for layer in layers
    )
    with_typography = [layer for layer in layers if layer.get("typography")]
    with_fills = [layer for layer in layers if _appearance(layer).get("fills")]
    with_strokes = [layer for layer in layers if _appearance(layer).get("strokes")]
    with_effects = [
        layer for layer in layers if any(_appearance(layer).get(field) for field in EFFECT_FIELDS)
    ]

    font_families: Counter = Counter()
    font_sizes: Counter = Counter()
    character_runs = 0
    paragraph_runs = 0
    text_effects: Counter = Counter()
    for layer in with_typography:
        typography = layer["typography"]
        runs = typography.get("character_runs") or []
        character_runs += len(runs)
        paragraph_runs += len(typography.get("paragraph_runs") or [])
        for run in runs:
            family = (run.get("font") or {}).get("family")
            if family:
                font_families[family] += 1
            size = run.get("effective_font_size_px")
            if size is not None:
                font_sizes[_number_label(size)] += 1
        for effect in typography.get("effects") or []:
            text_effects[effect] += 1

    token_counts = {
        token_type: len(design_system.get(key) or [])
        for key, token_type in TOKEN_GROUPS
    }
    layout_types = Counter(
        hypothesis.get("layout_type", "unknown")
        for hypothesis in analysis.get("layoutHypotheses") or []
    )

    unsupported = _unsupported_summary(ir)
    warnings = list(diagnostics.get("warnings") or [])

    return {
        "schemaVersion": ir.get("schemaVersion"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputFile": manifest.get("inputFile", {}),
        "profile": (manifest.get("parser") or {}).get("profile"),
        "document": {
            "filename": metadata.get("filename"),
            "widthPx": metadata.get("width_px"),
            "heightPx": metadata.get("height_px"),
            "colorMode": metadata.get("color_mode"),
            "bitDepth": metadata.get("bit_depth"),
            "dpi": [metadata.get("dpi_horizontal"), metadata.get("dpi_vertical")],
            "totalLayers": metadata.get("total_layers", len(layers)),
            "totalGroups": metadata.get("total_groups"),
            "smartObjects": metadata.get("smart_objects"),
        },
        "layers": {
            "total": len(layers),
            "visible": sum(1 for layer in layers if layer.get("visible")),
            "hidden": sum(1 for layer in layers if not layer.get("visible")),
            "withTypography": len(with_typography),
            "withFills": len(with_fills),
            "withStrokes": len(with_strokes),
            "withEffects": len(with_effects),
            "byKind": dict(sorted(by_kind.items())),
            "extractionStatus": dict(sorted(by_status.items())),
        },
        "typography": {
            "textLayers": len(with_typography),
            "characterRuns": character_runs,
            "paragraphRuns": paragraph_runs,
            "fontFamilies": dict(font_families.most_common()),
            "fontSizesPx": dict(font_sizes.most_common()),
            "effects": dict(text_effects.most_common()),
        },
        "geometry": {
            "measurements": len(analysis.get("measurements") or []),
            "spatialRelationships": len(analysis.get("spatialRelationships") or []),
            "layoutHypotheses": len(analysis.get("layoutHypotheses") or []),
            "layoutTypes": dict(sorted(layout_types.items())),
            "basis": "measured_geometry",
        },
        "designTokens": {
            "byType": token_counts,
            "total": design_system.get("totalCount", sum(token_counts.values())),
            "recommended": design_system.get("recommendedCount", 0),
        },
        "unsupported": unsupported,
        "diagnostics": {
            "warningCount": len(warnings),
            "warnings": warnings,
        },
        "assets": (
            {
                "enabled": True,
                **(assets.get("summary") or {}),
            }
            if assets is not None
            else {"enabled": False}
        ),
        "validation": _validation_summary(validation),
    }


def _validation_summary(validation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if validation is None:
        return {"status": "unavailable", "errorCount": 0}
    return {
        "status": validation.get("status"),
        "schemaPath": validation.get("schemaPath"),
        "errorCount": len(validation.get("errors") or []),
        "warning": validation.get("warning"),
    }


def _unsupported_summary(ir: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = ir.get("diagnostics", {})
    per_feature: Dict[str, List[str]] = defaultdict(list)
    for layer in ir.get("source", {}).get("rawLayers", []):
        for feature in (layer.get("extraction") or {}).get("unsupported_properties") or []:
            per_feature[feature].append(layer.get("id"))

    return {
        "documentFeatures": list(diagnostics.get("unsupportedFeatures") or []),
        "layerProperties": [
            {
                "feature": feature,
                "layerCount": len(layer_ids),
                "exampleLayerIds": sorted(layer_ids)[:10],
            }
            for feature, layer_ids in sorted(
                per_feature.items(), key=lambda item: (-len(item[1]), item[0])
            )
        ],
    }


def _unsupported_markdown(ir: Dict[str, Any], summary: Dict[str, Any]) -> str:
    unsupported = summary["unsupported"]
    lines = ["# Unsupported features", ""]
    document_features = unsupported["documentFeatures"]
    if document_features:
        lines.append("## Parser-level limitations")
        lines.append("")
        for feature in document_features:
            lines.append(f"- `{feature}`")
        lines.append("")

    layer_properties = unsupported["layerProperties"]
    if layer_properties:
        lines.append("## Layer-level properties")
        lines.append("")
        lines.append("| Feature | Layers | Example layer IDs |")
        lines.append("| --- | --- | --- |")
        for item in layer_properties:
            examples = ", ".join(f"`{layer_id}`" for layer_id in item["exampleLayerIds"])
            lines.append(
                f"| `{item['feature']}` | {item['layerCount']} | {examples} |"
            )
        lines.append("")

    if not document_features and not layer_properties:
        lines.append("No unsupported features were reported.")
        lines.append("")

    warnings = summary["diagnostics"]["warnings"]
    if warnings:
        lines.append("## Diagnostics warnings")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {_md(warning)}")
        lines.append("")

    lines.extend([
        "## Raster fallback",
        "",
        "Run `psd-inspector inspect --export-assets` to render per-layer PNG",
        "fallbacks for features that cannot be represented natively.",
        "",
    ])
    return "\n".join(lines)


def _layer_inventory_markdown(ir: Dict[str, Any]) -> str:
    layers = ir.get("source", {}).get("rawLayers", [])
    metadata = ir.get("document", {}).get("metadata", {})
    lines = [
        f"# Layer inventory: {metadata.get('filename', 'document')}",
        "",
        f"{len(layers)} layers, {metadata.get('width_px')}x{metadata.get('height_px')} px.",
        "",
        "| ID | Name | Kind | Parent | Bounds (x, y, w, h) | Visible | Extraction | Unsupported |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for layer in layers:
        bounds = (layer.get("geometry") or {}).get("source_bounds") or {}
        extraction = layer.get("extraction") or {}
        unsupported = ", ".join(extraction.get("unsupported_properties") or [])
        lines.append(
            "| `{id}` | {name} | {kind} | {parent} | {x}, {y}, {w}, {h} | {visible} | {status} | {unsupported} |".format(
                id=layer.get("id"),
                name=_md(layer.get("name", "")),
                kind=layer.get("kind"),
                parent=f"`{layer['parent_id']}`" if layer.get("parent_id") else "",
                x=bounds.get("x"),
                y=bounds.get("y"),
                w=bounds.get("width"),
                h=bounds.get("height"),
                visible="yes" if layer.get("visible") else "no",
                status=extraction.get("status", "unknown"),
                unsupported=_md(unsupported),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _design_spec_markdown(ir: Dict[str, Any], summary: Dict[str, Any]) -> str:
    document = summary["document"]
    design_system = ir.get("designSystem", {})
    lines = [
        f"# Design specification: {document.get('filename', 'document')}",
        "",
        f"- Canvas: {document.get('widthPx')} x {document.get('heightPx')} px",
        f"- Color mode: {document.get('colorMode')}, bit depth: {document.get('bitDepth')}",
        f"- Layers: {summary['layers']['total']} ({summary['layers']['visible']} visible)",
        f"- Profile: {summary.get('profile')}",
        "",
        "All geometry below is measured from native layer bounds. Layout proposals",
        "and token names are candidates and require human review.",
        "",
        "## Color tokens",
        "",
    ]
    lines.extend(_token_table(design_system.get("colorTokens")))
    lines.extend([
        "",
        "## Typography",
        "",
        "### Font families",
        "",
    ])
    lines.extend(_counter_table(summary["typography"]["fontFamilies"], "Family"))
    lines.extend(["", "### Font sizes (px)", ""])
    lines.extend(_counter_table(summary["typography"]["fontSizesPx"], "Size"))
    lines.extend(["", "### Typography tokens", ""])
    lines.extend(_token_table(design_system.get("typographyTokens")))
    lines.extend(["", "## Spacing tokens", ""])
    lines.extend(_token_table(design_system.get("spacingTokens")))
    lines.extend(["", "## Border tokens", ""])
    lines.extend(_token_table(design_system.get("borderTokens")))
    lines.extend(["", "## Shadow tokens", ""])
    lines.extend(_token_table(design_system.get("shadowTokens")))

    hypotheses = ir.get("analysis", {}).get("layoutHypotheses") or []
    ranked = sorted(
        hypotheses,
        key=lambda item: item.get("confidence", 0.0),
        reverse=True,
    )[:20]
    lines.extend([
        "",
        "## Layout candidates",
        "",
        f"{len(hypotheses)} candidates were derived from measured geometry.",
        "Only the 20 highest-confidence candidates are listed.",
        "",
    ])
    if ranked:
        lines.append("| Type | Confidence | Layers | CSS recommendation |")
        lines.append("| --- | --- | --- | --- |")
        for hypothesis in ranked:
            layer_ids = ", ".join(
                f"`{layer_id}`" for layer_id in hypothesis.get("layers_involved") or []
            )
            lines.append(
                f"| {hypothesis.get('layout_type')} | {hypothesis.get('confidence')} | "
                f"{layer_ids} | {_md(hypothesis.get('css_recommendation') or '')} |"
            )
    else:
        lines.append("No layout candidates were produced.")

    lines.extend([
        "",
        "## Caveats",
        "",
        "- Layout candidates are inferred, not native Photoshop values.",
        "- Token names are suggestions; usage counts do not imply brand priority.",
        "- `visibleBounds` currently mirrors native `sourceBounds`.",
        "",
    ])
    return "\n".join(lines)


def _token_table(tokens: Optional[List[Dict[str, Any]]]) -> List[str]:
    if not tokens:
        return ["_No tokens._"]
    lines = ["| Name | Value | Usage | Recommended |", "| --- | --- | --- | --- |"]
    for token in tokens:
        value = (token.get("value") or {}).get("base", "")
        lines.append(
            f"| {_md(token.get('name', ''))} | `{_md(value)}` | "
            f"{token.get('usage_count', 0)} | {'yes' if token.get('is_recommended') else 'no'} |"
        )
    return lines


def _counter_table(counter: Dict[str, int], label: str) -> List[str]:
    if not counter:
        return ["_None._"]
    lines = [f"| {label} | Occurrences |", "| --- | --- |"]
    for key, count in counter.items():
        lines.append(f"| {_md(str(key))} | {count} |")
    return lines


def _appearance(layer: Dict[str, Any]) -> Dict[str, Any]:
    return layer.get("appearance") or {}


def _number_label(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
