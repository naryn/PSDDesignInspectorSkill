"""Unit tests for annotated previews and the HTML viewer."""

from PIL import Image

from psd_inspector.exporters.preview_exporter import draw_annotations
from psd_inspector.exporters.viewer_exporter import build_viewer_html


def _layer(layer_id, x, y, width, height, kind="pixel", visible=True, name=None, parent=None):
    return {
        "id": layer_id,
        "name": name or layer_id,
        "kind": kind,
        "parent_id": parent,
        "depth": 0,
        "z_index": 0,
        "visible": visible,
        "geometry": {
            "source_bounds": {"x": x, "y": y, "width": width, "height": height},
            "relative_to_parent": {"x": x, "y": y},
        },
        "appearance": {"opacity": 1.0, "blend_mode": "normal"},
        "extraction": {
            "status": "complete",
            "source": "psd_native",
            "property_sources": {},
            "unsupported_properties": [],
        },
    }


def _design(layers, relationships=None):
    return {
        "schemaVersion": "1.0.0",
        "document": {
            "metadata": {
                "filename": "sample.psd",
                "width_px": 200,
                "height_px": 120,
                "color_mode": "RGB",
            }
        },
        "source": {"rawLayers": layers},
        "analysis": {
            "spatialRelationships": relationships or [],
            "layoutHypotheses": [],
        },
        "diagnostics": {"warnings": []},
    }


def test_draw_bounds_and_spacing():
    base = Image.new("RGB", (200, 120), (255, 255, 255))
    layers = [
        _layer("layer-a", 10, 10, 40, 20),
        _layer("layer-b", 60, 10, 40, 20),
    ]
    relationships = [
        {
            "source_layer_id": "layer-a",
            "target_layer_id": "layer-b",
            "distance_px": 10.0,
            "projection_overlap": True,
            "relative_position": "right",
            "is_neighbor": True,
        }
    ]

    annotated = draw_annotations(
        base, layers, show=("bounds", "spacing"), relationships=relationships
    )

    assert annotated.size == base.size
    assert annotated.getpixel((10, 10))[:3] != (255, 255, 255)
    assert annotated.getpixel((50, 20))[:3] != (255, 255, 255)


def test_hidden_layers_are_not_drawn_by_default():
    base = Image.new("RGB", (200, 120), (255, 255, 255))
    hidden = _layer("layer-hidden", 10, 10, 40, 20, visible=False)

    annotated = draw_annotations(base, [hidden], show=("bounds",))
    assert annotated.getpixel((10, 10))[:3] == (255, 255, 255)

    with_hidden = draw_annotations(base, [hidden], show=("bounds",), include_hidden=True)
    assert with_hidden.getpixel((10, 10))[:3] != (255, 255, 255)


def test_scaled_preview_uses_document_coordinates():
    base = Image.new("RGB", (400, 240), (255, 255, 255))
    layer = _layer("layer-a", 10, 10, 40, 20)

    annotated = draw_annotations(
        base,
        [layer],
        show=("bounds",),
        document_width=200,
        document_height=120,
    )

    assert annotated.size == base.size
    assert annotated.getpixel((20, 20))[:3] != (255, 255, 255)


def test_viewer_is_standalone_and_embeds_data():
    layers = [_layer("layer-a", 10, 10, 40, 20, name="Card")]
    html = build_viewer_html(_design(layers), Image.new("RGB", (200, 120), "white"))

    assert "data:image/jpeg;base64," in html
    assert "layer-a" in html
    assert "Card" in html
    assert "http://" not in html
    assert "https://" not in html
    assert html.count("<script") == 1


def test_viewer_embeds_mask_and_smart_object_metadata():
    layer = _layer("layer-a", 10, 10, 40, 20, kind="smart_object", name="Card")
    layer["mask"] = {
        "bounds": {"x": 1, "y": 2, "width": 3, "height": 4},
        "disabled": True,
        "inverted": True,
        "background_color": 7,
        "has_real": False,
    }
    layer["vector_mask"] = {
        "normalized_bounds": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        "disabled": False,
        "inverted": False,
        "fill_rule": 0,
        "path_count": 2,
    }
    layer["smart_object_data"] = {
        "kind": "data",
        "filename": "card.psd",
        "filesize_bytes": 1234,
        "contents_extracted": False,
    }

    html = build_viewer_html(_design([layer]), Image.new("RGB", (200, 120), "white"))

    assert "card.psd" in html
    assert '"background_color":7' in html
    assert '"path_count":2' in html
    assert "declutterLabels" in html


def test_viewer_escapes_layer_names():
    layers = [_layer("layer-a", 10, 10, 40, 20, name="x</script><script>alert(1)</script>")]
    html = build_viewer_html(_design(layers), Image.new("RGB", (200, 120), "white"))

    assert "x</script><script>alert(1)</script>" not in html
    assert html.count("</script>") == 1
