"""Unit tests for asset export, reports and schema validation."""

from pathlib import Path
import json

from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

from psd_inspector.adapters.psd_tools_adapter import PsdToolsAdapter
from psd_inspector.exporters.asset_exporter import export_layer_assets
from psd_inspector.pipeline import DesignIRPipeline
from psd_inspector.validation import validate_design_ir


def _make_psd(path: Path) -> Path:
    psd = PSDImage.new("RGB", (8, 8), color=(255, 255, 255))
    pixels = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    psd.append(PixelLayer.frompil(pixels, psd, "Red A", top=1, left=1))
    psd.append(PixelLayer.frompil(pixels, psd, "Red B", top=4, left=4))
    psd.save(path)
    return path


def test_asset_export_deduplicates_identical_layers(tmp_path):
    psd_path = _make_psd(tmp_path / "sample.psd")
    raw_layers = PsdToolsAdapter().get_layers(psd_path)

    result = export_layer_assets(psd_path, raw_layers, tmp_path / "assets")

    assert result["summary"]["exportedLayers"] == 2
    assert result["summary"]["uniqueFiles"] == 1
    assert result["summary"]["deduplicatedLayers"] == 1
    assert result["assets"][1]["duplicatedFrom"] == result["assets"][0]["layerId"]
    assert result["assets"][0]["bounds"] == {"x": 1, "y": 1, "width": 4, "height": 4}
    assert result["assets"][0]["documentOffset"] == {"x": 1, "y": 1}
    assert (tmp_path / "assets" / result["assets"][0]["file"]).is_file()
    assert (tmp_path / "assets" / "asset-index.json").is_file()


def test_asset_export_excludes_text_layers(tmp_path, monkeypatch):
    class _FakeTextLayer:
        layer_id = 42
        name = "Headline"
        kind = "type"

        def is_group(self):
            return False

        def topil(self):
            raise AssertionError("text layers must not be rasterized")

    class _FakePSD:
        def __iter__(self):
            return iter([_FakeTextLayer()])

    class _FakePsdImage:
        @staticmethod
        def open(handle):
            return _FakePSD()

    input_path = tmp_path / "sample.psd"
    input_path.write_bytes(b"")
    raw_layers = [
        {"id": "layer-42", "source_layer_id": 42, "name": "Headline", "kind": "text"}
    ]
    monkeypatch.setattr(
        "psd_inspector.exporters.asset_exporter.PSDImage", _FakePsdImage
    )

    result = export_layer_assets(input_path, raw_layers, tmp_path / "assets")

    assert result["summary"]["exportedLayers"] == 0
    assert result["summary"]["excludedTextLayers"] == 1
    assert result["assets"] == []
    assert "Text layers are excluded" in result["note"]


def test_asset_png_bytes_are_deterministic(tmp_path):
    psd_path = _make_psd(tmp_path / "sample.psd")
    raw_layers = PsdToolsAdapter().get_layers(psd_path)

    first = export_layer_assets(psd_path, raw_layers, tmp_path / "first")
    second = export_layer_assets(psd_path, raw_layers, tmp_path / "second")

    first_hashes = [asset["sha256"] for asset in first["assets"]]
    assert first_hashes == [asset["sha256"] for asset in second["assets"]]

    png_path = tmp_path / "first" / first["assets"][0]["file"]
    payload = png_path.read_bytes()
    assert b"iCCP" not in payload
    assert Image.open(png_path).info.get("icc_profile") is None


def test_pipeline_writes_assets_reports_and_validation(tmp_path):
    psd_path = _make_psd(tmp_path / "sample.psd")
    output_dir = tmp_path / "out"

    result = DesignIRPipeline().process_file(
        str(psd_path), str(output_dir), export_assets=True, report=True
    )

    assert result["status"] == "success"
    assert result["validation_status"] == "valid"
    for name in (
        "reports/extraction-summary.json",
        "reports/unsupported.md",
        "reports/layer-inventory.md",
        "reports/design-spec.md",
        "reports/validation.json",
        "assets/asset-index.json",
    ):
        assert (output_dir / name).is_file()

    with open(output_dir / "design.json", encoding="utf-8") as handle:
        ir = json.load(handle)
    assert all(layer["export_paths"] for layer in ir["source"]["rawLayers"])
    assert ir["diagnostics"]["validationResults"] == []

    with open(output_dir / "manifest.json", encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["assets"]["uniqueFiles"] == 1
    assert manifest["validation"]["status"] == "valid"
    assert "reports/extraction-summary.json" in manifest["output"]["files"]
    assert "assets/asset-index.json" in manifest["output"]["files"]
    assert manifest["output"]["hashes"]["reports/validation.json"]

    with open(output_dir / "reports" / "extraction-summary.json", encoding="utf-8") as handle:
        summary = json.load(handle)
    assert summary["layers"]["total"] == 2
    assert summary["assets"]["enabled"] is True
    assert summary["assets"]["uniqueFiles"] == 1
    assert summary["validation"]["status"] == "valid"


def test_summary_report_written_without_detailed_flag(tmp_path):
    psd_path = _make_psd(tmp_path / "sample.psd")
    output_dir = tmp_path / "out"

    result = DesignIRPipeline(profile="fast").process_file(
        str(psd_path), str(output_dir)
    )

    assert result["status"] == "success"
    assert (output_dir / "reports" / "extraction-summary.json").is_file()
    assert not (output_dir / "reports" / "design-spec.md").exists()
    with open(output_dir / "reports" / "extraction-summary.json", encoding="utf-8") as handle:
        summary = json.load(handle)
    assert summary["assets"] == {"enabled": False}
    assert summary["validation"]["status"] == "valid"


def test_validation_detects_missing_required_fields(tmp_path):
    report = validate_design_ir({})

    assert report["status"] == "invalid"
    paths = {error["path"] for error in report["errors"]}
    assert "$" in paths


def test_validation_unavailable_without_schema(tmp_path):
    report = validate_design_ir({}, schema_path=tmp_path / "missing.json")

    assert report["status"] == "unavailable"
    assert report["errors"] == []
    assert "not found" in report["warning"]
