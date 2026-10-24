"""Layout hypothesis detection (flex / grid / absolute candidates).

Hypotheses are inferences, not native PSD values. Every hypothesis carries
evidence and a confidence score, and never overwrites measured geometry.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..models.geometry import LayoutEvidence, LayoutHypothesis
from .geometry_engine import Rect, layer_rect


def _center(rect: Rect, axis: str) -> float:
    return rect[0] + rect[2] / 2 if axis == "horizontal" else rect[1] + rect[3] / 2


def _clusters(
    items: Sequence[Tuple[Dict[str, Any], float]], tolerance: float
) -> List[List[Tuple[Dict[str, Any], float]]]:
    clusters: List[List[Tuple[Dict[str, Any], float]]] = []
    for layer, value in sorted(items, key=lambda item: item[1]):
        if clusters and abs(value - sum(v for _, v in clusters[-1]) / len(clusters[-1])) <= tolerance:
            clusters[-1].append((layer, value))
        else:
            clusters.append([(layer, value)])
    return clusters


class LayoutDetector:
    """Detect candidate flex/grid layouts from measured alignment and spacing."""

    def __init__(self, tolerance_px: float = 2.0, min_overlap_ratio: float = 0.3):
        self.tolerance_px = tolerance_px
        self.min_overlap_ratio = min_overlap_ratio

    def detect(
        self,
        siblings: Sequence[Dict[str, Any]],
        parent_id: Optional[str],
        parent_bounds: Rect,
        alignments: Sequence[Dict[str, Any]],
        spacings: Sequence[Dict[str, Any]],
        document_width: float,
    ) -> List[Dict[str, Any]]:
        if len(siblings) < 2:
            return []

        hypotheses: List[Dict[str, Any]] = []
        grid_members: set = set()

        grid = self._grid_hypothesis(siblings, parent_id, parent_bounds, alignments, spacings)
        if grid is not None:
            hypotheses.append(grid)
            grid_members = set(grid["layers_involved"])

        for direction in ("horizontal", "vertical"):
            candidates = [item for item in spacings if item.get("direction") == direction]
            for candidate in candidates:
                layer_ids = list(candidate.get("layer_ids", []))
                if len(layer_ids) < 2 or set(layer_ids).issubset(grid_members):
                    continue
                hypothesis = self._flex_hypothesis(
                    siblings, parent_id, parent_bounds, candidate, alignments, document_width
                )
                if hypothesis is not None:
                    hypotheses.append(hypothesis)

        if not hypotheses:
            absolute = self._absolute_hypothesis(siblings, parent_id)
            if absolute is not None:
                hypotheses.append(absolute)

        return hypotheses

    # -- flex ------------------------------------------------------------

    def _flex_hypothesis(
        self,
        siblings: Sequence[Dict[str, Any]],
        parent_id: Optional[str],
        parent_bounds: Rect,
        spacing_group: Dict[str, Any],
        alignments: Sequence[Dict[str, Any]],
        document_width: float,
    ) -> Optional[Dict[str, Any]]:
        direction = spacing_group["direction"]
        axis = "horizontal" if direction == "horizontal" else "vertical"
        cross_axis = "vertical" if direction == "horizontal" else "horizontal"
        layer_ids = list(spacing_group.get("layer_ids", []))
        by_id = {layer["id"]: layer for layer in siblings}
        members = [by_id[layer_id] for layer_id in layer_ids if layer_id in by_id]
        if len(members) < 2:
            return None

        rects = [layer_rect(layer) for layer in members]
        centers = [_center(rect, cross_axis) for rect in rects]
        mean_center = sum(centers) / len(centers)
        deviation = max(abs(center - mean_center) for center in centers)
        alignment_strength = max(0.0, 1.0 - deviation / max(self.tolerance_px, 0.001))
        spacing_strength = max(
            0.0,
            1.0 - float(spacing_group.get("gap_variance_px", 0.0)) / max(self.tolerance_px, 0.001),
        )

        involved_alignments = [
            item["id"]
            for item in alignments
            if set(layer_ids).issubset(set(item.get("layer_ids", [])))
            and item.get("alignment_type")
            in (
                ("top", "bottom", "center_vertical")
                if direction == "horizontal"
                else ("left", "right", "center_horizontal")
            )
        ]

        evidence = [
            LayoutEvidence(
                evidence_type="spacing",
                strength=round(spacing_strength, 3),
                contributing_groups=[spacing_group["id"]],
                contributing_layers=layer_ids,
                metrics={"gap_px": spacing_group.get("gap_px"), "variance_px": spacing_group.get("gap_variance_px")},
            ).model_dump(mode="json"),
            LayoutEvidence(
                evidence_type="alignment",
                strength=round(alignment_strength, 3),
                contributing_groups=involved_alignments,
                contributing_layers=layer_ids,
                metrics={"max_center_deviation_px": round(deviation, 2)},
            ).model_dump(mode="json"),
        ]
        gap = float(spacing_group.get("gap_px", 0.0))
        justify = self._justify_content(members, parent_bounds, axis)
        conflicts = [
            layer["id"] for layer in siblings if layer["id"] not in layer_ids
        ]
        # A spacing run covering few siblings is weak evidence for the parent layout.
        coverage = len(layer_ids) / len(siblings)
        coverage_factor = 0.25 + 0.75 * coverage
        confidence = min(
            0.95,
            (0.5 + 0.25 * spacing_strength + 0.2 * alignment_strength)
            * coverage_factor,
        )

        frame = LayoutHypothesis(
            id=f"layout-{parent_id or 'root'}-flex-{direction}",
            layout_type="flex",
            confidence=round(confidence, 3),
            layers_involved=layer_ids,
            coverage_ratio=round(coverage, 3),
            evidence=evidence,
            conflicts=conflicts,
            css_recommendation={
                "display": "flex",
                "flex-direction": "row" if direction == "horizontal" else "column",
                "gap": f"{gap}px",
                "justify-content": justify,
                "align-items": "center",
            },
            flex_direction="row" if direction == "horizontal" else "column",
            flex_wrap="nowrap",
            justify_content=justify,
            align_items="center",
            gap_x_px=gap if direction == "horizontal" else None,
            gap_y_px=gap if direction == "vertical" else None,
        )
        result = frame.model_dump(mode="json")
        result["basis"] = "measured_geometry"
        result["notes"] = ["Layout candidate inferred from geometry; not a native PSD property."]
        return result

    def _justify_content(
        self, members: Sequence[Dict[str, Any]], parent_bounds: Rect, axis: str
    ) -> str:
        rects = [layer_rect(layer) for layer in members]
        if axis == "horizontal":
            first = min(rect[0] for rect in rects)
            last = max(rect[0] + rect[2] for rect in rects)
            start = first - parent_bounds[0]
            end = (parent_bounds[0] + parent_bounds[2]) - last
        else:
            first = min(rect[1] for rect in rects)
            last = max(rect[1] + rect[3] for rect in rects)
            start = first - parent_bounds[1]
            end = (parent_bounds[1] + parent_bounds[3]) - last

        if abs(start - end) <= self.tolerance_px and start > self.tolerance_px:
            return "center"
        if start <= self.tolerance_px and end <= self.tolerance_px:
            return "space-between"
        return "flex-start"

    # -- grid ------------------------------------------------------------

    def _grid_hypothesis(
        self,
        siblings: Sequence[Dict[str, Any]],
        parent_id: Optional[str],
        parent_bounds: Rect,
        alignments: Sequence[Dict[str, Any]],
        spacings: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        rows = _clusters([(layer, _center(layer_rect(layer), "vertical")) for layer in siblings], self.tolerance_px)
        rows = [row for row in rows if len(row) >= 2]
        if len(rows) < 2:
            return None

        reference_row = sorted(rows[0], key=lambda item: layer_rect(item[0])[0])
        reference_centers = [_center(layer_rect(layer), "horizontal") for layer, _ in reference_row]

        for row in rows:
            if len(row) != len(reference_centers):
                return None
            centers = sorted(_center(layer_rect(layer), "horizontal") for layer, _ in row)
            if any(abs(a - b) > self.tolerance_px for a, b in zip(centers, reference_centers)):
                return None

        widths = [layer_rect(layer)[2] for row in rows for layer, _ in row]
        heights = [layer_rect(layer)[3] for row in rows for layer, _ in row]
        width_variance = max(widths) - min(widths)
        height_variance = max(heights) - min(heights)
        if width_variance > self.tolerance_px or height_variance > self.tolerance_px:
            return None

        gap_xs: List[float] = []
        for row in rows:
            ordered = sorted(row, key=lambda item: layer_rect(item[0])[0])
            for (left, _), (right, _) in zip(ordered, ordered[1:]):
                left_rect, right_rect = layer_rect(left), layer_rect(right)
                gap_xs.append(right_rect[0] - (left_rect[0] + left_rect[2]))
        gap_ys: List[float] = []
        ordered_rows = sorted(rows, key=lambda row: min(layer_rect(layer)[1] for layer, _ in row))
        for upper, lower in zip(ordered_rows, ordered_rows[1:]):
            upper_bottom = max(layer_rect(layer)[1] + layer_rect(layer)[3] for layer, _ in upper)
            lower_top = min(layer_rect(layer)[1] for layer, _ in lower)
            gap_ys.append(lower_top - upper_bottom)

        if not gap_xs or not gap_ys or min(gap_xs) < 0 or min(gap_ys) < 0:
            return None

        gap_x = sum(gap_xs) / len(gap_xs)
        gap_y = sum(gap_ys) / len(gap_ys)
        gap_strength = max(
            0.0,
            1.0
            - (max(gap_xs) - min(gap_xs) + max(gap_ys) - min(gap_ys))
            / max(self.tolerance_px * 2, 0.001),
        )
        size_strength = max(
            0.0,
            1.0 - (width_variance + height_variance) / max(self.tolerance_px * 2, 0.001),
        )
        layer_ids = [layer["id"] for row in rows for layer, _ in row]
        coverage = len(layer_ids) / len(siblings)
        coverage_factor = 0.25 + 0.75 * coverage
        confidence = min(
            0.95,
            (0.55 + 0.2 * size_strength + 0.2 * gap_strength) * coverage_factor,
        )

        evidence = [
            LayoutEvidence(
                evidence_type="repetition",
                strength=round(gap_strength, 3),
                contributing_groups=[item["id"] for item in spacings if item.get("direction") in ("horizontal", "vertical")],
                contributing_layers=layer_ids,
                metrics={"rows": len(rows), "columns": len(reference_centers), "gap_x_px": round(gap_x, 2), "gap_y_px": round(gap_y, 2)},
            ).model_dump(mode="json"),
            LayoutEvidence(
                evidence_type="size_consistency",
                strength=round(size_strength, 3),
                contributing_groups=[],
                contributing_layers=layer_ids,
                metrics={"width_variance_px": round(width_variance, 2), "height_variance_px": round(height_variance, 2)},
            ).model_dump(mode="json"),
        ]

        hypothesis = LayoutHypothesis(
            id=f"layout-{parent_id or 'root'}-grid",
            layout_type="grid",
            confidence=round(confidence, 3),
            layers_involved=layer_ids,
            coverage_ratio=round(coverage, 3),
            evidence=evidence,
            conflicts=[layer["id"] for layer in siblings if layer["id"] not in layer_ids],
            css_recommendation={
                "display": "grid",
                "grid-template-columns": f"repeat({len(reference_centers)}, 1fr)",
                "gap": f"{round(gap_y, 2)}px {round(gap_x, 2)}px",
            },
            grid_columns=len(reference_centers),
            grid_rows=len(rows),
            gap_x_px=round(gap_x, 2),
            gap_y_px=round(gap_y, 2),
        )
        result = hypothesis.model_dump(mode="json")
        result["basis"] = "measured_geometry"
        result["notes"] = ["Layout candidate inferred from geometry; not a native PSD property."]
        return result

    # -- absolute --------------------------------------------------------

    def _absolute_hypothesis(
        self, siblings: Sequence[Dict[str, Any]], parent_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        hypothesis = LayoutHypothesis(
            id=f"layout-{parent_id or 'root'}-absolute",
            layout_type="absolute",
            confidence=0.2,
            layers_involved=[layer["id"] for layer in siblings],
            coverage_ratio=1.0,
            evidence=[],
            conflicts=["no consistent flex/grid alignment or spacing evidence"],
        )
        result = hypothesis.model_dump(mode="json")
        result["basis"] = "measured_geometry"
        result["notes"] = ["Fallback candidate only; do not treat absolute positioning as confirmed."]
        return result
