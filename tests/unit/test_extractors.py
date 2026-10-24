"""Unit tests for native typography and appearance extraction."""

from types import SimpleNamespace

from psd_tools.constants import Tag

from psd_inspector.extractors.appearance import extract_appearance
from psd_inspector.extractors.typography import extract_typography
from psd_inspector.pipeline import DesignIRPipeline


def _style(font, size, color, **extra):
    data = {
        "Font": font,
        "FontSize": size,
        "FauxBold": False,
        "FauxItalic": False,
        "AutoLeading": True,
        "Leading": 0.01,
        "Tracking": 0,
        "AutoKerning": True,
        "Kerning": 0,
        "Underline": False,
        "Strikethrough": False,
        "Ligatures": True,
        "DLigatures": False,
        "CharacterDirection": 0,
        "FillColor": {"Type": 1, "Values": list(color)},
    }
    data.update(extra)
    return {"StyleSheet": {"StyleSheetData": data}}


class FakeTypeLayer:
    kind = "type"
    text = "A\U0001F600B\n\u7b2c\u4e8c\u884c"
    text_type = SimpleNamespace(value=1)
    bbox = (10, 20, 210, 80)
    transform = (1.0, 0.0, 0.0, 1.0, 10.0, 20.0)
    effects = []

    engine_dict = {
        "StyleRun": {
            "DefaultRunData": {"StyleSheet": {"StyleSheetData": {}}},
            "RunLengthArray": [3, 1, 1, 3],
            "RunArray": [
                _style(
                    0,
                    10,
                    [1.0, 0.5, 0.0, 0.25],
                    Tracking=100,
                    AutoKerning=False,
                    Kerning=20,
                ),
                _style(1, 20, [1.0, 1.0, 1.0, 1.0], FauxBold=True),
                _style(0, 10, [1.0, 1.0, 1.0, 1.0]),
                _style(1, 12, [1.0, 1.0, 1.0, 1.0]),
            ],
        },
        "ParagraphRun": {
            "RunLengthArray": [3, 1, 4],
            "RunArray": [
                {
                    "ParagraphSheet": {
                        "DefaultStyleSheet": 0,
                        "Properties": {
                            "Justification": 2,
                            "AutoLeading": 1.5,
                            "FirstLineIndent": 12.0,
                            "StartIndent": 0.0,
                            "EndIndent": 0.0,
                            "SpaceBefore": 0.0,
                            "SpaceAfter": 0.0,
                        },
                    }
                },
                {
                    "ParagraphSheet": {
                        "DefaultStyleSheet": 0,
                        "Properties": {"Justification": 6, "AutoLeading": 1.2},
                    }
                },
                {
                    "ParagraphSheet": {
                        "DefaultStyleSheet": 0,
                        "Properties": {
                            "Justification": 0,
                            "AutoLeading": 1.2,
                            "StartIndent": 6.0,
                        },
                    }
                },
            ],
        },
    }
    resource_dict = {
        "FontSet": [
            {"Name": "'MyriadPro-Regular'"},
            {"Name": "PingFangSC-Bold"},
        ],
        "StyleSheetSet": [
            {"Name": "Normal", "StyleSheetData": {"FontSize": 12.0}}
        ],
        "ParagraphSheetSet": [],
    }

    def has_effects(self):
        return False


