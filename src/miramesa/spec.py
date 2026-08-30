"""Backend-independent description of a font request and of a shaped line.

Nothing here imports manim, so the shaping layer can be tested (and reused)
without a renderer.

Geometry convention, used by every backend:

    pixels, x to the right, y **up**, origin at the line's pen origin
    (the left edge of the line, sitting on the baseline).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = ["FontSpec", "Glyph", "Pen", "ShapedLine"]


class Pen(Protocol):
    """The subset of the fontTools pen protocol backends draw into."""

    def moveTo(self, pt: tuple[float, float]) -> None: ...  # noqa: N802
    def lineTo(self, pt: tuple[float, float]) -> None: ...  # noqa: N802
    def curveTo(self, *points: tuple[float, float]) -> None: ...  # noqa: N802
    def qCurveTo(self, *points: tuple[float, float]) -> None: ...  # noqa: N802
    def closePath(self) -> None: ...  # noqa: N802


@dataclass(frozen=True)
class FontSpec:
    """A font request.

    ``variations`` is stored as a sorted tuple of pairs so the whole spec stays
    hashable and can key a shaping cache.  Use :meth:`of` to build one from a
    dict.

    Backends **must** drive an ``opsz`` (optical size) axis from ``size``
    unless ``variations`` sets it explicitly.  Skipping that is what makes
    manim's stock text renderer draw display type with the small-text cut.

    Turning ``ligatures`` off gives every character its own glyph, which is
    what addressing characters individually needs: a ligature is one glyph
    covering several characters, so it can only take one colour.
    """

    family: str
    size: float
    variations: tuple[tuple[str, float], ...] = ()
    ligatures: bool = True

    @classmethod
    def of(
        cls,
        family: str,
        size: float,
        variations: Mapping[str, float] | None = None,
        ligatures: bool = True,
    ) -> FontSpec:
        return cls(
            family,
            float(size),
            tuple(sorted((variations or {}).items())),
            ligatures,
        )

    @property
    def variation_dict(self) -> dict[str, float]:
        return dict(self.variations)


@dataclass(frozen=True)
class Glyph:
    """One positioned glyph.

    ``draw`` replays the outline into a pen in glyph-local coordinates; ``x``
    and ``y`` are where that outline's origin sits relative to the pen origin.

    ``cluster`` indexes the **Python string** that was shaped -- code points,
    not UTF-16 code units -- so ``text[glyph.cluster]`` is the character the
    glyph was shaped from.  A backend whose engine counts differently must
    convert; Core Text does.

    One glyph can cover several characters: a ligature reports the index of
    its first, and ``text[cluster:cluster_end]`` is everything it draws.  That
    range is what tells a caller addressing characters individually that it is
    about to split a glyph it cannot split.
    """

    glyph_id: int
    x: float
    y: float
    cluster: int
    cluster_end: int
    draw: Callable[[Pen], None] = field(repr=False)


@dataclass(frozen=True)
class ShapedLine:
    """A shaped run of text, in pixels."""

    glyphs: Sequence[Glyph]
    advance: float
    ascent: float
    descent: float
    leading: float = 0.0
    #: family the backend actually used -- differs from the request after a
    #: fallback, which is the caller's cue that a warning was issued
    resolved_family: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def line_height(self) -> float:
        return self.ascent + self.descent + self.leading
