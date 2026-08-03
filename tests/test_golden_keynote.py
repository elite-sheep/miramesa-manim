"""Golden test: reproduce a real Keynote export, pixel for pixel.

``fixtures/keynote_hello_world.png`` is a 1920x1080 slide exported from Keynote
holding two "Hello World" strings set in New York -- 44pt with its text box at
(910, 510) and 128pt at (910, 570).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from conftest import needs_new_york
from manim import WHITE, Scene, tempconfig
from PIL import Image

from miramesa import keynote

REFERENCE = Path(__file__).parent / "fixtures" / "keynote_hello_world.png"
PX_PER_UNIT = 72.0  # a point is a pixel on a 1920x1080 slide

TEXT_BOXES = [
    # text, box left, box top, size
    ("Hello World", 910, 510, 44),
    ("Hello World", 910, 570, 128),
]
TEXT_AREA = (slice(490, 720), slice(880, 1600))


class KeynoteSlide(Scene):
    def construct(self) -> None:
        for text, left, top, size in TEXT_BOXES:
            self.add(keynote.text_box(text, "New York", left, top, size))


def ink_boxes(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    """(x, y, width, height) of each row of text."""
    dark = image < 0.5
    rows = np.flatnonzero(dark.any(axis=1))
    bands, start, previous = [], rows[0], rows[0]
    for row in rows[1:]:
        if row > previous + 3:
            bands.append((start, previous))
            start = row
        previous = row
    bands.append((start, previous))

    boxes = []
    for top, bottom in bands:
        cols = np.flatnonzero(dark[top : bottom + 1].any(axis=0))
        boxes.append(
            (int(cols[0]), int(top), int(cols[-1] - cols[0] + 1), int(bottom - top + 1))
        )
    return boxes


@pytest.fixture(scope="module")
def rendered() -> np.ndarray:
    with tempconfig(
        {
            "pixel_width": 1920,
            "pixel_height": 1080,
            "frame_width": 1920 / PX_PER_UNIT,
            "frame_height": 1080 / PX_PER_UNIT,
            "background_color": WHITE,
            "write_to_movie": False,
            "format": "png",
        }
    ):
        scene = KeynoteSlide()
        scene.render()
        image = scene.renderer.camera.get_image().convert("L")
    return np.asarray(image, dtype=np.float64) / 255.0


@pytest.fixture(scope="module")
def reference() -> np.ndarray:
    return np.asarray(Image.open(REFERENCE).convert("L"), dtype=np.float64) / 255.0


@needs_new_york
def test_ink_boxes_match(rendered, reference):
    ours, theirs = ink_boxes(rendered), ink_boxes(reference)
    assert len(ours) == len(theirs) == 2
    for (x, y, w, h), (rx, ry, rw, rh) in zip(ours, theirs, strict=True):
        assert abs(x - rx) <= 1 and abs(y - ry) <= 1, f"position {(x, y)} vs {(rx, ry)}"
        assert abs(w - rw) <= 1 and abs(h - rh) <= 1, f"size {(w, h)} vs {(rw, rh)}"


@needs_new_york
def test_pixel_difference_is_small(rendered, reference):
    difference = np.abs(rendered[TEXT_AREA] - reference[TEXT_AREA]).mean()
    assert difference <= 0.005, f"mean |difference| {difference:.2%} exceeds 0.5%"


@needs_new_york
def test_no_translation_would_improve_the_match(rendered, reference):
    """A systematic offset would show up as a better score after nudging."""
    base = np.abs(rendered[TEXT_AREA] - reference[TEXT_AREA]).mean()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            shifted = np.roll(rendered, (dy, dx), axis=(0, 1))
            score = np.abs(shifted[TEXT_AREA] - reference[TEXT_AREA]).mean()
            assert score >= base - 1e-6 or (dx, dy) == (0, 0), (
                f"shifting by {(dx, dy)} improves the match: {score:.4f} < {base:.4f}"
            )


@needs_new_york
def test_ink_weight_matches(rendered, reference):
    """Stem darkening should land the total ink within a few percent."""
    for name, band in (("44pt", slice(515, 565)), ("128pt", slice(595, 705))):
        ours = (1.0 - rendered[band]).sum()
        theirs = (1.0 - reference[band]).sum()
        ratio = ours / theirs
        assert ratio == pytest.approx(1.0, abs=0.05), f"{name} ink {ratio:.3f}x"
