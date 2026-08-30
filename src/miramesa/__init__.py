"""miramesa-manim -- high-fidelity text for manim.

manim's stock :class:`~manim.mobject.text.text_mobject.Text` goes through Pango
and an SVG round-trip, which loses the font's optical size axis, all Apple
typographic tables, and every typographic metric except the ink bounding box.
This package shapes text with a real text engine instead and hands manim
positioned glyph outlines::

    from miramesa import GlyphText, pixel_to_scene

    title = GlyphText("Hello World", font="New York", size=128)
    title.shift(pixel_to_scene(914, 696))   # pen origin -> that pixel

Rasterisation is unchanged: the glyphs are ordinary ``VMobject``s.
"""

from miramesa import keynote
from miramesa.backends.base import (
    Backend,
    BackendUnavailable,
    available_backends,
    get_backend,
    register_backend,
)
from miramesa.mobject import (
    DEFAULT_STEM_DARKENING,
    GlyphText,
    pixel_to_scene,
    pixels_per_unit,
)
from miramesa.spans import ColorSpan
from miramesa.spec import FontSpec, Glyph, ShapedLine

__version__ = "0.1.0.dev0"

__all__ = [
    "DEFAULT_STEM_DARKENING",
    "Backend",
    "BackendUnavailable",
    "ColorSpan",
    "FontSpec",
    "Glyph",
    "GlyphText",
    "ShapedLine",
    "available_backends",
    "get_backend",
    "keynote",
    "pixel_to_scene",
    "pixels_per_unit",
    "register_backend",
]
