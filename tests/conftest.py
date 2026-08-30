from __future__ import annotations

import platform

import pytest

from miramesa import get_backend


def font_missing(family: str, backend: str = "coretext") -> bool:
    """Whether ``family`` is unusable here -- for skip conditions."""
    if platform.system() != "Darwin":
        return True
    try:
        return family not in get_backend(backend).families()
    except Exception:
        return True


needs_new_york = pytest.mark.skipif(
    font_missing("New York"),
    reason="needs macOS with Apple's New York font installed",
)

#: New York does not ligate, so the ligature tests need a font that does
needs_hoefler = pytest.mark.skipif(
    font_missing("Hoefler Text"),
    reason="needs macOS with Hoefler Text installed, which ligates 'ffi'",
)
