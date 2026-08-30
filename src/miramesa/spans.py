"""Which characters of a string take which colour.

Nothing here imports manim -- a colour is an opaque object -- so the range
arithmetic tests in milliseconds, without a renderer.

Ranges index the string that was shaped, which is the same thing a glyph's
``cluster`` indexes.  manim's own ``Text`` has two disagreeing conventions
here: its ``t2c`` slices index the source string while slicing the mobject
indexes rendered characters with whitespace removed.  There is only one
convention in this package.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["ColorSpan", "color_table", "spans_from_mapping"]

logger = logging.getLogger("miramesa")

#: a ``t2c`` key of this shape is read as a slice rather than as a substring
_SLICE_KEY = re.compile(r"\[(-?\d+)?:(-?\d+)?\]")


@dataclass(frozen=True)
class ColorSpan:
    """``color``, applied to ``text[start:stop]``.

    The bounds are Python slice bounds, resolved against a particular string
    by :meth:`resolve`: negative indices count from the end, ``stop=None``
    runs to the end, and out-of-range values clamp instead of raising.
    """

    start: int
    stop: int | None
    color: Any

    def resolve(self, length: int) -> tuple[int, int]:
        """The half-open ``[start, stop)`` this covers in a string of ``length``."""
        start, stop, _ = slice(self.start, self.stop).indices(length)
        return start, max(start, stop)


def spans_from_mapping(text: str, mapping: Mapping[str, Any]) -> list[ColorSpan]:
    """Turn a manim-style ``t2c`` mapping into spans.

    A key is either a substring -- every non-overlapping occurrence of which is
    coloured -- or a slice of the source string written ``"[start:stop]"``,
    with either end optional.  A key that could be read both ways is read as a
    slice.

    A substring that does not occur is a typo far more often than it is
    deliberate, so it is reported rather than quietly doing nothing.  A range
    that covers no glyph is not: colouring a stretch of spaces is a reasonable
    thing to ask for.
    """
    spans: list[ColorSpan] = []
    for key, color in mapping.items():
        slice_key = _SLICE_KEY.fullmatch(key)
        if slice_key is not None:
            start, stop = slice_key.groups()
            spans.append(
                ColorSpan(
                    0 if start is None else int(start),
                    None if stop is None else int(stop),
                    color,
                )
            )
            continue
        if not key:
            raise ValueError("a t2c key must be a substring or a '[start:stop]' slice")
        occurrences = [match.start() for match in re.finditer(re.escape(key), text)]
        if not occurrences:
            logger.warning("t2c substring %r does not occur in %r", key, text)
        spans.extend(ColorSpan(at, at + len(key), color) for at in occurrences)
    return spans


def color_table(text: str, spans: Sequence[ColorSpan], default: Any) -> list[Any]:
    """The colour of every character of ``text``.

    Spans are applied in the order given, so where two overlap the later one
    wins.  That is the only precedence rule -- there is no notion of a more
    specific span.
    """
    table = [default] * len(text)
    for span in spans:
        start, stop = span.resolve(len(text))
        for index in range(start, stop):
            table[index] = span.color
    return table