def test_typography_runs_offsets_fonts_and_paragraphs():
    payload, warnings = extract_typography(FakeTypeLayer(), dpi=144.0)

    assert warnings == []
    assert payload["content"] == "A\U0001F600B\n\u7b2c\u4e8c\u884c"
    assert payload["total_characters"] == 7
    assert payload["total_lines"] == 2
    assert payload["orientation"] == "horizontal"
    assert payload["text_box"]["auto_wrap"] is True
    assert payload["text_box"]["width_px"] == 200.0

    runs = payload["character_runs"]
    assert [run["content"] for run in runs] == [
        "A\U0001F600",
        "B",
        "\n",
        "\u7b2c\u4e8c\u884c",
    ]
    assert [(run["start"], run["end"]) for run in runs] == [(0, 2), (2, 3), (3, 4), (4, 7)]
    assert [run["paragraph_index"] for run in runs] == [0, 1, 2, 2]

    first = runs[0]
    assert first["font"]["family"] == "MyriadPro"
    assert first["font"]["post_script_name"] == "MyriadPro-Regular"
    assert first["font"]["weight"] == "normal"
    assert first["source_font_size"]["value"] == 10.0
    assert first["source_font_size"]["converted_px"] == 20.0
    assert first["source_font_size"]["conversion_basis"] == "144 DPI (pt -> px)"
    assert first["color"] == "#800040"
    assert first["opacity"] == 1.0
    assert first["tracking"] == 100.0
    assert first["kerning"] == 20.0
    assert first["letter_spacing_px"] == 2.0

    second = runs[1]
    assert second["font"]["family"] == "PingFangSC"
    assert second["font"]["style"] == "Bold"
    assert second["font"]["weight"] == "bold"
    assert second["font"]["is_bold"] is True

    paragraphs = payload["paragraph_runs"]
    assert paragraphs[0]["alignment"] == "center"
    assert paragraphs[0]["line_height_px"] == 30.0
    assert paragraphs[0]["line_height_percent"] == 150.0
    assert paragraphs[0]["first_line_indent_px"] == 24.0
    assert paragraphs[1]["alignment"] == "justified_last_line"
    assert paragraphs[1]["justified_last_line"] is True
    assert paragraphs[2]["alignment"] == "left"
    assert paragraphs[2]["left_indent_px"] == 12.0

    assert payload["dominant_font_family"] == "PingFangSC"
    assert payload["dominant_font_size_px"] == 20.0


def test_typography_resolves_style_sheet_index_and_missing_font():
    layer = FakeTypeLayer()
    layer.text = "Hi"
    layer.text_type = SimpleNamespace(value=0)
    layer.engine_dict = {
        "StyleRun": {
            "RunLengthArray": [2],
            "RunArray": [0],
        },
        "ParagraphRun": {"RunLengthArray": [2], "RunArray": []},
    }
    layer.resource_dict = {
        "FontSet": [{"Name": "HelveticaNeue-Light"}],
        "StyleSheetSet": [
            {
                "Name": "Normal",
                "StyleSheetData": {
                    "Font": 0,
                    "FontSize": 12.0,
                    "FillColor": {"Type": 1, "Values": [1.0, 0.1, 0.2, 0.3]},
                },
            }
        ],
        "ParagraphSheetSet": [],
    }

    payload, warnings = extract_typography(layer, dpi=72.0)

    run = payload["character_runs"][0]
    assert run["content"] == "Hi"
    assert run["font"]["family"] == "HelveticaNeue"
    assert run["source_font_size"]["value"] == 12.0
    assert run["color"] == "#1A334D"
    assert payload["text_box"]["auto_wrap"] is False
    assert payload["total_lines"] == 1
    assert warnings == []

    layer.engine_dict["StyleRun"]["RunArray"] = [
        _style(5, 12, [1.0, 1.0, 1.0, 1.0])
    ]
    _, warnings = extract_typography(layer, dpi=72.0)
    assert any("missing font index" in warning for warning in warnings)


# -- appearance ----------------------------------------------------------


class FakeStrokeSettings:
    content = {b"Clr ": {b"Rd  ": 35.0, b"Grn ": 35.0, b"Bl  ": 255.0}}
    fill_enabled = True
    enabled = True
    line_width = 2.0
    line_alignment = "inside"
    opacity = 100.0


class RoundedRectangle:
    radii = {
        b"unitValueQuadVersion": 1,
        b"topLeft": 8.0,
        b"topRight": 12.0,
        b"bottomRight": 8.0,
        b"bottomLeft": 12.0,
    }


class FakeTaggedBlocks:
    def __init__(self, fill):
        self._fill = fill

    def get_data(self, tag):
        assert tag == Tag.VECTOR_STROKE_CONTENT_DATA
        return self._fill


