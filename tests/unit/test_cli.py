"""Unit tests for CLI layer lookup."""

import json
from types import SimpleNamespace

import pytest

from psd_inspector.cli import _geometry_neighbors, _layer_get


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
