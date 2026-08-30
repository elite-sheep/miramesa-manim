"""The mobject layer: shaped glyphs as manim vector mobjects."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Self

import numpy as np
from fontTools.pens.basePen import BasePen
from manim import BLACK, RendererType, VGroup, VMobject, config
from manim.mobject.opengl.opengl_compatibility import ConvertToOpenGL

from miramesa.backends.base import Backend, get_backend
from miramesa.spans import ColorSpan, color_table, spans_from_mapping
from miramesa.spec import FontSpec, Glyph, ShapedLine

__all__ = ["DEFAULT_STEM_DARKENING", "GlyphText", "pixel_to_scene", "pixels_per_unit"]

logger = logging.getLogger("miramesa")

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


def _paint(mobject, color, stroke_width: float) -> None:
    """Colour a glyph, stem-darkening stroke included.

    The stroke is not decoration -- it is what grows the outline to match Core
    Graphics' rasterisation -- so it has to carry the same colour as the fill.
    Painting through one helper is what keeps the two from drifting apart.
    """
    mobject.set_fill(color, opacity=1)
    if stroke_width > 0:
        mobject.set_stroke(color, width=stroke_width, opacity=1)
    else:
        mobject.set_stroke(width=0)


def _split_glyphs(glyphs, colors: Sequence[Any]) -> list[Glyph]:
    """Glyphs whose characters were asked for in more than one colour.

    A ligature is a single glyph covering several characters, so it can only
    take one colour.  A span ending inside one is therefore a request that
    cannot be honoured, and saying so is better than quietly colouring the
    characters on the far side of the boundary too.
    """
    return [
        glyph
        for glyph in glyphs
        if any(
            colors[index] != colors[glyph.cluster]
            for index in range(glyph.cluster, glyph.cluster_end)
        )
    ]


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
    color
        The colour of every character no span covers.
    spans
        :class:`~miramesa.spans.ColorSpan` ranges, e.g.
        ``[ColorSpan(6, 11, RED)]``.  Bounds are Python slice bounds.
    t2c
        The same thing in manim's ``Text`` spelling: ``{"World": RED}`` colours
        every occurrence of a substring, ``{"[6:11]": RED}`` a slice.  Both
        index the source string, which is what ``cluster`` and :meth:`chars`
        index too -- so ``t2c={"[0:5]": RED}`` and ``chars(0, 5)`` cover the
        same characters.  Applied after ``spans``; where two overlap, the later
        one wins.
    variations
        OpenType variation axes, e.g. ``{"wght": 600}``.  Backends set ``opsz``
        from ``size`` unless it appears here.
    stem_darkening
        Outward growth in pixels compensating for cairo's lighter rasterisation;
        see :data:`DEFAULT_STEM_DARKENING`.  Pass ``0`` for the raw outlines.
    ligatures
        Ligation is on by default, so "ffi" may be drawn as one glyph.  Such a
        glyph can only take one colour: a span ending inside it is reported and
        takes the colour of its first character.  ``ligatures=False`` gives
        every character its own glyph, at the cost of the font's ligatures.
    """

    def __init__(
        self,
        text: str,
        font: str = "Helvetica",
        size: float = 48.0,
        color=BLACK,
        spans: Sequence[ColorSpan] | None = None,
        t2c: Mapping[str, Any] | None = None,
        variations: Mapping[str, float] | None = None,
        backend: Backend | str | None = None,
        stem_darkening: float | None = None,
        ligatures: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if "\n" in text:
            raise NotImplementedError("GlyphText handles a single line for now")

        engine = backend if isinstance(backend, Backend) else get_backend(backend)
        spec = FontSpec.of(font, size, variations, ligatures=ligatures)
        ppu = pixels_per_unit()

        self.text = text
        self.font_spec = spec
        self.backend_name = engine.name
        self.pixels_per_unit = ppu
        self.metrics: ShapedLine = engine.shape(text, spec)
        #: the spans as requested, resolved from ``spans`` and ``t2c``.  A
        #: record of the request, not of the current colours: recolouring a
        #: glyph afterwards, by any route, does not show up here.
        self.spans: tuple[ColorSpan, ...] = tuple(spans or ()) + tuple(
            spans_from_mapping(text, t2c or {})
        )

        for glyph in self.metrics.glyphs:
            mobject = _glyph_mobject(glyph, ppu)
            if mobject is not None:
                self.add(mobject)

        darkening = (
            DEFAULT_STEM_DARKENING if stem_darkening is None else float(stem_darkening)
        )
        # a centred stroke grows the shape by half its width
        width = (
            2 * darkening / (_CAIRO_LINE_WIDTH_MULTIPLE * ppu) if darkening > 0 else 0
        )
        _paint(self, color, width)  # the default, on the whole family
        if self.spans:
            colors = color_table(text, self.spans, color)
            for mobject in self.submobjects:
                _paint(mobject, colors[mobject.cluster], width)
            self._warn_about_split(_split_glyphs(self.metrics.glyphs, colors))

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

    # -- colour --------------------------------------------------------------

    def set_span_color(self, start: int, stop: int | None, color) -> Self:
        """Recolour ``text[start:stop]``, stem-darkening stroke included.

        Bounds are Python slice bounds, as in :class:`~miramesa.spans.ColorSpan`.
        A bound falling inside a ligature is reported, as at construction: the
        glyph is not divisible, so it takes the colour of its first character
        and the range actually recoloured is wider than the one asked for.
        Animates like any other mobject method::

            self.play(title.animate.set_span_color(6, 11, RED))
        """
        start, stop = ColorSpan(start, stop, color).resolve(len(self.text))
        self._warn_about_split(
            [
                glyph
                for glyph in self.metrics.glyphs
                if glyph.cluster < start < glyph.cluster_end
                or glyph.cluster < stop < glyph.cluster_end
            ]
        )
        self.chars(start, stop).set_color(color)
        return self

    def set_color_by_text(self, substring: str, color) -> Self:
        """Recolour every occurrence of ``substring``."""
        for span in spans_from_mapping(self.text, {substring: color}):
            self.set_span_color(span.start, span.stop, color)
        return self

    def _warn_about_split(self, split: Sequence[Glyph]) -> None:
        if not split:
            return
        logger.warning(
            "a colour span ends inside %s in %r, which the font draws as one "
            "glyph; it takes the colour of its first character. Pass "
            "ligatures=False to give every character its own glyph.",
            " and ".join(
                repr(self.text[glyph.cluster : glyph.cluster_end]) for glyph in split
            ),
            self.text,
        )
