"""Shaping-level tests: no renderer involved."""

from __future__ import annotations

import logging

import pytest
from conftest import needs_new_york

from miramesa import FontSpec, get_backend

TEXT = "Hello World"


@pytest.fixture(scope="module")
def backend():
    return get_backend("coretext")


@needs_new_york
def test_optical_size_follows_the_point_size(backend):
    """The whole point of the package: outlines must change with the size.

    Pinned outlines are what manim's Pango path gets wrong, so this asserts the
    shape of the glyphs actually differs between a text size and a display one.
    """
    small = backend.shape(TEXT, FontSpec.of("New York", 128, {"opsz": 12}))
    display = backend.shape(TEXT, FontSpec.of("New York", 128, {"opsz": 256}))
    auto = backend.shape(TEXT, FontSpec.of("New York", 128))

    # higher optical sizes are narrower
    assert display.advance < auto.advance < small.advance
    # ... and "auto" must land on the point size, not at an axis end
    at_128 = backend.shape(TEXT, FontSpec.of("New York", 128, {"opsz": 128}))
    assert auto.advance == pytest.approx(at_128.advance, abs=0.01)


@needs_new_york
def test_metrics_are_in_pixels(backend):
    line = backend.shape(TEXT, FontSpec.of("New York", 128))
    assert line.ascent / 128 == pytest.approx(0.9521, abs=1e-3)
    assert line.advance == pytest.approx(631.08, abs=0.1)
    assert line.line_height == pytest.approx(line.ascent + line.descent, abs=1e-6)


@needs_new_york
def test_clusters_index_the_source_string(backend):
    line = backend.shape(TEXT, FontSpec.of("New York", 44))
    # the space at index 5 produces no outline, every other character does
    assert [g.cluster for g in line.glyphs] == [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]


@needs_new_york
def test_clusters_count_code_points_not_utf16_units(backend):
    """Core Text indexes an NSString, which counts UTF-16 code units.

    One astral character occupies two of them, so without the translation
    every cluster after an emoji is off by one and slicing by character
    position lands on the wrong glyph.
    """
    text = "a\U0001f600b"  # the emoji is one code point but two UTF-16 units
    line = backend.shape(text, FontSpec.of("New York", 44))
    # the emoji itself carries no outline here, so only "a" and "b" survive
    assert [g.cluster for g in line.glyphs] == [0, 2]
    assert text[line.glyphs[-1].cluster] == "b"


@needs_new_york
def test_tracking_makes_scaling_slightly_nonlinear(backend):
    """Apple fonts carry a `trak` table that tightens letterspacing as size grows.

    Core Text applies it, so doubling the point size gives slightly *less* than
    double the advance even with the optical size held still.  Nothing in the
    Pango stack does this, and it is worth a few percent on a headline.
    """
    small = backend.shape(TEXT, FontSpec.of("New York", 64, {"opsz": 64}))
    large = backend.shape(TEXT, FontSpec.of("New York", 128, {"opsz": 64}))
    assert large.advance < 2 * small.advance
    assert large.advance == pytest.approx(2 * small.advance, rel=5e-3)


@needs_new_york
def test_missing_font_warns_and_substitutes(backend, caplog):
    with caplog.at_level(logging.WARNING, logger="miramesa"):
        line = backend.shape(TEXT, FontSpec.of("New Yrok", 44))
    assert "not found" in caplog.text
    assert line.resolved_family != "New Yrok"
    assert line.glyphs, "the substitute must still produce glyphs"


@needs_new_york
def test_family_lookup_is_case_insensitive(backend, caplog):
    with caplog.at_level(logging.WARNING, logger="miramesa"):
        line = backend.shape(TEXT, FontSpec.of("new york", 44))
    assert line.resolved_family == "New York"
    assert "not found" not in caplog.text


def test_font_spec_is_hashable_and_normalised():
    a = FontSpec.of("New York", 44, {"wght": 600, "opsz": 44})
    b = FontSpec.of("New York", 44, {"opsz": 44, "wght": 600})
    assert a == b and hash(a) == hash(b)
    assert a.variation_dict == {"opsz": 44, "wght": 600}


@needs_new_york
def test_chars_addresses_glyphs_after_an_astral_character():
    """`chars` slices the Python string, so an emoji must not shift the rest."""
    from manim import tempconfig

    from miramesa import GlyphText

    with tempconfig({"pixel_width": 1920, "frame_width": 1920 / 72}):
        text = GlyphText("a\U0001f600b", font="New York", size=44)
    assert len(text.chars(2, 3).submobjects) == 1


@needs_new_york
def test_glyph_outlines_are_whole_curves():
    """Every glyph's point array must be a whole number of Bezier curves.

    Core Text's CGPath-to-NSBezierPath conversion tacks a stray `moveTo` onto
    the end of each glyph.  Emitting it leaves a dangling anchor that renders
    fine but breaks anything that walks the mobject's anchors -- `align_to`,
    bounding boxes of the family, TransformMatchingShapes.
    """
    from manim import tempconfig

    from miramesa import GlyphText

    with tempconfig({"pixel_width": 1920, "frame_width": 1920 / 72}):
        text = GlyphText("Hello World", font="New York", size=128)
    nppc = 4  # cubic Bezier
    for glyph in text.submobjects:
        assert len(glyph.points) % nppc == 0, (
            f"glyph at cluster {glyph.cluster} has {len(glyph.points)} points"
        )
