"""Unit tests for measured geometry and layout hypotheses."""

import pytest

from psd_inspector.analysis.geometry_engine import GeometryAnalyzer
from psd_inspector.analysis.layout_detector import LayoutDetector


def make_layer(layer_id, x, y, width, height, parent_id=None, kind="pixel", visible=True):
    return {
        "id": layer_id,
        "name": layer_id,
        "kind": kind,
        "parent_id": parent_id,
        "visible": visible,
        "geometry": {
            "source_bounds": {"x": x, "y": y, "width": width, "height": height}
        },
        "appearance": {},
    }


def test_horizontal_spacing_and_flex_row():
    layers = [
        make_layer("a", 20, 40, 60, 30),
        make_layer("b", 96, 40, 60, 30),
        make_layer("c", 172, 40, 60, 30),
    ]

    result = GeometryAnalyzer().analyze(layers, 300, 120)

    spacing = [m for m in result["measurements"] if m["type"] == "spacing_group"]
    assert any(
        m["direction"] == "horizontal" and m["gap_px"] == 16.0 for m in spacing
    )
    alignment_types = {
        m["alignment_type"] for m in result["measurements"] if m["type"] == "alignment_group"
    }
    assert "top" in alignment_types

    flex = [h for h in result["layoutHypotheses"] if h["layout_type"] == "flex"]
    assert any(h["flex_direction"] == "row" and h["gap_x_px"] == 16.0 for h in flex)
    assert all(h["basis"] == "measured_geometry" for h in result["layoutHypotheses"])


def test_vertical_spacing_and_flex_column():
    layers = [
        make_layer("a", 20, 20, 100, 30),
        make_layer("b", 20, 66, 100, 30),
    ]

    result = GeometryAnalyzer().analyze(layers, 200, 200)

    flex = [h for h in result["layoutHypotheses"] if h["layout_type"] == "flex"]
    assert any(h["flex_direction"] == "column" and h["gap_y_px"] == 16.0 for h in flex)


def test_diagonal_neighbor_is_not_a_css_gap():
    layers = [
        make_layer("a", 10, 10, 20, 20),
        make_layer("b", 60, 60, 20, 20),
    ]

    relationships = GeometryAnalyzer(max_neighbor_distance=200).analyze(
        layers, 100, 100
    )["spatialRelationships"]

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship["relative_position"] == "diagonal"
    assert relationship["projection_overlap"] is False
    assert relationship["distance_px"] == pytest.approx(42.43, abs=0.01)


def test_overlapping_layers_are_reported_as_overlap():
    layers = [
        make_layer("a", 10, 10, 50, 50),
        make_layer("b", 30, 30, 50, 50),
    ]

    relationships = GeometryAnalyzer().analyze(layers, 100, 100)["spatialRelationships"]

    assert relationships[0]["relative_position"] == "overlapping"
    assert relationships[0]["distance_px"] == 0
    assert relationships[0]["overlap_ratio"] > 0


def test_group_padding_measurement():
    group = make_layer("g", 0, 0, 200, 100, kind="group")
    children = [
        make_layer("a", 10, 10, 50, 20, parent_id="g"),
        make_layer("b", 10, 40, 50, 20, parent_id="g"),
    ]

    result = GeometryAnalyzer().analyze([group] + children, 300, 200)

    padding = [m for m in result["measurements"] if m["type"] == "group_padding"]
    assert len(padding) == 1
    assert padding[0]["padding"] == {"top": 10, "right": 140, "bottom": 40, "left": 10}


def test_grid_hypothesis():
    layers = [
        make_layer("a", 0, 0, 50, 40),
        make_layer("b", 60, 0, 50, 40),
        make_layer("c", 0, 60, 50, 40),
        make_layer("d", 60, 60, 50, 40),
    ]

    result = GeometryAnalyzer().analyze(layers, 200, 200)

    grid = [h for h in result["layoutHypotheses"] if h["layout_type"] == "grid"]
    assert len(grid) == 1
    assert grid[0]["grid_columns"] == 2
    assert grid[0]["grid_rows"] == 2
    assert grid[0]["gap_x_px"] == 10.0
    assert grid[0]["gap_y_px"] == 20.0


