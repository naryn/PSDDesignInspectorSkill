"""Unit tests for AI-assisted naming pack and merge."""

import json

import pytest
from PIL import Image

from psd_inspector.naming import (
    NamingError,
    apply_names,
    build_naming_pack,
    ir_sha256_for,
    render_naming_visuals,
)


def _make_ir():
    return {
        "document": {
            "metadata": {
                "filename": "sample.psd",
                "width_px": 100,
                "height_px": 80,
            }
        },
        "source": {
            "rawLayers": [
                {
                    "id": "layer-10",
                    "source_layer_id": 10,
                    "name": "Group 1",
                    "kind": "group",
                    "parent_id": None,
                    "depth": 0,
                    "z_index": 1,
                    "visible": True,
                    "geometry": {
                        "source_bounds": {"x": 0, "y": 0, "width": 100, "height": 80}
                    },
                },
                {
                    "id": "layer-11",
                    "source_layer_id": 11,
                    "name": "Title",
                    "kind": "text",
                    "parent_id": "layer-10",
                    "depth": 1,
                    "z_index": 2,
                    "visible": True,
                    "geometry": {
                        "source_bounds": {"x": 4, "y": 4, "width": 60, "height": 20}
                    },
                    "typography": {
                        "content": "Hello world",
                        "dominant_font_family": "Inter",
                        "dominant_font_size_px": 24,
                    },
                    "appearance": {
                        "fills": [{"solid_color": "#111111"}],
                        "border_radius": {
                            "top_left": 0,
                            "top_right": 0,
                            "bottom_right": 0,
                            "bottom_left": 0,
                        },
                    },
                    "export_paths": [],
                },
                {
                    "id": "layer-12",
                    "source_layer_id": 12,
                    "name": "Rectangle 1",
                    "kind": "shape",
                    "parent_id": "layer-10",
                    "depth": 1,
                    "z_index": 3,
                    "visible": True,
                    "geometry": {
                        "source_bounds": {"x": 10, "y": 40, "width": 20, "height": 20}
                    },
                    "appearance": {
                        "fills": [{"solid_color": "#ff0000"}],
                        "border_radius": {
                            "top_left": 4,
                            "top_right": 4,
                            "bottom_right": 4,
                            "bottom_left": 4,
                        },
                    },
                    "export_paths": ["assets/layer-previews/layer-12.png"],
                },
                {
                    "id": "layer-13",
                    "source_layer_id": 13,
                    "name": "Rectangle 1",
                    "kind": "shape",
                    "parent_id": "layer-10",
                    "depth": 1,
                    "z_index": 4,
                    "visible": False,
                    "geometry": {
                        "source_bounds": {"x": 40, "y": 40, "width": 20, "height": 20}
                    },
                },
            ]
        },
    }


def test_pack_includes_hierarchy_text_and_duplicate_counts():
    pack = build_naming_pack(_make_ir())

    assert pack["source"]["filename"] == "sample.psd"
    assert pack["source"]["irSha256"] == ir_sha256_for(_make_ir())
    assert pack["summary"] == {
        "total": 4,
        "groups": 1,
        "textLayers": 1,
        "duplicateNameLayers": 2,
        "hiddenLayers": 1,
        "visualCrops": 0,
    }
    assert pack["semanticVocabulary"]["regions"]
    assert pack["visualEvidence"]["preview"] is None
    assert pack["visualEvidence"]["cropCount"] == 0

    by_id = {entry["id"]: entry for entry in pack["layers"]}
    group = by_id["layer-10"]
    assert group["childIds"] == ["layer-11", "layer-12", "layer-13"]
    assert group["childCount"] == 3
    assert [child["id"] for child in group["children"]] == [
        "layer-11",
        "layer-12",
        "layer-13",
    ]

    title = by_id["layer-11"]
    assert title["text"] == "Hello world"
    assert title["fontFamily"] == "Inter"
    assert title["fontSizePx"] == 24
    assert title["fillColor"] == "#111111"

    rect = by_id["layer-12"]
    assert rect["duplicateName"] is True
    assert rect["nameOccurrences"] == 2
    assert rect["borderRadiusPx"] == 4.0
    assert rect["asset"] == "assets/layer-previews/layer-12.png"
    assert by_id["layer-13"]["visible"] is False
    assert by_id["layer-13"]["nameOccurrences"] == 2


