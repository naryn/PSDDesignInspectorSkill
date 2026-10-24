"""Integration test: parse a generated PSD end-to-end (P1 + P2)."""

import hashlib
import json

import numpy as np
import pytest
from PIL import Image
from psd_tools import PSDImage

from psd_inspector.adapters.psd_tools_adapter import PsdToolsAdapter
from psd_inspector.pipeline import DesignIRPipeline


BLUE = (36, 107, 253)  # #246BFD


@pytest.fixture()
def sample_psd(tmp_path):
    psd = PSDImage.new("RGB", (300, 200), color=(255, 255, 255))
    for index, left in enumerate((40, 136)):
        pixels = Image.fromarray(
            np.full((32, 80, 3), BLUE, dtype=np.uint8)
        )
        psd.create_pixel_layer(pixels, name=f"btn-{index}", left=left, top=80)
    psd.create_group([], name="nav")

    path = tmp_path / "sample.psd"
    psd.save(path)
    return path


def test_adapter_metadata(sample_psd):
    adapter = PsdToolsAdapter()
    assert adapter.can_parse(sample_psd)

    metadata = adapter.parse(sample_psd)
    assert metadata.width_px == 300
    assert metadata.height_px == 200
    assert metadata.color_mode.value == "RGB"
    assert metadata.psd_version.value == "PSD"
    assert metadata.total_layers == 3
    assert metadata.total_groups == 1
    assert metadata.dpi_horizontal == 72.0
    assert len(metadata.sha256) == 64


def test_adapter_layers(sample_psd):
    layers = PsdToolsAdapter().get_layers(sample_psd)

    assert len(layers) == 3
    by_name = {layer["name"]: layer for layer in layers}
    assert by_name["btn-0"]["bounds"] == {"x": 40, "y": 80, "width": 80, "height": 32}
    assert by_name["btn-0"]["kind"] == "pixel"
    assert by_name["nav"]["kind"] == "group"
    assert all(layer["parent_id"] is None for layer in layers)


def test_adapter_samples_colors_only_when_enabled(sample_psd):
    disabled = PsdToolsAdapter().get_layers(sample_psd)
    assert all(layer["sampled_colors"] == [] for layer in disabled)

    enabled = PsdToolsAdapter({"sample_colors": True}).get_layers(sample_psd)
    btn = next(layer for layer in enabled if layer["name"] == "btn-0")
    assert btn["sampled_colors"][0]["color"] == "#246BFD"
    assert btn["sampled_colors"][0]["coverage"] == 1.0


def test_pipeline_end_to_end(sample_psd, tmp_path):
    output_dir = tmp_path / "out"
    before = hashlib.sha256(sample_psd.read_bytes()).hexdigest()

    result = DesignIRPipeline().process_file(str(sample_psd), str(output_dir))

    assert result["status"] == "success", result
    for filename in (
        "design.json",
        "source-layers.json",
        "geometry.json",
        "design-tokens.json",
        "previews/original.png",
        "previews/annotated.png",
        "viewer.html",
        "manifest.json",
    ):
        assert (output_dir / filename).exists(), filename

    design = json.loads((output_dir / "design.json").read_text(encoding="utf-8"))
    assert design["schemaVersion"] == "1.0.0"
    assert len(design["source"]["rawLayers"]) == 3
    assert design["document"]["metadata"]["sha256"] == before
    assert len(design["source"]["layerHierarchy"]) == 3

    measurements = design["analysis"]["measurements"]
    assert any(
        item["type"] == "sampled_color" and item["color"] == "#246BFD"
        for item in measurements
    )
    assert any(item["type"] == "spacing_group" and item["gap_px"] == 16.0 for item in measurements)

    hypotheses = design["analysis"]["layoutHypotheses"]
    assert any(
        item["layout_type"] == "flex"
        and item["flex_direction"] == "row"
        and item["gap_x_px"] == 16.0
        for item in hypotheses
    )

    tokens = json.loads((output_dir / "design-tokens.json").read_text(encoding="utf-8"))
    assert any(token["value"]["base"] == "#246BFD" for token in tokens["colorTokens"])
    assert any(token["value"]["base"] == "16" for token in tokens["spacingTokens"])

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["inputFile"]["sha256"] == before
    assert manifest["parser"]["profile"] == "full"
    assert manifest["run"]["timestamp"] != "placeholder"
    assert set(manifest["output"]["files"]) == {
        "design.json",
        "source-layers.json",
        "geometry.json",
        "design-tokens.json",
        "previews/original.png",
        "previews/annotated.png",
        "viewer.html",
        "reports/extraction-summary.json",
        "manifest.json",
    }
    assert manifest["validation"]["status"] == "valid"
    assert len(manifest["output"]["hashes"]["design.json"]) == 64
    assert "manifest.json" not in manifest["output"]["hashes"]

    preview = Image.open(output_dir / "previews" / "original.png")
    assert preview.size == (300, 200)
    annotated = Image.open(output_dir / "previews" / "annotated.png")
    assert annotated.size == (300, 200)
    viewer = (output_dir / "viewer.html").read_text(encoding="utf-8")
    assert "data:image/jpeg;base64," in viewer
    assert "btn-0" in viewer

    after = hashlib.sha256(sample_psd.read_bytes()).hexdigest()
    assert before == after, "original PSD must never be modified"


def test_fast_profile_skips_analysis(sample_psd, tmp_path):
    output_dir = tmp_path / "fast"
    result = DesignIRPipeline(profile="fast").process_file(str(sample_psd), str(output_dir))

    assert result["status"] == "success", result
    assert not (output_dir / "geometry.json").exists()
    assert not (output_dir / "design-tokens.json").exists()
    assert not (output_dir / "previews").exists()
    assert not (output_dir / "viewer.html").exists()
