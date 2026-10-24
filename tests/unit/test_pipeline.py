"""Unit tests for DesignIRPipeline."""

import pytest
from pathlib import Path

from psd_inspector.pipeline import DesignIRPipeline, ExtractorProfile
from psd_inspector.models.document import ColorMode, DocumentMetadata, PSDVersion


def make_metadata(**overrides):
    values = dict(
        filename="test.psd",
        parser_version="1.0.0",
        width_px=1000,
        height_px=500,
        dpi_horizontal=72.0,
        dpi_vertical=72.0,
        color_mode=ColorMode.RGB,
        bit_depth=8,
        psd_version=PSDVersion.PSD,
        total_layers=2,
        total_groups=0,
        max_depth=0,
        visible_layers=2,
        hidden_layers=0,
        smart_objects=0,
    )
    values.update(overrides)
    return DocumentMetadata(**values)


class TestDesignIRPipeline:
    """Test cases for DesignIRPipeline."""

    def test_init_with_default_profile(self):
        pipeline = DesignIRPipeline()
        assert pipeline.profile == ExtractorProfile.FULL

    def test_init_with_fast_profile(self):
        pipeline = DesignIRPipeline(profile=ExtractorProfile.FAST)
        assert pipeline.profile == ExtractorProfile.FAST

    def test_build_design_ir_structure(self):
        pipeline = DesignIRPipeline()
        raw_layers = [
            {
                "id": "layer-1",
                "name": "Test Layer",
                "kind": "pixel",
                "visible": True,
                "bounds": {"x": 0, "y": 0, "width": 100, "height": 100},
            }
        ]

        design_ir = pipeline._build_design_ir(make_metadata(), raw_layers, [], [])

        assert design_ir["schemaVersion"] == pipeline.SCHEMA_VERSION
        for key in ("document", "source", "analysis", "designSystem", "diagnostics"):
            assert key in design_ir
        assert design_ir["document"]["metadata"]["width_px"] == 1000
        assert design_ir["source"]["rawLayers"][0]["id"] == "layer-1"

    def test_convert_raw_to_layer(self):
        pipeline = DesignIRPipeline()
        raw_layer = {
            "id": "layer-123",
            "source_layer_id": 123,
            "name": "TestButton",
            "kind": "shape",
            "parent_id": "group-100",
            "z_index": 5,
            "depth": 1,
            "visible": True,
            "opacity": 0.8,
            "blend_mode": "normal",
            "bounds": {"x": 10, "y": 20, "width": 100, "height": 50},
        }
        bounds_by_id = {"group-100": {"x": 0, "y": 0, "width": 500, "height": 500}}

        layer = pipeline._convert_raw_to_layer(raw_layer, 1000, 500, bounds_by_id)

        assert layer.id == "layer-123"
        assert layer.source_layer_id == 123
        assert layer.name == "TestButton"
        assert layer.kind.value == "shape"
        assert layer.visible is True
        assert layer.appearance.opacity == 0.8
        assert layer.geometry.relative_to_parent == {"x": 10, "y": 20}
        assert layer.geometry.normalized["width"] == pytest.approx(0.1)

    def test_normalized_coordinates_zero_document(self):
        pipeline = DesignIRPipeline()
        raw_layer = {
            "id": "layer-1",
            "name": "Zero",
            "kind": "pixel",
            "bounds": {"x": 0, "y": 0, "width": 10, "height": 10},
        }

        layer = pipeline._convert_raw_to_layer(raw_layer, 0, 0)

        assert layer.geometry.normalized["width"] == 0.0

    def test_layer_mask_is_reported_as_unsupported_without_false_provenance(self):
        pipeline = DesignIRPipeline()
        raw_layer = {
            "id": "layer-1",
            "name": "Masked",
            "kind": "pixel",
            "has_mask": True,
            "bounds": {"x": 0, "y": 0, "width": 10, "height": 10},
        }

        layer = pipeline._convert_raw_to_layer(raw_layer, 100, 100)

        assert layer.extraction.status.value == "partial"
        assert "layer_mask" in layer.extraction.unsupported_properties
        assert "masks" not in layer.extraction.property_sources
        assert layer.masks == []

    def test_map_blend_mode_unknown(self):
        pipeline = DesignIRPipeline()
        assert pipeline._map_blend_mode("unknown_mode") == "normal"

    def test_map_layer_kind_unknown(self):
        pipeline = DesignIRPipeline()
        assert pipeline._map_layer_kind("unknown_kind") == "pixel"

    def test_process_file_invalid_input(self, tmp_path):
        pipeline = DesignIRPipeline()
        result = pipeline.process_file(str(tmp_path / "missing.psd"), str(tmp_path / "out"))
        assert result["status"] == "error"