def test_pack_truncates_long_text():
    ir = _make_ir()
    ir["source"]["rawLayers"][1]["typography"]["content"] = "x" * 500

    pack = build_naming_pack(ir, max_text_chars=20)

    text = {entry["id"]: entry for entry in pack["layers"]}["layer-11"]["text"]
    assert len(text) == 20
    assert text.endswith("…")


def test_apply_merges_suggestions_without_mutating_native_names():
    ir = _make_ir()
    candidate = {
        "schemaVersion": "1.0.0",
        "source": {"irSha256": ir_sha256_for(ir)},
        "names": {
            "layer-10": {
                "suggestedName": "hero",
                "confidence": 0.9,
                "reason": "Contains the headline and CTA.",
            },
            "layer-11": {
                "suggestedName": "hero/title",
                "confidence": 0.95,
            },
        },
    }

    result = apply_names(ir, candidate)

    assert ir["source"]["rawLayers"][0]["name"] == "Group 1"
    assert result["summary"] == {
        "total": 4,
        "aiSuggested": 2,
        "ruleBased": 2,
        "missingSuggestions": 2,
        "duplicatesResolved": 0,
        "warnings": [],
    }

    by_id = {layer["id"]: layer for layer in result["layers"]}
    assert by_id["layer-10"]["source"] == "ai_inferred"
    assert by_id["layer-10"]["suggestedName"] == "hero"
    assert by_id["layer-10"]["slug"] == "hero"
    assert by_id["layer-11"]["originalName"] == "Title"
    assert by_id["layer-11"]["uniqueName"] == "hero/title"
    assert by_id["layer-11"]["slug"] == "hero-title"
    assert by_id["layer-12"]["source"] == "rule_based"
    assert by_id["layer-12"]["confidence"] is None
    assert by_id["layer-13"]["source"] == "rule_based"
    assert by_id["layer-13"]["uniqueName"] == "Rectangle 1 (13)"


def test_apply_accepts_list_form_and_string_suggestions():
    ir = _make_ir()
    candidate = {
        "names": [
            {"layerId": "layer-11", "suggestedName": "hero-title"},
            {"layerId": "layer-12", "suggestedName": "layer-12"},
        ]
    }

    result = apply_names(ir, candidate)

    by_id = {layer["id"]: layer for layer in result["layers"]}
    assert by_id["layer-11"]["suggestedName"] == "hero-title"
    assert by_id["layer-12"]["suggestedName"] == "layer-12"
    assert result["summary"]["aiSuggested"] == 2
    assert result["summary"]["warnings"]


def test_apply_disambiguates_duplicate_suggestions_and_slugs():
    ir = _make_ir()
    candidate = {
        "source": {"irSha256": ir_sha256_for(ir)},
        "names": {
            "layer-12": {"suggestedName": "Hero Title"},
            "layer-13": {"suggestedName": "Hero Title"},
        },
    }

    result = apply_names(ir, candidate)

    by_id = {layer["id"]: layer for layer in result["layers"]}
    assert by_id["layer-12"]["uniqueName"] == "Hero Title"
    assert by_id["layer-13"]["uniqueName"] == "Hero Title (13)"
    assert by_id["layer-13"]["disambiguated"] is True
    assert result["summary"]["duplicatesResolved"] == 1


def test_apply_resolves_same_slug_for_distinct_names():
    ir = _make_ir()
    candidate = {
        "source": {"irSha256": ir_sha256_for(ir)},
        "names": {
            "layer-12": {"suggestedName": "Hero Title"},
            "layer-13": {"suggestedName": "hero title"},
        },
    }

    result = apply_names(ir, candidate)

    by_id = {layer["id"]: layer for layer in result["layers"]}
    assert by_id["layer-12"]["slug"] == "hero-title"
    assert by_id["layer-13"]["uniqueName"] == "hero title (13)"
    assert by_id["layer-13"]["slug"] == "hero-title-13"