def test_absolute_fallback_without_evidence():
    layers = [
        make_layer("a", 10, 10, 20, 20),
        make_layer("b", 50, 50, 20, 20),
    ]

    result = GeometryAnalyzer().analyze(layers, 100, 100)

    assert len(result["layoutHypotheses"]) == 1
    assert result["layoutHypotheses"][0]["layout_type"] == "absolute"
    assert result["layoutHypotheses"][0]["confidence"] < 0.5


def test_hidden_and_group_layers_are_excluded():
    layers = [
        make_layer("a", 10, 10, 20, 20),
        make_layer("hidden", 40, 10, 20, 20, visible=False),
        make_layer("group", 0, 0, 100, 100, kind="group"),
    ]

    result = GeometryAnalyzer().analyze(layers, 100, 100)

    assert result["spatialRelationships"] == []
    assert result["layoutHypotheses"] == []


def test_flex_confidence_drops_when_few_siblings_are_covered():
    siblings = [make_layer("a", 0, 0, 10, 10), make_layer("b", 20, 0, 10, 10)]
    siblings += [
        make_layer(f"other-{index}", 0, 100 + index * 40, 10, 10)
        for index in range(9)
    ]
    spacing = {
        "id": "spacing-root-horizontal-0",
        "direction": "horizontal",
        "layer_ids": ["a", "b"],
        "gap_px": 10,
        "gap_variance_px": 0,
    }

    hypotheses = LayoutDetector().detect(
        siblings, None, (0, 0, 500, 500), [], [spacing], 500
    )
    flex = next(h for h in hypotheses if h["layout_type"] == "flex")

    assert flex["coverage_ratio"] == pytest.approx(2 / 11, abs=0.001)
    assert flex["confidence"] < 0.5


def test_flex_confidence_stays_high_for_full_coverage():
    siblings = [
        make_layer("a", 0, 0, 10, 10),
        make_layer("b", 20, 0, 10, 10),
        make_layer("c", 40, 0, 10, 10),
    ]
    spacing = {
        "id": "spacing-root-horizontal-0",
        "direction": "horizontal",
        "layer_ids": ["a", "b", "c"],
        "gap_px": 10,
        "gap_variance_px": 0,
    }

    hypotheses = LayoutDetector().detect(
        siblings, None, (0, 0, 100, 100), [], [spacing], 100
    )
    flex = next(h for h in hypotheses if h["layout_type"] == "flex")

    assert flex["coverage_ratio"] == 1.0
    assert flex["confidence"] > 0.9


def test_neighbors_are_limited_to_the_targets_siblings():
    root = make_layer("background", 0, 0, 100, 100)
    group = make_layer("group", 10, 10, 50, 50, kind="group")
    first = make_layer("a", 20, 20, 10, 10, parent_id="group")
    second = make_layer("b", 40, 20, 10, 10, parent_id="group")

    neighbors = GeometryAnalyzer().relationships_for(
        [root, group, first, second], "a", 200
    )

    assert {item["target_layer_id"] for item in neighbors} == {"b"}


def test_neighbors_for_returns_reciprocal_direction():
    layers = [
        make_layer("a", 20, 40, 60, 30),
        make_layer("b", 96, 40, 60, 30),
    ]

    neighbors = GeometryAnalyzer().relationships_for(layers, "a", 100)

    assert len(neighbors) == 1
    assert neighbors[0]["source_layer_id"] == "a"
    assert neighbors[0]["target_layer_id"] == "b"
    assert neighbors[0]["relative_position"] == "right"
    assert neighbors[0]["distance_px"] == 16.0
