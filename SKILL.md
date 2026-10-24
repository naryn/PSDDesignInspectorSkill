---
name: psd-design-inspector
description: >
  Analyze Photoshop PSD/PSB files and extract layers,
  typography, colors, effects, geometry, spatial
  relationships, design tokens and assets.
---

# PSD Design Inspector

## When to use

- PSD design specification extraction
- Layer and style inspection  
- Typography, colors, spacing, borders, geometry analysis
- Design IR conversion for Vue/HTML reconstruction
- Asset extraction from layered designs
- Preparation for design system tokenization

## Workflow

1. Verify input PSD/PSB file validity
2. Run preflight inspection
3. Select appropriate extraction profile (fast/full/deep)
4. Execute deterministic PSD parsing with psd-tools
5. Identify missing or unsupported properties
6. Compute geometric relationships and spatial graphs
7. Build complete Design IR with provenance tracking
8. Export assets and generate visual annotations
9. Report unresolved properties and diagnostic warnings

## Rules

- Never overwrite the original PSD file
- Never invent or guess missing design attributes
- Keep original layer tree separate from inferred semantic components
- Prefer precise native extraction over AI model guesses
- Record source and confidence for every extracted property
- Support offline-first operation without external API dependencies
- Maintain backward compatible JSON schema versioning
- Fail gracefully on partial errors without losing complete results

## Configuration

### Extraction Profiles

- `fast`: Native properties only, minimal computation
- `full`: All properties, geometry, tokens, assets (recommended)
- `deep`: Reserved; currently equivalent to `full` apart from a diagnostic warning
  (no extra pixel measurements yet)

### Output Structure

```
output/
├── design.json              # Main Design IR data
├── source-layers.json       # Original layer tree projection
├── geometry.json            # Measured relationships, spacing, layout candidates
├── design-tokens.json       # Color/typography/spacing/border/shadow candidates
├── previews/
│   ├── original.png         # psd-tools composite preview
│   └── annotated.png        # Bounds, IDs and measured gaps
├── viewer.html              # Standalone HTML checker (preview + data embedded)
├── assets/                  # --export-assets: layer PNGs + asset-index.json
├── reports/
│   ├── extraction-summary.json  # Always written
│   ├── unsupported.md           # --report
│   ├── layer-inventory.md       # --report
│   ├── design-spec.md           # --report
│   └── validation.json          # --report
├── components.json          # Semantic component tree (P3, not implemented)
└── manifest.json            # Execution metadata, hashes, validation status
```

`fast` profile outputs only `design.json`, `source-layers.json`,
`reports/extraction-summary.json` and `manifest.json`. Asset and detailed report
output requires `--export-assets` and `--report` respectively.

## Constraints

- Supports PSD and PSB formats only
- Requires Python 3.9+ with psd-tools, Pillow, Pydantic and jsonschema
- Offline processing by default, no cloud dependencies
- Smart object contents are not extracted; such layers are marked
  `smart_object_contents` in `extraction.unsupported_properties`
- Handles corrupted or incomplete PSDs gracefully
- PSD files are processed in memory; streaming and caching are not implemented

## Error Handling

- Invalid PSD structure: return detailed error with validation info
- Missing fonts: preserve original names; local font availability is not checked,
  so `font.missing` stays false
- Rasterized text: report OCR capabilities if enabled
- Corrupted layers: skip individual layers, continue processing others
- Unsupported features: document in `diagnostics.unsupportedFeatures` and
  per-layer `extraction.unsupported_properties`

## Integration Points

This skill integrates with:
- **PSD Normalize Studio**: For preprocessing and normalization
- **Vue Generation Skill**: For HTML/CSS reconstruction
- **Design Token System**: For unified design language management

## Examples

```bash
# Standard full analysis (geometry + tokens + previews + viewer)
psd-inspector inspect \
  --input ./designs/home.psd \
  --output ./output/home \
  --profile full

# Full analysis plus per-layer PNG assets and detailed reports
psd-inspector inspect \
  --input ./designs/home.psd \
  --output ./output/home \
  --profile full \
  --export-assets \
  --report

# Minimal fast check
psd-inspector inspect \
  --input ./designs/sketch.psb \
  --output ./output/sketch \
  --profile fast

# Inspect one layer
psd-inspector layer get --ir ./output/home/design.json --id layer-1038

# Query measured neighbors and gaps
psd-inspector geometry neighbors \
  --ir ./output/home/design.json --id layer-1038 --distance 100

# Re-extract selected token types
psd-inspector tokens extract \
  --ir ./output/home/design.json --types colors,spacing

# Re-render an annotated preview
psd-inspector annotate \
  --ir ./output/home/design.json \
  --show bounds,ids,spacing \
  --output ./output/home/annotated.png
```

## Interpreting Results

- `geometry.json` contains measurements (`alignment_group`, `spacing_group`,
  `group_padding`, `sampled_color`) and inferred `layoutHypotheses`.
- Every hypothesis carries `evidence`, `confidence`, and `basis: measured_geometry`.
  Do not present layout candidates as native PSD values.
- `sourceBounds` is the authoritative geometry. `visibleBounds` currently mirrors it;
  pixel-level visible/effect bounds are planned for P3.
- `geometry neighbors` compares only visible leaf layers that share the target's
  parent; `--id` accepts `layer-<n>` or a bare native id `<n>`.
- Text layers carry native `characterRuns` and `paragraphRuns`; point sizes are kept
  with a DPI conversion basis for `effective_font_size_px`.
- Shape fills come from `vscg`, stroke colors from `vstk`. Effects that the IR cannot
  represent (e.g. BevelEmboss/Satin) are listed in `extraction.unsupported_properties`.
- Token names are candidates and require human review. Sampled colors are statistical.
- `viewer.html` is fully standalone: preview and IR subset are embedded.
- `assets/layer-previews/` contains psd-tools raster renderings, not SVG or native
  vector exports. Assets are deduplicated by PNG hash; `asset-index.json` records
  `duplicatedFrom`, bounds, document offset, mask flags and visibility. Asset and
  preview PNGs are saved without ICC metadata so hashes are reproducible across runs.
- `reports/extraction-summary.json` is always produced. Treat schema validation
  failures in `manifest.validation` as real defects, not warnings to hide.
- `diagnostics.unsupportedFeatures` lists parser-level gaps;
  `extraction.unsupported_properties` lists per-layer unsupported properties.

## Version Compatibility

- Schema version: `1.0.0`
- Parser version tracking in manifest.json
- Backward migration path for older IR versions