@pytest.mark.parametrize(
    "candidate, message",
    [
        ({"source": {"irSha256": "wrong"}, "names": {}}, "does not match"),
        ({"names": {"layer-999": "ghost"}}, "unknown layer id"),
        ({"names": {"layer-11": {"suggestedName": ""}}}, "non-empty"),
        ({"names": {"layer-11": {"suggestedName": "x", "confidence": 2}}}, "0..1"),
        ({"names": {"layer-11": {"suggestedName": "x", "confidence": "high"}}}, "numeric"),
        ({"names": {"layer-11": {"suggestedName": "x\ny"}}}, "control characters"),
        ({"names": "bad"}, "must be an object"),
    ],
)
def test_apply_rejects_invalid_candidates(candidate, message):
    with pytest.raises(NamingError, match=message):
        apply_names(_make_ir(), candidate)


def test_pack_and_apply_hashes_ignore_json_formatting(tmp_path):
    ir = _make_ir()
    pretty = json.loads(json.dumps(ir, indent=4))

    pack = build_naming_pack(ir)
    result = apply_names(pretty, {"source": {"irSha256": pack["source"]["irSha256"]}, "names": {}})

    assert result["source"]["irSha256"] == pack["source"]["irSha256"]


def _semantic_ir():
    def layer(layer_id, name, kind, bounds, parent=None, **extra):
        entry = {
            "id": layer_id,
            "source_layer_id": int(layer_id.split("-")[1]),
            "name": name,
            "kind": kind,
            "parent_id": parent,
            "depth": 1 if parent else 0,
            "z_index": 1,
            "visible": True,
            "geometry": {"source_bounds": dict(zip(("x", "y", "width", "height"), bounds))},
        }
        entry.update(extra)
        return entry

    return {
        "document": {
            "metadata": {"filename": "window.psd", "width_px": 100, "height_px": 100}
        },
        "source": {
            "rawLayers": [
                layer("layer-1", "Top Nav", "group", (0, 0, 100, 12)),
                layer("layer-2", "Play Now", "text", (40, 2, 20, 8), "layer-1",
                      typography={"content": "Play Now"}),
                layer("layer-3", "footer", "group", (0, 92, 100, 8)),
                layer("layer-4", "Lef_Nav", "group", (0, 12, 15, 70)),
                layer("layer-5", "Packages", "group", (30, 30, 40, 30)),
                layer("layer-6", "Title", "text", (32, 32, 20, 6), "layer-5",
                      typography={"content": "Starter pack"}),
                layer("layer-7", "Price", "text", (32, 40, 10, 6), "layer-5",
                      typography={"content": "$9.99"}),
                layer("layer-8", "Button", "text", (32, 50, 12, 6), "layer-5",
                      typography={"content": "Buy"}),
                layer("layer-9", "Rectangle 1", "shape", (60, 60, 5, 5)),
                layer("layer-10", "Rectangle 1", "shape", (70, 60, 5, 5)),
            ]
        },
    }


def test_pack_adds_layout_regions_and_semantic_role_hints():
    pack = build_naming_pack(_semantic_ir())
    by_id = {entry["id"]: entry for entry in pack["layers"]}

    assert by_id["layer-1"]["layout"]["regionCandidates"] == ["header"]
    assert by_id["layer-3"]["layout"]["regionCandidates"] == ["footer"]
    assert by_id["layer-4"]["layout"]["regionCandidates"] == ["sidebar-left"]
    assert by_id["layer-5"]["layout"]["regionCandidates"] == ["main-content"]

    assert "header" in by_id["layer-1"]["roleHints"]
    assert "navigation" in by_id["layer-1"]["roleHints"]
    assert "navigation" in by_id["layer-4"]["roleHints"]
    assert by_id["layer-5"]["childKinds"] == {"text": 3}
    assert by_id["layer-5"]["childTextSamples"] == [
        "Starter pack", "$9.99", "Buy",
    ]
    assert "text-block" in by_id["layer-5"]["roleHints"]
    assert "button" in by_id["layer-5"]["roleHints"]
    assert "Rectangle 1" in by_id["layer-9"]["siblingNames"]
    assert pack["semanticVocabulary"]["elements"]


