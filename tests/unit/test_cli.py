"""Unit tests for CLI layer lookup."""

import json
from types import SimpleNamespace

import pytest
from PIL import Image

from psd_inspector.cli import (
    _geometry_neighbors,
    _handle_viewer,
    _layer_get,
    _names_apply,
    _names_pack,
)
from psd_inspector.naming import ir_sha256_for


@pytest.fixture()
def ir_path(tmp_path):
    path = tmp_path / "design.json"
    path.write_text(
        json.dumps(
            {
                "source": {
                    "rawLayers": [
                        {
                            "id": "layer-123",
                            "source_layer_id": 123,
                            "name": "Button",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("target", ["layer-123", "123"])
def test_layer_get_accepts_prefixed_and_bare_ids(ir_path, capsys, target):
    _layer_get(SimpleNamespace(ir=str(ir_path), id=target))

    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "layer-123"


@pytest.mark.parametrize("target", ["nope", "layer-nope", ""])
def test_layer_get_reports_unknown_ids_without_traceback(ir_path, capsys, target):
    with pytest.raises(SystemExit) as exc:
        _layer_get(SimpleNamespace(ir=str(ir_path), id=target))

    assert exc.value.code == 1
    assert "Layer not found" in capsys.readouterr().err


def test_geometry_neighbors_accepts_bare_native_ids(tmp_path, capsys):
    path = tmp_path / "design.json"
    path.write_text(
        json.dumps(
            {
                "source": {
                    "rawLayers": [
                        {
                            "id": "layer-123",
                            "source_layer_id": 123,
                            "name": "A",
                            "kind": "pixel",
                            "visible": True,
                            "parent_id": None,
                            "geometry": {
                                "source_bounds": {
                                    "x": 0,
                                    "y": 0,
                                    "width": 10,
                                    "height": 10,
                                }
                            },
                        },
                        {
                            "id": "layer-124",
                            "source_layer_id": 124,
                            "name": "B",
                            "kind": "pixel",
                            "visible": True,
                            "parent_id": None,
                            "geometry": {
                                "source_bounds": {
                                    "x": 20,
                                    "y": 0,
                                    "width": 10,
                                    "height": 10,
                                }
                            },
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    _geometry_neighbors(SimpleNamespace(ir=str(path), id="123", distance=100.0))

    payload = json.loads(capsys.readouterr().out)
    assert payload["layer"]["id"] == "layer-123"
    assert [item["target_layer_id"] for item in payload["neighbors"]] == ["layer-124"]


def test_names_pack_writes_context_pack(ir_path, tmp_path, capsys):
    output = tmp_path / "naming-pack.json"

    _names_pack(
        SimpleNamespace(
            ir=str(ir_path),
            output=str(output),
            preview=None,
            visuals="none",
            visuals_dir=None,
            max_edge=512,
            padding=32,
        )
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"]["filename"] is None
    assert payload["source"]["irSha256"]
    assert payload["summary"]["total"] == 1
    assert payload["layers"][0]["id"] == "layer-123"
    assert payload["layers"][0]["fallbackName"] == "Button"
    assert "Naming pack written to" in capsys.readouterr().out


def test_names_apply_writes_names_json(ir_path, tmp_path, capsys):
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps({"names": {"layer-123": "cta-button"}}), encoding="utf-8"
    )
    output = tmp_path / "names.json"

    _names_apply(
        SimpleNamespace(
            ir=str(ir_path), names=str(candidate_path), output=str(output)
        )
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["layers"][0]["suggestedName"] == "cta-button"
    assert payload["layers"][0]["slug"] == "cta-button"
    assert payload["summary"]["aiSuggested"] == 1
    captured = capsys.readouterr()
    assert "Names written to" in captured.out
    assert "irSha256 is missing" in captured.err


def test_names_apply_reports_unknown_layer(ir_path, tmp_path, capsys):
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps({"names": {"layer-999": "ghost"}}), encoding="utf-8"
    )

    with pytest.raises(SystemExit) as exc:
        _names_apply(
            SimpleNamespace(ir=str(ir_path), names=str(candidate_path), output=None)
        )

    assert exc.value.code == 1
    assert "unknown layer id" in capsys.readouterr().err


def test_names_apply_rejects_stale_pack(ir_path, tmp_path, capsys):
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps({"source": {"irSha256": "stale"}, "names": {}}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        _names_apply(
            SimpleNamespace(ir=str(ir_path), names=str(candidate_path), output=None)
        )

    assert exc.value.code == 1
    assert "does not match" in capsys.readouterr().err


def test_viewer_command_applies_semantic_names(tmp_path, capsys):
    ir = {
        "document": {"metadata": {"width_px": 100, "height_px": 80, "filename": "ui.psd"}},
        "source": {
            "rawLayers": [
                {
                    "id": "layer-123",
                    "source_layer_id": 123,
                    "name": "Rectangle 1",
                    "kind": "group",
                    "parent_id": None,
                    "geometry": {
                        "source_bounds": {"x": 0, "y": 0, "width": 100, "height": 12}
                    },
                }
            ]
        },
    }
    ir_path = tmp_path / "design.json"
    ir_path.write_text(json.dumps(ir), encoding="utf-8")
    preview = tmp_path / "preview.png"
    Image.new("RGB", (100, 80), "white").save(preview)
    names = {
        "source": {"irSha256": ir_sha256_for(ir)},
        "layers": [
            {
                "id": "layer-123",
                "uniqueName": "header/app-bar",
                "source": "ai_inferred",
                "confidence": 0.9,
                "reason": "Top application bar.",
            }
        ],
    }
    names_path = tmp_path / "names.json"
    names_path.write_text(json.dumps(names), encoding="utf-8")
    output = tmp_path / "viewer.html"

    _handle_viewer(
        SimpleNamespace(
            ir=str(ir_path),
            names=str(names_path),
            preview=str(preview),
            output=str(output),
        )
    )

    html = output.read_text(encoding="utf-8")
    assert "header/app-bar" in html
    assert "Rectangle 1" in html
    assert "semantic names: 1 (AI 1, rule 0)" in capsys.readouterr().out


def test_viewer_rejects_stale_names(tmp_path, capsys):
    ir = {
        "document": {"metadata": {"width_px": 10, "height_px": 10}},
        "source": {"rawLayers": [{"id": "layer-1", "name": "A"}]},
    }
    ir_path = tmp_path / "design.json"
    ir_path.write_text(json.dumps(ir), encoding="utf-8")
    preview = tmp_path / "preview.png"
    Image.new("RGB", (10, 10), "white").save(preview)
    names_path = tmp_path / "names.json"
    names_path.write_text(
        json.dumps({"source": {"irSha256": "stale"}, "layers": []}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        _handle_viewer(
            SimpleNamespace(
                ir=str(ir_path),
                names=str(names_path),
                preview=str(preview),
                output=None,
            )
        )

    assert exc.value.code == 1
    assert "irSha256 mismatch" in capsys.readouterr().err


def test_names_pack_generates_visual_crops(tmp_path, capsys):
    ir_path = tmp_path / "design.json"
    ir_path.write_text(
        json.dumps(
            {
                "document": {
                    "metadata": {"width_px": 100, "height_px": 80, "filename": "ui.psd"}
                },
                "source": {
                    "rawLayers": [
                        {
                            "id": "layer-1",
                            "source_layer_id": 1,
                            "name": "Top",
                            "kind": "group",
                            "parent_id": None,
                            "visible": True,
                            "geometry": {
                                "source_bounds": {"x": 10, "y": 5, "width": 95, "height": 12}
                            },
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    preview = tmp_path / "preview.png"
    Image.new("RGBA", (200, 160), (255, 255, 255, 255)).save(preview)
    output = tmp_path / "naming-pack.json"
    visuals_dir = tmp_path / "visuals"

    _names_pack(
        SimpleNamespace(
            ir=str(ir_path),
            output=str(output),
            preview=str(preview),
            visuals="auto",
            visuals_dir=str(visuals_dir),
            max_edge=64,
            padding=5,
        )
    )

    pack = json.loads(output.read_text(encoding="utf-8"))
    assert pack["visualEvidence"]["cropCount"] == 1
    assert pack["visualEvidence"]["preview"] == str(preview.resolve())
    assert pack["summary"]["visualCrops"] == 1
    layer = pack["layers"][0]
    assert layer["layout"]["regionCandidates"] == ["header"]
    assert (visuals_dir / layer["visual"]["crop"]).is_file()
    assert "visual crops: 1" in capsys.readouterr().out
