"""The mobject layer: shaped glyphs as manim vector mobjects."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from fontTools.pens.basePen import BasePen
from manim import BLACK, RendererType, VGroup, VMobject, config
from manim.mobject.opengl.opengl_compatibility import ConvertToOpenGL

from miramesa.backends.base import Backend, get_backend
from miramesa.spec import FontSpec, Glyph, ShapedLine

__all__ = ["DEFAULT_STEM_DARKENING", "GlyphText", "pixel_to_scene", "pixels_per_unit"]

#: manim's cairo camera uses ``stroke_width * this`` as the line width, in
#: scene units (``Camera.cairo_line_width_multiple``).
_CAIRO_LINE_WIDTH_MULTIPLE = 0.01

#: Core Graphics dilates glyph outlines slightly when it rasterises ("font
#: smoothing"); cairo does not, so manim comes out lighter -- about 15% at
#: 44px and 8% at 128px.  This much outward growth, in pixels, matches Keynote.
#: Calibrated against one reference at one colour; set to 0 to disable.
DEFAULT_STEM_DARKENING = 0.29


def pixels_per_unit() -> float:
    """How many rendered pixels one scene unit spans, under the current config."""
    return config.pixel_width / config.frame_width


def pixel_to_scene(x_px: float, y_px: float, ppu: float | None = None) -> np.ndarray:
    """Map a top-left-origin pixel coordinate to a scene point."""
    ppu = pixels_per_unit() if ppu is None else ppu
    return np.array(
        [
            (x_px - config.pixel_width / 2) / ppu,
            (config.pixel_height / 2 - y_px) / ppu,
            0.0,
        ]
    )


class _VMobjectPen(BasePen):
    """Draws glyph outlines straight into a :class:`VMobject`.

    Subclassing ``BasePen`` means quadratic segments arrive already elevated to
    cubics, so backends may emit whichever the font uses.
    """

    def __init__(self, mobject: VMobject, dx: float, dy: float, ppu: float):
        super().__init__(glyphSet=None)
        self.mobject = mobject
        self._dx, self._dy, self._ppu = dx, dy, ppu

    def _point(self, pt: tuple[float, float]) -> np.ndarray:
        return np.array(
            [(self._dx + pt[0]) / self._ppu, (self._dy + pt[1]) / self._ppu, 0.0]
        )

    def _moveTo(self, pt) -> None:  # noqa: N802
        self.mobject.start_new_path(self._point(pt))

    def _lineTo(self, pt) -> None:  # noqa: N802
        self.mobject.add_line_to(self._point(pt))

    def _curveToOne(self, pt1, pt2, pt3) -> None:  # noqa: N802
        self.mobject.add_cubic_bezier_curve_to(
            self._point(pt1), self._point(pt2), self._point(pt3)
        )

    def _closePath(self) -> None:  # noqa: N802
        # contour direction carries the winding, so a plain close is enough:
        # cairo's default nonzero rule then cuts the counters out for us
        self.mobject.close_path()


def _leaf_class() -> type:
    """The vector mobject class the active renderer can actually draw.

    ``manim.VMobject`` stays bound to the cairo class even under
    ``--renderer=opengl``; only classes whose *base* is named ``VMobject`` get
    swapped, and only at import time.  Resolving per construction covers the
    case where the renderer is chosen after import.
    """
    if config.renderer == RendererType.OPENGL:
        from manim.mobject.opengl.opengl_vectorized_mobject import OpenGLVMobject

        return OpenGLVMobject
    return VMobject


def _group_class() -> type:
    if config.renderer == RendererType.OPENGL:
        from manim.mobject.opengl.opengl_vectorized_mobject import OpenGLVGroup

        return OpenGLVGroup
    return VGroup


def _glyph_mobject(glyph: Glyph, ppu: float) -> VMobject | None:
    mobject = _leaf_class()()
    glyph.draw(_VMobjectPen(mobject, glyph.x, glyph.y, ppu))
    if not len(mobject.points):
        return None
    mobject.glyph_id = glyph.glyph_id
    mobject.cluster = glyph.cluster
    return mobject


class GlyphText(VMobject, metaclass=ConvertToOpenGL):
    """Text shaped by a real text engine, as one ``VMobject`` per glyph.

    Like manim's own ``Text`` this is a vector mobject holding one submobject
    per glyph, so it indexes and iterates like a group.  The ``ConvertToOpenGL``
    metaclass re-bases it on ``OpenGLVMobject`` when the OpenGL renderer is
    selected before import -- the same mechanism, and the same caveat, as
    manim's ``SVGMobject``.

    The mobject is built with its **pen origin at the scene origin** -- the left
    edge of the line, on the baseline.  To place it, shift by the scene point
    you want that origin at::

        title = GlyphText("Hello World", font="New York", size=128)
        title.shift(pixel_to_scene(914, 696))

    ``size`` is in pixels of the rendered frame, resolved from ``config`` when
    the mobject is built: ``size=128`` draws a 128-pixel em, matching what
    Keynote means by 128pt on a 1920x1080 slide.  Changing the frame afterwards
    does not re-resolve it.

    Parameters
    ----------
    text
        The string to set.  Single line for now; ``\\n`` is not yet handled.
    font
        Family name.  A family the backend cannot find is reported and replaced
        with the system font rather than silently substituted.
    size
        Em size, in pixels of the rendered frame.
    variations
        OpenType variation axes, e.g. ``{"wght": 600}``.  Backends set ``opsz``
        from ``size`` unless it appears here.
    stem_darkening
        Outward growth in pixels compensating for cairo's lighter rasterisation;
        see :data:`DEFAULT_STEM_DARKENING`.  Pass ``0`` for the raw outlines.
    """

    def __init__(
        self,
        text: str,
        font: str = "Helvetica",
        size: float = 48.0,
        color=BLACK,
        variations: Mapping[str, float] | None = None,
        backend: Backend | str | None = None,
        stem_darkening: float | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if "\n" in text:
            raise NotImplementedError("GlyphText handles a single line for now")

        engine = backend if isinstance(backend, Backend) else get_backend(backend)
        spec = FontSpec.of(font, size, variations)
        ppu = pixels_per_unit()

        self.text = text
        self.font_spec = spec
        self.backend_name = engine.name
        self.pixels_per_unit = ppu
        self.metrics: ShapedLine = engine.shape(text, spec)

        for glyph in self.metrics.glyphs:
            mobject = _glyph_mobject(glyph, ppu)
            if mobject is not None:
                self.add(mobject)

        darkening = (
            DEFAULT_STEM_DARKENING if stem_darkening is None else float(stem_darkening)
        )
        self.set_fill(color, opacity=1)
        if darkening > 0:
            # a centred stroke grows the shape by half its width
            self.set_stroke(
                color,
                width=2 * darkening / (_CAIRO_LINE_WIDTH_MULTIPLE * ppu),
                opacity=1,
            )
        else:
            self.set_stroke(width=0)

    # -- typographic metrics, in scene units ---------------------------------

    @property
    def ascent(self) -> float:
        return self.metrics.ascent / self.pixels_per_unit

    @property
    def descent(self) -> float:
        return self.metrics.descent / self.pixels_per_unit

    @property
    def advance(self) -> float:
        return self.metrics.advance / self.pixels_per_unit

    @property
    def resolved_font(self) -> str:
        """The family actually used; differs from the request after a fallback."""
        return self.metrics.resolved_family

    def chars(self, start: int, stop: int | None = None) -> VGroup:
        """The glyphs covering ``text[start:stop]``, via their cluster indices."""
        stop = len(self.text) if stop is None else stop
        matching = (g for g in self.submobjects if start <= g.cluster < stop)
        return _group_class()(*matching)
