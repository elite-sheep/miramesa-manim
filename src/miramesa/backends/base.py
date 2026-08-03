"""Backend protocol and registry.

A backend turns text into positioned glyph outlines.  It does not rasterise
anything -- manim's own renderer still draws the resulting mobjects.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from miramesa.spec import FontSpec, ShapedLine

__all__ = [
    "Backend",
    "BackendUnavailable",
    "available_backends",
    "get_backend",
    "register_backend",
]

logger = logging.getLogger("miramesa")


class BackendUnavailable(RuntimeError):
    """Raised when no shaping backend can run on this machine."""


@runtime_checkable
class Backend(Protocol):
    """Turns a string into positioned glyph outlines."""

    #: short identifier, e.g. ``"coretext"``
    name: str

    @staticmethod
    def available() -> bool:
        """Whether this backend can run here (imports resolve, OS matches)."""
        ...

    def families(self) -> frozenset[str]:
        """Every font family this backend can resolve."""
        ...

    def system_family(self) -> str:
        """The platform's default UI font, used when a request cannot be met."""
        ...

    def shape(self, text: str, font: FontSpec) -> ShapedLine:
        """Shape one line. Must apply optical sizing -- see :class:`FontSpec`."""
        ...


_REGISTRY: dict[str, type[Backend]] = {}
#: tried in this order when no backend is named
_PREFERENCE = ("coretext", "harfbuzz")


def register_backend(cls: type[Backend]) -> type[Backend]:
    _REGISTRY[cls.name] = cls
    return cls


def available_backends() -> list[str]:
    _load_all()
    return [name for name, cls in _REGISTRY.items() if cls.available()]


def get_backend(name: str | None = None) -> Backend:
    """Return a backend instance, preferring the highest-fidelity one available."""
    _load_all()
    if name is not None:
        try:
            cls = _REGISTRY[name]
        except KeyError:
            raise BackendUnavailable(
                f"unknown backend {name!r}; known: {sorted(_REGISTRY)}"
            ) from None
        if not cls.available():
            raise BackendUnavailable(f"backend {name!r} is not usable on this machine")
        return cls()

    for candidate in _PREFERENCE:
        cls = _REGISTRY.get(candidate)
        if cls is not None and cls.available():
            return cls()
    raise BackendUnavailable(
        "no shaping backend available; install an extra, e.g. "
        "`pip install miramesa-manim[coretext]` on macOS"
    )


def resolve_family(backend: Backend, family: str) -> str:
    """Map a requested family onto one the backend has, warning on a fallback.

    A missing font is never silently substituted: the user hears about it and
    gets the system font rather than whatever the platform would have picked.
    """
    families = backend.families()
    if family in families:
        return family
    for candidate in families:  # font names are case-insensitive in practice
        if candidate.lower() == family.lower():
            return candidate
    substitute = backend.system_family()
    logger.warning(
        "font %r not found; falling back to the system font %r", family, substitute
    )
    return substitute


def _load_all() -> None:
    """Import the built-in backends, ignoring ones whose imports fail."""
    from importlib import import_module

    for module in ("coretext", "harfbuzz"):
        if module in _REGISTRY:
            continue
        try:
            import_module(f"miramesa.backends.{module}")
        except ImportError:  # optional dependency missing -- fine
            logger.debug("backend %r could not be imported", module)