def _visual_ir():
    def layer(layer_id, name, kind, bounds, parent=None, **extra):
        entry = {
            "id": layer_id,
            "source_layer_id": int(layer_id.split("-")[1]),
            "name": name,
            "kind": kind,
            "parent_id": parent,
            "depth": 1 if parent else 0,
            "z_index": 1,
            "visible": True,
            "geometry": {"source_bounds": dict(zip(("x", "y", "width", "height"), bounds))},
        }
        entry.update(extra)
        return entry

    return {
        "document": {
            "metadata": {"filename": "window.psd", "width_px": 100, "height_px": 80}
        },
        "source": {
            "rawLayers": [
                layer("layer-201", "Group A", "group", (10, 10, 20, 20)),
                layer("layer-202", "Group B", "group", (10, 10, 20, 20)),
                layer("layer-203", "Hidden group", "group", (50, 50, 10, 10),
                      visible=False),
                layer("layer-204", "Raster label", "text", (40, 40, 10, 10)),
                layer("layer-205", "Title", "text", (60, 60, 10, 10),
                      typography={"content": "Title"}),
                layer("layer-206", "Rectangle 1", "shape", (0, 0, 5, 5)),
                layer("layer-207", "Rectangle 1", "shape", (20, 0, 5, 5),
                      export_paths=["assets/layer-207.png"]),
            ]
        },
    }


def _preview(path):
    image = Image.new("RGBA", (200, 160), (255, 255, 255, 255))
    image.save(path)
    return path


def test_visual_crops_cover_groups_and_ambiguous_layers(tmp_path):
    ir = _visual_ir()
    preview = _preview(tmp_path / "preview.png")

    visual = render_naming_visuals(
        ir, tmp_path / "visuals", preview, max_edge=64, padding=5
    )

    assert visual["cropCount"] == 4
    assert visual["targetCount"] == 6
    assert visual["skipped"] == {"hidden": 1, "noBounds": 0, "invalidBounds": 0}
    assert set(visual["crops"]) == {
        "layer-201", "layer-202", "layer-204", "layer-206", "layer-207",
    }
    assert visual["crops"]["layer-201"]["file"] == visual["crops"]["layer-202"]["file"]

    for filename in visual["files"]:
        with Image.open(tmp_path / "visuals" / filename) as image:
            assert max(image.size) <= 64
            assert image.format == "PNG"

    pack = build_naming_pack(ir, visual_context=visual)
    by_id = {entry["id"]: entry for entry in pack["layers"]}
    assert pack["visualEvidence"]["cropCount"] == 4
    assert pack["visualEvidence"]["layersWithVisual"] == 5
    assert pack["visualEvidence"]["visualsDir"] == str(tmp_path / "visuals")
    assert by_id["layer-201"]["visual"]["crop"] == visual["crops"]["layer-201"]["file"]
    assert by_id["layer-203"].get("visual") is None
    assert by_id["layer-205"].get("visual") is None
    assert by_id["layer-207"]["visual"]["crop"] == visual["crops"]["layer-207"]["file"]


def test_visual_crops_are_deterministic(tmp_path):
    ir = _visual_ir()
    preview = _preview(tmp_path / "preview.png")

    first = render_naming_visuals(ir, tmp_path / "first", preview, max_edge=64, padding=5)
    second = render_naming_visuals(ir, tmp_path / "second", preview, max_edge=64, padding=5)

    first_hashes = {
        layer_id: crop["sha256"] for layer_id, crop in first["crops"].items()
    }
    second_hashes = {
        layer_id: crop["sha256"] for layer_id, crop in second["crops"].items()
    }
    assert first_hashes == second_hashes
    for filename in first["files"]:
        assert (tmp_path / "first" / filename).read_bytes() == (
            tmp_path / "second" / filename
        ).read_bytes()
