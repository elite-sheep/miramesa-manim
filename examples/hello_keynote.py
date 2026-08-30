"""Rebuild a Keynote slide in manim.

Two "Hello World" strings in New York on a 1920x1080 slide: 44pt with its text
box at (910, 510) and 128pt at (910, 570).

    manim -s examples/hello_keynote.py KeynoteSlide
    manim -s examples/hello_keynote.py ClassicAndMiramesa
"""

from __future__ import annotations

from manim import BLACK, BLUE, RED, WHITE, Scene, Text, Write, config

from miramesa import GlyphText, keynote, pixel_to_scene

PX_PER_UNIT = 72.0  # one point is one pixel on a 1920x1080 slide

config.pixel_width, config.pixel_height = 1920, 1080
config.frame_width = config.pixel_width / PX_PER_UNIT
config.frame_height = config.pixel_height / PX_PER_UNIT
config.background_color = WHITE

FONT = "New York"


class KeynoteSlide(Scene):
    def construct(self) -> None:
        self.add(keynote.text_box("Hello World", FONT, 910, 510, 44))
        self.add(keynote.text_box("Hello World", FONT, 910, 570, 128))


class HighlightOneWord(Scene):
    """`cluster` indices survive shaping, so a word can be addressed directly."""

    def construct(self) -> None:
        title = keynote.text_box("Hello World", FONT, 910, 570, 128)
        self.add(title.chars(0, 5))  # "Hello"
        self.play(Write(title.chars(6, 11)))  # "World"
        self.play(title.chars(6, 11).animate.set_color(BLUE))


class ClassicAndMiramesa(Scene):
    """The same headline drawn both ways, stacked, for comparison.

    The two APIs line up almost one for one -- the comments below mark the
    three places they do not.  What the render shows is the point of the
    package: manim's `Text` draws New York's small-text cut whatever the size,
    while miramesa asks Core Text for the 128pt cut, which is narrower and
    has thinner hairlines.
    """

    def construct(self) -> None:
        # -- the classic manim way -------------------------------------------
        # `font_size` rather than `size`; `Text` defaults to the config's
        # colour, white here, so black has to be asked for; and it carries no
        # baseline, so it can only be placed by its ink box.
        classic = Text(
            "Hello World", font=FONT, font_size=128, color=BLACK, t2c={"World": RED}
        )
        classic.move_to(pixel_to_scene(960, 400))

        # -- the miramesa way ------------------------------------------------
        # `size` is in pixels of the frame, and the mobject is built with its
        # pen origin -- the left edge of the line, on the baseline -- at the
        # scene origin, so `shift` places that origin rather than a box.
        # `t2c` is spelled the same in both, and colours the same word.
        ours = GlyphText("Hello World", font=FONT, size=128, t2c={"World": RED})
        ours.shift(pixel_to_scene(645, 700))

        self.add(classic, ours)


class ColouredWord(Scene):
    """A colour span, set at construction and then moved to the other word."""

    def construct(self) -> None:
        title = keynote.text_box("Hello World", FONT, 910, 570, 128, t2c={"World": RED})
        self.add(title)
        self.play(title.animate.set_span_color(0, 11, BLUE))
        self.play(title.animate.set_span_color(0, 5, RED))
