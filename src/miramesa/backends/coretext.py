"""Core Text shaping backend (macOS).

Core Text is the engine Keynote and every other Mac app lay text out with, so
this backend inherits the whole Apple typographic stack for free: the ``opsz``
variation axis driven from the point size, the ``trak`` tracking table, kerning,
ligatures, and per-run font substitution for missing glyphs.

Only shaping and outline extraction happen here -- manim still rasterises.
"""

from __future__ import annotations

import struct
from bisect import bisect_right
from collections.abc import Sequence
from functools import lru_cache

from miramesa.backends.base import register_backend, resolve_family
from miramesa.spec import FontSpec, Glyph, Pen, ShapedLine

try:
    from AppKit import NSBezierPath
    from CoreText import (
        CTFontCopyFamilyName,
        CTFontCreatePathForGlyph,
        CTFontCreateUIFontForLanguage,
        CTFontCreateWithFontDescriptor,
        CTFontCreateWithName,
        CTFontDescriptorCreateWithAttributes,
        CTFontManagerCopyAvailableFontFamilyNames,
        CTLineCreateWithAttributedString,
        CTLineGetGlyphRuns,
        CTLineGetTypographicBounds,
        CTRunGetAttributes,
        CTRunGetGlyphCount,
        CTRunGetGlyphs,
        CTRunGetPositions,
        CTRunGetStringIndices,
        CTRunGetStringRange,
        kCTFontAttributeName,
        kCTFontNameAttribute,
        kCTFontUIFontSystem,
        kCTFontVariationAttribute,
        kCTLigatureAttributeName,
    )
    from Foundation import NSAttributedString

    _IMPORTED = True
except ImportError:  # pragma: no cover - exercised only off macOS
    _IMPORTED = False

__all__ = ["CoreTextBackend"]

# NSBezierPath element kinds.  macOS 14 added the quadratic case; code that
# only knows the first four silently drops segments on newer systems.
_MOVE, _LINE, _CURVE, _CLOSE, _QUAD = 0, 1, 2, 3, 4


def _axis_tag(tag: str) -> int:
    """Core Text identifies variation axes by the tag's four bytes as an int."""
    return struct.unpack(">I", tag.encode("ascii"))[0]


@lru_cache(maxsize=64)
def _ct_font(family: str, size: float, variations: tuple[tuple[str, float], ...]):
    if not variations:
        return CTFontCreateWithName(family, size, None)
    descriptor = CTFontDescriptorCreateWithAttributes(
        {
            kCTFontNameAttribute: family,
            kCTFontVariationAttribute: {
                _axis_tag(tag): value for tag, value in variations
            },
        }
    )
    return CTFontCreateWithFontDescriptor(descriptor, size, None)


def _code_point_index(text: str) -> list[int] | None:
    """Map every UTF-16 offset in ``text`` to the code point that contains it.

    Core Text reports string indices into an ``NSString``, which counts UTF-16
    code units, so one astral character -- an emoji, say -- shifts every index
    after it by one.  Clusters are documented to index the Python string, so
    they have to be translated or a caller slicing by character position
    addresses the wrong glyph, or none at all.

    Returns ``None`` when the two conventions agree, which is the case for any
    text made only of BMP characters.  The table carries one entry past the end
    so a run's end offset maps to ``len(text)``.
    """
    if all(ord(character) <= 0xFFFF for character in text):
        return None
    table = [
        index
        for index, character in enumerate(text)
        for _ in range(2 if ord(character) > 0xFFFF else 1)
    ]
    table.append(len(text))
    return table


def _cluster_ends(starts: Sequence[int], run_end: int) -> dict[int, int]:
    """Where each glyph's characters stop, taken from the next boundary along.

    Core Text reports only where a glyph's characters *start*, so a ligature
    is indistinguishable from a single-character glyph until you look at what
    follows it: it covers everything up to the next glyph's start, or to the
    end of the run.  Sorting the boundaries keeps this direction-agnostic, so
    a right-to-left run works the same way.
    """
    boundaries = sorted({*starts, run_end})
    ends = {}
    for start in starts:
        after = bisect_right(boundaries, start)
        ends[start] = boundaries[after] if after < len(boundaries) else run_end
    return ends


