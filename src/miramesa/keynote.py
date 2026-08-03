"""Placing text the way Keynote places a text box.

Keynote positions a text box by its top-left corner, insets the text from that
corner, and puts the first baseline one ascent below the inset edge.  Reproducing
a slide means doing the same arithmetic, so it lives here rather than being
retyped into every scene.
"""

from __future__ import annotations

from miramesa.mobject import GlyphText, pixel_to_scene

__all__ = ["DEFAULT_INSET", "text_box"]

#: Keynote's default text inset, in points.  Measured off a reference export --
#: it reproduced the ink position on both axes at both sizes.  Change it if the
#: slide's own inset margin was edited.
DEFAULT_INSET = 4.0


def text_box(
    text: str,
    font: str,
    left: float,
    top: float,
    size: float,
    inset: float = DEFAULT_INSET,
    **kwargs,
) -> GlyphText:
    """Text laid out as if in a Keynote text box whose top-left is (left, top).

    Coordinates are slide pixels from the top-left corner, which is what
    Keynote's position fields report.
    """
    mobject = GlyphText(text, font=font, size=size, **kwargs)
    return mobject.shift(
        pixel_to_scene(left + inset, top + inset + mobject.metrics.ascent)
    )