class DropShadow:
    size = 76.0
    choke = 10.0
    distance = 50.0
    angle = 90.0
    opacity = 14.0
    noise = 0.0
    enabled = True
    use_global_light = False
    color = {b"Rd  ": 255.0, b"Grn ": 160.0, b"Bl  ": 124.0}


class GradientOverlay:
    gradient = {
        b"Clrs": [
            {b"Clr ": {b"Rd  ": 195.0, b"Grn ": 68.0, b"Bl  ": 83.0}, b"Lctn": 0},
            {b"Clr ": {b"Rd  ": 128.0, b"Grn ": 0.0, b"Bl  ": 32.0}, b"Lctn": 4096},
        ],
        b"Trns": [
            {b"Opct": 100.0, b"Lctn": 0},
            {b"Opct": 50.0, b"Lctn": 4096},
        ],
    }
    type = b"Lnr "
    angle = 180.0
    scale = 100.0
    opacity = 100.0
    blend_mode = b"normal"
    enabled = True


class BevelEmboss:
    enabled = True


class FakeShapeLayer:
    kind = "shape"
    stroke = FakeStrokeSettings()
    origination = [RoundedRectangle()]
    effects = [DropShadow(), GradientOverlay(), BevelEmboss()]

    def __init__(self, fill):
        self.tagged_blocks = FakeTaggedBlocks(fill)

    def has_effects(self):
        return True


def test_appearance_extracts_vector_fill_stroke_radii_and_effects():
    fill = {b"Clr ": {b"Rd  ": 54.0, b"Grn ": 54.0, b"Bl  ": 54.0}}
    appearance, warnings, unsupported = extract_appearance(FakeShapeLayer(fill))

    assert appearance["fills"][0]["solid_color"] == "#363636"
    assert appearance["strokes"][0] == {
        "width_px": 2.0,
        "color": "#2323FF",
        "opacity": 1.0,
        "position": "inside",
        "visible": True,
    }
    assert appearance["border_radius"] == {
        "top_left": 8.0,
        "top_right": 12.0,
        "bottom_right": 8.0,
        "bottom_left": 12.0,
        "uniform": False,
    }

    shadow = appearance["drop_shadow"]
    assert shadow["color"] == "#FFA07C"
    assert shadow["opacity"] == 0.14
    assert shadow["spread_px"] == 7.6
    assert shadow["enabled"] is True
    assert any("choke" in warning for warning in warnings)

    overlay = appearance["gradient_overlay"]
    assert overlay["gradient_type"] == "linear"
    assert [stop["offset"] for stop in overlay["gradient_stops"]] == [0.0, 1.0]
    assert [stop["color"] for stop in overlay["gradient_stops"]] == [
        "#C34453",
        "#800020",
    ]
    assert [stop["opacity"] for stop in overlay["gradient_stops"]] == [1.0, 0.5]

    assert unsupported == ["BevelEmboss"]


def test_appearance_reports_non_solid_vector_fill():
    appearance, warnings, unsupported = extract_appearance(FakeShapeLayer({}))

    assert appearance["fills"] == []
    assert "vector_gradient_fill" in unsupported
    assert any("not a solid color" in warning for warning in warnings)


def test_layer_conversion_attaches_typography_and_warnings():
    raw = {
        "id": "layer-1",
        "name": "Title",
        "kind": "text",
        "bounds": {"x": 10, "y": 20, "width": 200, "height": 60},
        "appearance": {"fills": [], "strokes": [], "border_radius": {}},
        "typography": extract_typography(FakeTypeLayer(), dpi=72.0)[0],
        "typography_warnings": ["Example warning."],
    }

    layer = DesignIRPipeline()._convert_raw_to_layer(raw, 400, 300)

    assert layer.typography is not None
    assert layer.typography.character_runs[0].color == "#800040"
    assert layer.extraction.warnings == ["Example warning."]
    assert "typography.character_runs" in layer.extraction.property_sources