def _replay(cg_path, pen: Pen) -> None:
    """Replay a CGPath into a pen, in the glyph's own coordinates.

    ``bezierPathWithCGPath_`` ends every glyph with a spurious ``moveTo`` after
    the last contour closes, so the ``moveTo`` is held back until a segment
    actually follows it.  Emitting it eagerly leaves a stray anchor that renders
    fine but leaves the point array a non-whole number of curves, which trips up
    anything walking the mobject's anchors.
    """
    bezier = NSBezierPath.bezierPathWithCGPath_(cg_path)
    pending: tuple[float, float] | None = None
    drawing = False

    def begin() -> None:
        nonlocal pending, drawing
        if pending is not None:
            pen.moveTo(pending)
            pending, drawing = None, True

    for index in range(bezier.elementCount()):
        kind, points = bezier.elementAtIndex_associatedPoints_(index)
        if kind == _MOVE:
            if drawing:  # a contour left open by the font
                pen.closePath()
                drawing = False
            pending = (points[0].x, points[0].y)
        elif kind == _LINE:
            begin()
            pen.lineTo((points[0].x, points[0].y))
        elif kind == _CURVE:
            begin()
            pen.curveTo(*((p.x, p.y) for p in points[:3]))
        elif kind == _QUAD:
            begin()
            pen.qCurveTo(*((p.x, p.y) for p in points[:2]))  # pen elevates it
        elif kind == _CLOSE:
            if drawing:
                pen.closePath()
                drawing = False
            pending = None
    if drawing:
        pen.closePath()


@register_backend
class CoreTextBackend:
    name = "coretext"

    @staticmethod
    def available() -> bool:
        return _IMPORTED

    def families(self) -> frozenset[str]:
        return _families()

    def system_family(self) -> str:
        font = CTFontCreateUIFontForLanguage(kCTFontUIFontSystem, 12.0, None)
        return str(CTFontCopyFamilyName(font))

    def shape(self, text: str, font: FontSpec) -> ShapedLine:
        family = resolve_family(self, font.family)
        ct_font = _ct_font(family, font.size, font.variations)
        attributes = {kCTFontAttributeName: ct_font}
        if not font.ligatures:
            attributes[kCTLigatureAttributeName] = 0
        attributed = NSAttributedString.alloc().initWithString_attributes_(
            text, attributes
        )
        line = CTLineCreateWithAttributedString(attributed)
        table = _code_point_index(text)

        def index_of(utf16_offset: int) -> int:
            """The index into ``text`` of the character at a UTF-16 offset."""
            return utf16_offset if table is None else table[utf16_offset]

        glyphs: list[Glyph] = []
        for run in CTLineGetGlyphRuns(line):
            count = CTRunGetGlyphCount(run)
            if not count:
                continue
            span = (0, count)
            ids = CTRunGetGlyphs(run, span, None)
            positions = CTRunGetPositions(run, span, None)
            clusters = [
                index_of(int(raw)) for raw in CTRunGetStringIndices(run, span, None)
            ]
            run_range = CTRunGetStringRange(run)
            ends = _cluster_ends(
                clusters, index_of(int(run_range.location + run_range.length))
            )
            # a run carries its own font: this is where Core Text hands back a
            # substitute for characters the requested family cannot draw
            run_font = CTRunGetAttributes(run)[kCTFontAttributeName]
            for glyph_id, position, cluster in zip(
                ids, positions, clusters, strict=True
            ):
                cg_path = CTFontCreatePathForGlyph(run_font, glyph_id, None)
                if cg_path is None:  # whitespace carries no outline
                    continue
                glyphs.append(
                    Glyph(
                        glyph_id=int(glyph_id),
                        x=float(position.x),
                        y=float(position.y),
                        cluster=cluster,
                        cluster_end=ends[cluster],
                        draw=_make_drawer(cg_path),
                    )
                )

        advance, ascent, descent, leading = CTLineGetTypographicBounds(
            line, None, None, None
        )
        return ShapedLine(
            glyphs=glyphs,
            advance=float(advance),
            ascent=float(ascent),
            descent=float(descent),
            leading=float(leading),
            resolved_family=family,
        )


def _make_drawer(cg_path):
    def draw(pen: Pen) -> None:
        _replay(cg_path, pen)

    return draw


@lru_cache(maxsize=1)
def _families() -> frozenset[str]:
    return frozenset(str(name) for name in CTFontManagerCopyAvailableFontFamilyNames())
