"""Geometry analysis: measured relationships, alignment, spacing and padding.

All values produced here are deterministic measurements over layer bounds.
They are *measurements*, not layout guesses; layout inference lives in
``layout_detector``.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..models.geometry import AlignmentGroup, SpacingGroup, SpatialRelationship


Rect = Tuple[float, float, float, float]  # x, y, width, height


def layer_rect(layer: Dict[str, Any]) -> Rect:
    bounds = layer.get("geometry", {}).get("source_bounds", {})
    return (
        float(bounds.get("x", 0)),
        float(bounds.get("y", 0)),
        float(bounds.get("width", 0)),
        float(bounds.get("height", 0)),
    )


def is_visible_leaf(layer: Dict[str, Any]) -> bool:
    if not layer.get("visible", True):
        return False
    return layer.get("kind") not in ("group", "adjustment")


def _overlap(a: Rect, b: Rect) -> float:
    return max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    )


def _projection_overlap_ratio(a: Rect, b: Rect, axis: str) -> float:
    if axis == "horizontal":
        overlap = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
        shortest = min(a[2], b[2])
    else:
        overlap = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
        shortest = min(a[3], b[3])
    return overlap / shortest if shortest > 0 else 0.0


def _axis_gap(a: Rect, b: Rect, axis: str) -> float:
    """Positive gap when separated on axis, 0 when overlapping on that axis."""
    if axis == "horizontal":
        if b[0] >= a[0] + a[2]:
            return b[0] - (a[0] + a[2])
        if a[0] >= b[0] + b[2]:
            return a[0] - (b[0] + b[2])
        return 0.0
    if b[1] >= a[1] + a[3]:
        return b[1] - (a[1] + a[3])
    if a[1] >= b[1] + b[3]:
        return a[1] - (b[1] + b[3])
    return 0.0


def _relative_position(a: Rect, b: Rect, min_overlap_ratio: float) -> Tuple[str, float, bool]:
    """Describe where b sits relative to a and the edge distance."""
    overlap_area = _overlap(a, b)
    if overlap_area > 0:
        return "overlapping", 0.0, True

    gap_x = _axis_gap(a, b, "horizontal")
    gap_y = _axis_gap(a, b, "vertical")
    ratio_y = _projection_overlap_ratio(a, b, "vertical")
    ratio_x = _projection_overlap_ratio(a, b, "horizontal")

    if b[0] >= a[0] + a[2] and ratio_y >= min_overlap_ratio:
        return "right", gap_x, True
    if b[0] + b[2] <= a[0] and ratio_y >= min_overlap_ratio:
        return "left", gap_x, True
    if b[1] >= a[1] + a[3] and ratio_x >= min_overlap_ratio:
        return "below", gap_y, True
    if b[1] + b[3] <= a[1] and ratio_x >= min_overlap_ratio:
        return "above", gap_y, True

    distance = (gap_x**2 + gap_y**2) ** 0.5
    return "diagonal", distance, False


class GeometryAnalyzer:
    """Compute measured geometry facts for a set of IR layers."""

    def __init__(
        self,
        tolerance_px: float = 2.0,
        relative_tolerance: float = 0.005,
        min_overlap_ratio: float = 0.3,
        max_neighbor_distance: float = 100.0,
    ):
        self.tolerance_px = tolerance_px
        self.relative_tolerance = relative_tolerance
        self.min_overlap_ratio = min_overlap_ratio
        self.max_neighbor_distance = max_neighbor_distance

    def analyze(
        self,
        layers: Sequence[Dict[str, Any]],
        document_width: float,
        document_height: float,
    ) -> Dict[str, Any]:
        leaves = [layer for layer in layers if is_visible_leaf(layer)]
        measurements: List[Dict[str, Any]] = []
        relationships: List[Dict[str, Any]] = []
        hypotheses: List[Dict[str, Any]] = []

        for parent_id, siblings in self._siblings(leaves).items():
            if len(siblings) < 2:
                continue
            parent_bounds = self._parent_bounds(parent_id, layers, document_width, document_height)

            alignments = self._alignment_groups(siblings, parent_id)
            spacings = self._spacing_groups(siblings, parent_bounds, parent_id)
            measurements.extend(alignments)
            measurements.extend(spacings)

            for rel in self._relationships(siblings, self.max_neighbor_distance):
                relationships.append(rel.model_dump(mode="json"))

            hypotheses.extend(
                self._layout_hypotheses(
                    siblings, parent_id, parent_bounds, alignments, spacings, document_width
                )
            )

        measurements.extend(self._group_paddings(layers))

        return {
            "measurements": measurements,
            "spatialRelationships": relationships,
            "layoutHypotheses": hypotheses,
        }

    def relationships_for(
        self,
        layers: Sequence[Dict[str, Any]],
        layer_id: str,
        max_distance: float = 100.0,
    ) -> List[Dict[str, Any]]:
        """Measured relationships between one layer and nearby sibling layers."""
        leaves = [layer for layer in layers if is_visible_leaf(layer)]
        target = next((layer for layer in leaves if layer.get("id") == layer_id), None)
        if target is None:
            return []

        siblings = [
            layer for layer in leaves if layer.get("parent_id") == target.get("parent_id")
        ]
        target_rect = layer_rect(target)
        results: List[Dict[str, Any]] = []
        for other in siblings:
            if other is target:
                continue
            other_rect = layer_rect(other)
            # Cheap distance pre-filter before full classification.
            if _axis_gap(target_rect, other_rect, "horizontal") > max_distance:
                continue
            if _axis_gap(target_rect, other_rect, "vertical") > max_distance:
                continue

            if self._layer_order(target, other):
                source, src_rect, dst, dst_rect = target, target_rect, other, other_rect
            else:
                source, src_rect, dst, dst_rect = other, other_rect, target, target_rect

            position, distance, projection = _relative_position(
                src_rect, dst_rect, self.min_overlap_ratio
            )
            if distance > max_distance:
                continue
            if source is not target:
                position = self._invert_position(position)

            results.append(
                SpatialRelationship(
                    source_layer_id=layer_id,
                    target_layer_id=dst.get("id") if source is target else source.get("id"),
                    distance_px=round(distance, 2),
                    vector_x=round(other_rect[0] - target_rect[0], 2),
                    vector_y=round(other_rect[1] - target_rect[1], 2),
                    overlap_ratio=round(_overlap(target_rect, other_rect) / max(1.0, min(
                        target_rect[2] * target_rect[3], other_rect[2] * other_rect[3]
                    )), 3),
                    projection_overlap=projection,
                    relative_position=position,
                    is_neighbor=distance <= max_distance,
                ).model_dump(mode="json")
            )

        results.sort(key=lambda item: item["distance_px"])
        return results

    # -- grouping helpers ------------------------------------------------

    @staticmethod
    def _siblings(layers: Iterable[Dict[str, Any]]) -> Dict[Optional[str], List[Dict[str, Any]]]:
        grouped: Dict[Optional[str], List[Dict[str, Any]]] = {}
        for layer in layers:
            grouped.setdefault(layer.get("parent_id"), []).append(layer)
        return grouped

    @staticmethod
    def _parent_bounds(
        parent_id: Optional[str],
        layers: Sequence[Dict[str, Any]],
        document_width: float,
        document_height: float,
    ) -> Rect:
        if parent_id is None:
            return (0.0, 0.0, float(document_width), float(document_height))
        parent = next((layer for layer in layers if layer.get("id") == parent_id), None)
        if parent is None:
            return (0.0, 0.0, float(document_width), float(document_height))
        return layer_rect(parent)

    @staticmethod
    def _layer_order(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        """Deterministic ordering so pair results are stable."""
        return str(a.get("id")) < str(b.get("id"))

    @staticmethod
    def _invert_position(position: str) -> str:
        return {
            "left": "right",
            "right": "left",
            "above": "below",
            "below": "above",
        }.get(position, position)

    # -- alignment -------------------------------------------------------

    def _alignment_groups(
        self, siblings: Sequence[Dict[str, Any]], parent_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        metrics = {
            "left": ("vertical", lambda r: r[0]),
            "right": ("vertical", lambda r: r[0] + r[2]),
            "center_horizontal": ("vertical", lambda r: r[0] + r[2] / 2),
            "top": ("horizontal", lambda r: r[1]),
            "bottom": ("horizontal", lambda r: r[1] + r[3]),
            "center_vertical": ("horizontal", lambda r: r[1] + r[3] / 2),
        }

        groups: List[Dict[str, Any]] = []
        for name, (axis, getter) in metrics.items():
            values = sorted(
                ((layer, getter(layer_rect(layer))) for layer in siblings),
                key=lambda item: item[1],
            )
            clusters: List[List[Tuple[Dict[str, Any], float]]] = []
            for layer, value in values:
                if (
                    clusters
                    and abs(value - sum(v for _, v in clusters[-1]) / len(clusters[-1]))
                    <= self.tolerance_px
                ):
                    clusters[-1].append((layer, value))
                else:
                    clusters.append([(layer, value)])

            for index, cluster in enumerate(clusters):
                if len(cluster) < 2:
                    continue
                mean = sum(value for _, value in cluster) / len(cluster)
                group = AlignmentGroup(
                    id=f"align-{parent_id or 'root'}-{name}-{index}",
                    axis=axis,
                    alignment_type=name,
                    layer_ids=[layer["id"] for layer, _ in cluster],
                    tolerance_px=self.tolerance_px,
                    reference_position=round(mean, 2),
                )
                entry = group.model_dump(mode="json")
                entry["type"] = "alignment_group"
                entry["parentId"] = parent_id
                entry["source"] = "geometry_computed"
                entry["confidence"] = 1.0
                groups.append(entry)
        return groups

    # -- spacing ---------------------------------------------------------

    def _spacing_groups(
        self,
        siblings: Sequence[Dict[str, Any]],
        parent_bounds: Rect,
        parent_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = []
        for direction in ("horizontal", "vertical"):
            ordered = sorted(
                siblings,
                key=lambda layer: layer_rect(layer)[0] if direction == "horizontal" else layer_rect(layer)[1],
            )
            runs: List[List[Tuple[Dict[str, Any], float]]] = []
            for previous, current in zip(ordered, ordered[1:]):
                gap, valid = self._gap_between(previous, current, direction)
                if not valid:
                    runs.append([])
                    continue
                if not runs or not runs[-1]:
                    runs.append([(previous, gap), (current, gap)])
                elif abs(gap - runs[-1][-1][1]) <= self.tolerance_px:
                    runs[-1].append((current, gap))
                else:
                    runs.append([(previous, gap), (current, gap)])

            for index, run in enumerate(runs):
                if len(run) < 2:
                    continue
                layer_ids = [run[0][0]["id"]] + [layer["id"] for layer, _ in run[1:]]
                gaps = [gap for _, gap in run[1:]]
                if not gaps:
                    continue
                first_rect = layer_rect(run[0][0])
                last_rect = layer_rect(run[-1][0])
                if direction == "horizontal":
                    padding_start = first_rect[0] - parent_bounds[0]
                    padding_end = (parent_bounds[0] + parent_bounds[2]) - (last_rect[0] + last_rect[2])
                else:
                    padding_start = first_rect[1] - parent_bounds[1]
                    padding_end = (parent_bounds[1] + parent_bounds[3]) - (last_rect[1] + last_rect[3])

                group = SpacingGroup(
                    id=f"spacing-{parent_id or 'root'}-{direction}-{index}",
                    direction=direction,
                    layer_ids=layer_ids,
                    gap_px=round(sum(gaps) / len(gaps), 2),
                    gap_variance_px=round(max(gaps) - min(gaps), 2),
                    padding_start_px=round(padding_start, 2),
                    padding_end_px=round(padding_end, 2),
                )
                entry = group.model_dump(mode="json")
                entry["type"] = "spacing_group"
                entry["parentId"] = parent_id
                entry["source"] = "geometry_computed"
                entry["confidence"] = round(
                    max(0.0, 1.0 - group.gap_variance_px / max(self.tolerance_px, 0.001)), 3
                )
                groups.append(entry)
        return groups

    def _gap_between(
        self, a: Dict[str, Any], b: Dict[str, Any], direction: str
    ) -> Tuple[float, bool]:
        a_rect, b_rect = layer_rect(a), layer_rect(b)
        if direction == "horizontal":
            if b_rect[0] < a_rect[0] + a_rect[2]:
                return 0.0, False
            if _projection_overlap_ratio(a_rect, b_rect, "vertical") < self.min_overlap_ratio:
                return 0.0, False
            return b_rect[0] - (a_rect[0] + a_rect[2]), True

        if b_rect[1] < a_rect[1] + a_rect[3]:
            return 0.0, False
        if _projection_overlap_ratio(a_rect, b_rect, "horizontal") < self.min_overlap_ratio:
            return 0.0, False
        return b_rect[1] - (a_rect[1] + a_rect[3]), True

    # -- relationships ---------------------------------------------------

    def _relationships(
        self, layers: Sequence[Dict[str, Any]], max_distance: float
    ) -> List[SpatialRelationship]:
        results: List[SpatialRelationship] = []
        for i, a in enumerate(layers):
            for b in layers[i + 1 :]:
                a_rect, b_rect = layer_rect(a), layer_rect(b)
                position, distance, projection = _relative_position(
                    a_rect, b_rect, self.min_overlap_ratio
                )
                if distance > max_distance:
                    continue
                results.append(
                    SpatialRelationship(
                        source_layer_id=a["id"],
                        target_layer_id=b["id"],
                        distance_px=round(distance, 2),
                        vector_x=round(b_rect[0] - a_rect[0], 2),
                        vector_y=round(b_rect[1] - a_rect[1], 2),
                        overlap_ratio=round(
                            _overlap(a_rect, b_rect)
                            / max(1.0, min(a_rect[2] * a_rect[3], b_rect[2] * b_rect[3])),
                            3,
                        ),
                        projection_overlap=projection,
                        relative_position=position,
                        is_neighbor=distance <= max_distance,
                    )
                )
        return results

    # -- group padding ---------------------------------------------------

    def _group_paddings(self, layers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for layer in layers:
            parent_id = layer.get("parent_id")
            if parent_id is not None:
                by_parent.setdefault(parent_id, []).append(layer)

        measurements: List[Dict[str, Any]] = []
        for group in layers:
            if group.get("kind") != "group" or not group.get("visible", True):
                continue
            children = by_parent.get(group.get("id"))
            if not children:
                continue
            group_rect = layer_rect(group)
            if group_rect[2] <= 0 or group_rect[3] <= 0:
                continue
            left = min(layer_rect(child)[0] for child in children)
            top = min(layer_rect(child)[1] for child in children)
            right = max(layer_rect(child)[0] + layer_rect(child)[2] for child in children)
            bottom = max(layer_rect(child)[1] + layer_rect(child)[3] for child in children)
            measurements.append(
                {
                    "id": f"measurement-padding-{group['id']}",
                    "type": "group_padding",
                    "groupId": group["id"],
                    "padding": {
                        "top": round(top - group_rect[1], 2),
                        "right": round(group_rect[0] + group_rect[2] - right, 2),
                        "bottom": round(group_rect[1] + group_rect[3] - bottom, 2),
                        "left": round(left - group_rect[0], 2),
                    },
                    "source": "geometry_computed",
                    "confidence": 0.9,
                }
            )
        return measurements

    # -- layout candidate delegation -------------------------------------

    def _layout_hypotheses(
        self,
        siblings: Sequence[Dict[str, Any]],
        parent_id: Optional[str],
        parent_bounds: Rect,
        alignments: Sequence[Dict[str, Any]],
        spacings: Sequence[Dict[str, Any]],
        document_width: float,
    ) -> List[Dict[str, Any]]:
        from .layout_detector import LayoutDetector

        detector = LayoutDetector(
            tolerance_px=self.tolerance_px,
            min_overlap_ratio=self.min_overlap_ratio,
        )
        return detector.detect(
            siblings=siblings,
            parent_id=parent_id,
            parent_bounds=parent_bounds,
            alignments=alignments,
            spacings=spacings,
            document_width=document_width,
        )
