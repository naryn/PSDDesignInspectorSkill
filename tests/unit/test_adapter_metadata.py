"""Unit tests for smart object and mask metadata extraction."""

import hashlib
from types import SimpleNamespace

from psd_inspector.adapters.psd_tools_adapter import PsdToolsAdapter
from psd_inspector.pipeline import DesignIRPipeline


def _smart_object(**overrides):
    values = dict(
        kind="data",
        filename="card.png",
        filetype="png",
        filesize=4,
        unique_id="uuid-1",
        resolution=72.0,
        transform_box=(10.0, 20.0, 30.0, 20.0, 30.0, 40.0, 10.0, 40.0),
        is_psd=lambda: False,
        data=b"data",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_embedded_smart_object_metadata():
    layer = SimpleNamespace(kind="smartobject", smart_object=_smart_object())

    link, data = PsdToolsAdapter._smart_object_metadata(layer)

    assert link is None
    assert data["kind"] == "data"
    assert data["filename"] == "card.png"
    assert data["filesize_bytes"] == 4
    assert data["resolution_dpi"] == 72.0
    assert data["transform_box"] == [10.0, 20.0, 30.0, 20.0, 30.0, 40.0, 10.0, 40.0]
    assert data["embedded_sha256"] == hashlib.sha256(b"data").hexdigest()
    assert data["contents_extracted"] is False


def test_external_smart_object_link_uses_full_path():
    smart_object = _smart_object(
        kind="external",
        filename="card.psd",
        _data=SimpleNamespace(
            linked_file={b"fullPath": SimpleNamespace(value="file:///tmp/card.psd")}
        ),
    )
    layer = SimpleNamespace(kind="smartobject", smart_object=smart_object)

    link, data = PsdToolsAdapter._smart_object_metadata(layer)

    assert link == "/tmp/card.psd"
    assert data["kind"] == "external"
    assert "embedded_sha256" not in data


def test_mask_metadata():
    mask = SimpleNamespace(
        bbox=(10, 20, 50, 80),
        disabled=False,
        flags=SimpleNamespace(invert_mask=True),
        background_color=255,
        has_real=lambda: False,
    )
    layer = SimpleNamespace(has_mask=lambda: True, mask=mask)

    data = PsdToolsAdapter._mask_metadata(layer)

    assert data == {
        "bounds": {"x": 10, "y": 20, "width": 40, "height": 60},
        "disabled": False,
        "inverted": True,
        "background_color": 255,
        "has_real": False,
    }


def test_vector_mask_metadata():
    mask = SimpleNamespace(
        bbox=(1.0, 2.0, 11.0, 22.0),
        disabled=True,
        inverted=False,
        initial_fill_rule=1,
        paths=[object(), object()],
    )
    layer = SimpleNamespace(has_vector_mask=lambda: True, vector_mask=mask)

    data = PsdToolsAdapter._vector_mask_metadata(layer)

    assert data == {
        "normalized_bounds": {"x": 1.0, "y": 2.0, "width": 10.0, "height": 20.0},
        "disabled": True,
        "inverted": False,
        "fill_rule": 1,
        "path_count": 2,
    }


def test_pipeline_maps_metadata_without_claiming_contents():
    pipeline = DesignIRPipeline()
    raw_layer = {
        "id": "layer-1",
        "name": "Card",
        "kind": "smart_object",
        "has_mask": True,
        "has_vector_mask": True,
        "bounds": {"x": 0, "y": 0, "width": 100, "height": 100},
        "mask_data": {
            "bounds": {"x": 0, "y": 0, "width": 100, "height": 100},
            "disabled": False,
            "inverted": False,
            "background_color": 255,
            "has_real": False,
        },
        "vector_mask_data": {
            "normalized_bounds": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
            "disabled": False,
            "inverted": False,
            "fill_rule": 0,
            "path_count": 1,
        },
        "smart_object_data": {
            "kind": "data",
            "filename": "card.psd",
            "contents_extracted": False,
        },
        "smart_object_link": None,
    }

    layer = pipeline._convert_raw_to_layer(raw_layer, 100, 100)

    assert layer.mask.bounds["width"] == 100
    assert layer.vector_mask.path_count == 1
    assert layer.smart_object_data["filename"] == "card.psd"
    assert layer.extraction.property_sources["mask.metadata"]["source"] == "psd_native"
    assert layer.extraction.property_sources["smart_object_data"]["source"] == "psd_native"
    assert "smart_object_contents" in layer.extraction.unsupported_properties
    assert "layer_mask" in layer.extraction.unsupported_properties
