"""Unit tests for design token extraction."""

from psd_inspector.analysis.token_extractor import TokenExtractor


def make_layer(layer_id, fills=None, strokes=None, appearance=None):
    layer_appearance = {"fills": fills or [], "strokes": strokes or []}
    layer_appearance.update(appearance or {})
    return {"id": layer_id, "kind": "pixel", "appearance": layer_appearance}


def make_ir(layers, measurements):
    return {
        "source": {"rawLayers": layers},
        "analysis": {"measurements": measurements},
    }


def test_color_tokens_from_native_fills_and_samples():
    layers = [
        make_layer("layer-1", fills=[{"solid_color": "#246BFD", "visible": True}]),
        make_layer("layer-2", strokes=[{"color": "#246BFD", "visible": True, "width_px": 1}]),
        make_layer("layer-3"),
        make_layer("layer-4"),
    ]
    measurements = [
        {"type": "sampled_color", "layerId": "layer-3", "color": "#246BFD", "coverage": 0.9},
        {"type": "sampled_color", "layerId": "layer-3", "color": "#FFFFFF", "coverage": 0.95},
        {"type": "sampled_color", "layerId": "layer-4", "color": "#1A1A1A", "coverage": 0.8},
    ]

    result = TokenExtractor().extract(make_ir(layers, measurements), types=["colors"])
    tokens = {token["value"]["base"]: token for token in result["colorTokens"]}

    assert tokens["#246BFD"]["name"] == "primary"
    assert tokens["#246BFD"]["usage_count"] == 3
    assert tokens["#246BFD"]["is_recommended"] is True
    assert tokens["#FFFFFF"]["name"] == "backgroundPrimary"
    assert tokens["#1A1A1A"]["name"] == "textPrimary"
    assert any("statistical" in note for note in tokens["#246BFD"]["notes"])


def test_color_tokens_include_text_and_gradient_stops():
    text_layer = {
        "id": "text-1",
        "kind": "text",
        "appearance": {"fills": [], "strokes": []},
        "typography": {
            "character_runs": [
                {"content": "Hello", "color": "#FF0000", "opacity": 1.0}
            ]
        },
    }
    gradient_layer = make_layer(
        "shape-1",
        fills=[
            {
                "kind": "gradient",
                "visible": True,
                "solid_color": None,
                "gradient_stops": [{"color": "#00FF00"}, {"color": "#0000FF"}],
            }
        ],
        appearance={
            "gradient_overlay": {"gradient_stops": [{"color": "#FFFF00"}]}
        },
    )

    result = TokenExtractor().extract(
        make_ir([text_layer, gradient_layer], []), types=["colors"]
    )
    tokens = {token["value"]["base"]: token for token in result["colorTokens"]}

    assert set(tokens) == {"#FF0000", "#00FF00", "#0000FF", "#FFFF00"}
    assert any("native text" in note for note in tokens["#FF0000"]["notes"])
    assert any("gradient stop" in note for note in tokens["#00FF00"]["notes"])


def test_low_coverage_samples_are_ignored():
    measurements = [
        {"type": "sampled_color", "layerId": "layer-1", "color": "#FF00FF", "coverage": 0.2},
    ]

    result = TokenExtractor().extract(make_ir([make_layer("layer-1")], measurements), types=["colors"])

    assert result["colorTokens"] == []


def test_spacing_tokens_cluster_measurements():
    measurements = [
        {"type": "spacing_group", "gap_px": 16, "layer_ids": ["a", "b"]},
        {"type": "spacing_group", "gap_px": 17, "layer_ids": ["b", "c"]},
        {"type": "spacing_group", "gap_px": 24, "layer_ids": ["c", "d"]},
        {"type": "group_padding", "groupId": "g", "padding": {"top": 16, "left": 8}},
    ]

    result = TokenExtractor().extract(make_ir([], measurements), types=["spacing"])
    tokens = {token["value"]["base"]: token for token in result["spacingTokens"]}

    assert tokens["16.33"]["usage_count"] == 3
    assert tokens["24"]["usage_count"] == 1
    assert tokens["8"]["usage_count"] == 1


def test_border_and_shadow_tokens():
    layer = make_layer(
        "layer-1",
        strokes=[{"visible": True, "width_px": 2, "color": "#000000"}],
        appearance={
            "border_radius": {"top_left": 8, "top_right": 8, "bottom_right": 8, "bottom_left": 8},
            "drop_shadow": {
                "color": "#000000",
                "opacity": 0.15,
                "angle_deg": 90,
                "distance_px": 4,
                "spread_px": 0,
                "size_px": 12,
                "enabled": True,
            },
        },
    )

    result = TokenExtractor().extract(make_ir([layer], []), types=["borders", "shadows"])

    assert {token["value"]["base"] for token in result["borderTokens"]} == {"8", "2"}
    assert len(result["shadowTokens"]) == 1
    assert result["shadowTokens"][0]["value"]["base"].endswith("rgba(0, 0, 0, 0.15)")


def test_opaque_shadow_keeps_hex_color():
    layer = make_layer(
        "layer-1",
        appearance={
            "drop_shadow": {
                "color": "#B30004",
                "opacity": 1.0,
                "angle_deg": 90,
                "distance_px": 0,
                "spread_px": 0,
                "size_px": 4,
                "enabled": True,
            },
        },
    )

    result = TokenExtractor().extract(make_ir([layer], []), types=["shadows"])

    assert result["shadowTokens"][0]["value"]["base"].endswith("#B30004")


def test_typography_tokens_attribute_layers_per_value():
    def text_layer(layer_id, family, size, weight):
        return {
            "id": layer_id,
            "kind": "text",
            "appearance": {"fills": [], "strokes": []},
            "typography": {
                "character_runs": [
                    {
                        "font": {"family": family, "weight": weight},
                        "effective_font_size_px": size,
                        "color": "#000000",
                        "opacity": 1.0,
                    }
                ]
            },
        }

    layers = [
        text_layer("text-1", "Inter", 16, "regular"),
        text_layer("text-2", "Inter", 16, "regular"),
        text_layer("text-3", "Source Han Sans", 24, "bold"),
    ]

    result = TokenExtractor().extract(make_ir(layers, []), types=["typography"])
    tokens = {token["value"]["base"]: token for token in result["typographyTokens"]}

    assert tokens["16"]["source_layer_ids"] == ["text-1", "text-2"]
    assert tokens["24"]["source_layer_ids"] == ["text-3"]
    assert tokens["Inter"]["source_layer_ids"] == ["text-1", "text-2"]
    assert tokens["Source Han Sans"]["source_layer_ids"] == ["text-3"]
    assert tokens["regular"]["source_layer_ids"] == ["text-1", "text-2"]
    assert tokens["bold"]["source_layer_ids"] == ["text-3"]


def test_type_filter_only_returns_requested_groups():
    result = TokenExtractor().extract(make_ir([], []), types=["spacing"])

    assert result["colorTokens"] == []
    assert result["spacingTokens"] == []
    assert result["totalCount"] == 0
