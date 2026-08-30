"""Colour spans: which characters take which colour.

The span arithmetic is pure -- no renderer, no font -- and is tested as such.
The mobject-level tests below import manim lazily, the way the shaping tests
do, and need a font that actually ligates for the ligature cases.
"""

from __future__ import annotations

import logging

import pytest
from conftest import needs_hoefler, needs_new_york

from miramesa.spans import ColorSpan, color_table, spans_from_mapping

TEXT = "Hello World"


# -- the span arithmetic -----------------------------------------------------


def test_span_bounds_are_python_slice_bounds():
    length = len(TEXT)
    assert ColorSpan(6, 11, "red").resolve(length) == (6, 11)
    assert ColorSpan(6, None, "red").resolve(length) == (6, 11)
    assert ColorSpan(-5, None, "red").resolve(length) == (6, 11)
    assert ColorSpan(0, 99, "red").resolve(length) == (0, 11)  # clamps, not raises
    assert ColorSpan(8, 3, "red").resolve(length) == (8, 8)  # empty, never backwards


def test_a_later_span_wins_where_two_overlap():
    spans = [ColorSpan(0, 4, "red"), ColorSpan(2, 6, "blue")]
    assert color_table("abcdef", spans, "black") == ["red"] * 2 + ["blue"] * 4


def test_characters_no_span_covers_keep_the_default():
    assert color_table("abc", [], "black") == ["black"] * 3


def test_a_substring_colours_every_occurrence():
    spans = spans_from_mapping("banana", {"an": "red"})
    assert [span.resolve(6) for span in spans] == [(1, 3), (3, 5)]


def test_slice_keys_index_the_source_string():
    """Whitespace included -- the indices `cluster` and `chars` already use."""
    for key, expected in (
        ("[3:7]", (3, 7)),
        ("[:5]", (0, 5)),
        ("[6:]", (6, 11)),
        ("[-5:]", (6, 11)),
    ):
        (span,) = spans_from_mapping(TEXT, {key: "red"})
        assert span.resolve(len(TEXT)) == expected, key


def test_a_substring_that_never_occurs_is_reported(caplog):
    """Nearly always a typo, and silence would leave nothing to go on."""
    with caplog.at_level(logging.WARNING, logger="miramesa"):
        assert spans_from_mapping(TEXT, {"Wrold": "red"}) == []
    assert "does not occur" in caplog.text


def test_an_empty_t2c_key_is_rejected():
    with pytest.raises(ValueError, match="substring"):
        spans_from_mapping(TEXT, {"": "red"})


# -- the mobject ------------------------------------------------------------


def build(**kwargs):
    from manim import tempconfig

    from miramesa import GlyphText

    with tempconfig({"pixel_width": 1920, "frame_width": 1920 / 72}):
        return GlyphText(**kwargs)


@needs_new_york
def test_spans_colour_the_fill_and_the_darkening_stroke():
    """The stroke is what grows the outline, so it takes the span colour too.

    A glyph whose fill turned red but whose stroke stayed black would render
    with a black halo the width of the stem darkening.
    """
    from manim import BLACK, RED

    text = build(text=TEXT, font="New York", size=44, t2c={"World": RED})
    for glyph in text.submobjects:
        expected = RED if glyph.cluster >= 6 else BLACK
        assert glyph.get_fill_color() == expected
        assert glyph.get_stroke_color() == expected
    widths = {round(glyph.stroke_width, 6) for glyph in text.submobjects}
    assert len(widths) == 1 and widths.pop() > 0, "darkening must stay uniform"


@needs_new_york
def test_spans_and_t2c_agree_and_t2c_wins_on_an_overlap():
    from manim import BLUE, RED

    text = build(
        text=TEXT,
        font="New York",
        size=44,
        spans=[ColorSpan(0, 11, RED)],
        t2c={"[6:]": BLUE},
    )
    assert all(glyph.get_fill_color() == RED for glyph in text.chars(0, 5))
    assert all(glyph.get_fill_color() == BLUE for glyph in text.chars(6, 11))


@needs_new_york
def test_set_span_color_keeps_the_stroke_width():
    from manim import BLUE

    text = build(text=TEXT, font="New York", size=44)
    before = [glyph.stroke_width for glyph in text.submobjects]
    assert text.set_span_color(6, None, BLUE) is text, "must chain and animate"
    assert [glyph.stroke_width for glyph in text.submobjects] == before
    assert all(glyph.get_fill_color() == BLUE for glyph in text.chars(6, 11))
    assert all(glyph.get_stroke_color() == BLUE for glyph in text.chars(6, 11))


@needs_new_york
def test_set_color_by_text_recolours_every_occurrence():
    from manim import GREEN

    text = build(text="banana", font="New York", size=44)
    text.set_color_by_text("an", GREEN)
    coloured = [g.cluster for g in text.submobjects if g.get_fill_color() == GREEN]
    assert coloured == [1, 2, 3, 4]


@needs_hoefler
def test_a_span_ending_inside_a_ligature_is_reported(caplog):
    """ "ffi" is one glyph, so it can only take one colour -- say so."""
    from manim import RED

    with caplog.at_level(logging.WARNING, logger="miramesa"):
        text = build(text="office", font="Hoefler Text", size=44, t2c={"[0:3]": RED})
    assert "'ffi'" in caplog.text and "ligatures=False" in caplog.text
    assert len(text.submobjects) == 4, "o, ffi, c, e"


@needs_hoefler
def test_recolouring_across_a_ligature_is_reported_too(caplog):
    """The warning cannot be a construction-time-only courtesy.

    `set_span_color(0, 3, ...)` reaches the same undividable "ffi" glyph the
    constructor warns about, and widens the recoloured range the same way.
    """
    from manim import RED

    text = build(text="office", font="Hoefler Text", size=44)
    with caplog.at_level(logging.WARNING, logger="miramesa"):
        text.set_span_color(0, 3, RED)
    assert "'ffi'" in caplog.text and "ligatures=False" in caplog.text


@needs_hoefler
def test_recolouring_along_a_ligature_boundary_is_quiet(caplog):
    """Only a bound *inside* a glyph is a problem; "o" and "ffi" divide fine."""
    from manim import RED

    text = build(text="office", font="Hoefler Text", size=44)
    with caplog.at_level(logging.WARNING, logger="miramesa"):
        text.set_span_color(0, 4, RED)
    assert caplog.text == ""


@needs_hoefler
def test_ligatures_false_gives_every_character_its_own_glyph(caplog):
    from manim import BLACK, RED

    with caplog.at_level(logging.WARNING, logger="miramesa"):
        text = build(
            text="office",
            font="Hoefler Text",
            size=44,
            t2c={"[0:3]": RED},
            ligatures=False,
        )
    assert "ligature" not in caplog.text
    assert [glyph.cluster for glyph in text.submobjects] == [0, 1, 2, 3, 4, 5]
    assert text.submobjects[3].get_fill_color() == BLACK, "the 'i' is outside [0:3]"
