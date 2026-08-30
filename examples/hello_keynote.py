"""Rebuild a Keynote slide in manim.

Two "Hello World" strings in New York on a 1920x1080 slide: 44pt with its text
box at (910, 510) and 128pt at (910, 570).

    manim -s examples/hello_keynote.py KeynoteSlide
"""

from __future__ import annotations

from manim import BLUE, RED, WHITE, Scene, Write, config

from miramesa import keynote

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


class ColouredWord(Scene):
    """A colour span, set at construction and then moved to the other word."""

    def construct(self) -> None:
        title = keynote.text_box("Hello World", FONT, 910, 570, 128, t2c={"World": RED})
        self.add(title)
        self.play(title.animate.set_span_color(0, 11, BLUE))
        self.play(title.animate.set_span_color(0, 5, RED))
