"""Compare miramesa's output against the Keynote export it is modelled on.

    python examples/compare_keynote.py                 # miramesa vs Keynote
    python examples/compare_keynote.py --baseline      # ... and manim's own Text
    python examples/compare_keynote.py -o out.png

Writes a figure of the text area -- each render, then a red/cyan overlay where
red is Keynote, cyan is manim, and black means they agree -- and prints the ink
boxes and difference numbers.

Needs matplotlib (in the dev dependency group).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from manim import BLACK, UL, WHITE, Scene, Text, tempconfig
from PIL import Image

from miramesa import keynote

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "tests" / "fixtures" / "keynote_hello_world.png"

PX_PER_UNIT = 72.0  # a point is a pixel on a 1920x1080 slide
FONT = "New York"
TEXT_BOXES = [
    # text, box left, box top, size
    ("Hello World", 910, 510, 44),
    ("Hello World", 910, 570, 128),
]
CROP = (880, 490, 1600, 720)  # left, top, right, bottom
BANDS = {"44pt": slice(515, 565), "128pt": slice(595, 705)}

SLIDE = {
    "pixel_width": 1920,
    "pixel_height": 1080,
    "frame_width": 1920 / PX_PER_UNIT,
    "frame_height": 1080 / PX_PER_UNIT,
    "background_color": WHITE,
    "write_to_movie": False,
    "format": "png",
}


class MiramesaSlide(Scene):
    def construct(self) -> None:
        for text, left, top, size in TEXT_BOXES:
            self.add(keynote.text_box(text, FONT, left, top, size))


class StockManimSlide(Scene):
    """manim's own Text, placed as closely as its ink box allows."""

    def construct(self) -> None:
        for text, left, top, size in TEXT_BOXES:
            mobject = Text(text, font=FONT, font_size=size, color=BLACK)
            # no baseline to work from, so line the ink boxes up instead
            reference = keynote.text_box(text, FONT, left, top, size)
            self.add(mobject.align_to(reference, UL))


def render(scene_class: type[Scene]) -> np.ndarray:
    with tempconfig(SLIDE):
        scene = scene_class()
        scene.render()
        image = scene.renderer.camera.get_image().convert("L")
    return np.asarray(image, dtype=np.float64) / 255.0


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


def report(name: str, image: np.ndarray, reference: np.ndarray) -> None:
    left, top, right, bottom = CROP
    area = (slice(top, bottom), slice(left, right))
    print(f"\n{name}")
    for (x, y, w, h), (rx, ry, rw, rh) in zip(
        ink_boxes(image), ink_boxes(reference), strict=True
    ):
        print(
            f"    ink box {w:4d} x {h:2d} at ({x}, {y})"
            f"    dx={x - rx:+d} dy={y - ry:+d} dw={w - rw:+d} dh={h - rh:+d}"
        )
    for label, band in BANDS.items():
        ratio = (1.0 - image[band]).sum() / (1.0 - reference[band]).sum()
        print(f"    {label:>5s} ink {ratio:5.3f}x reference")
    difference = np.abs(image[area] - reference[area]).mean()
    print(f"    mean |difference| over the text area: {difference:.2%}")


def figure(panels: list[tuple[str, np.ndarray]], reference: np.ndarray, out: Path):
    import matplotlib.pyplot as plt

    left, top, right, bottom = CROP
    renders = [(name, img) for name, img in panels if name != "Keynote reference"]
    rows = len(panels) + len(renders)
    fig, axes = plt.subplots(rows, 1, figsize=(13, 2.6 * rows), dpi=100)

    for ax, (name, image) in zip(axes[: len(panels)], panels, strict=True):
        ax.imshow(
            image[top:bottom, left:right],
            cmap="gray",
            vmin=0,
            vmax=1,
            interpolation="nearest",
        )
        ax.set_title(name, fontsize=11, loc="left")

    for ax, (name, image) in zip(axes[len(panels) :], renders, strict=True):
        overlay = np.ones((bottom - top, right - left, 3))
        overlay[..., 0] -= 1.0 - image[top:bottom, left:right]  # manim ink -> cyan
        overlay[..., 1] -= 1.0 - reference[top:bottom, left:right]  # Keynote -> red
        overlay[..., 2] -= 1.0 - reference[top:bottom, left:right]
        ax.imshow(np.clip(overlay, 0, 1), interpolation="nearest")
        ax.set_title(f"overlay: red = Keynote, cyan = {name}", fontsize=11, loc="left")

    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(
        f'"Hello World" in {FONT}, 44pt @ (910, 510) and 128pt @ (910, 570), '
        f"1920x1080 -- crop x[{left}:{right}] y[{top}:{bottom}]",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(out, facecolor="white")
    print(f"\nwrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="also render manim's built-in Text for contrast",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "comparison_keynote.png",
        help="where to write the figure",
    )
    args = parser.parse_args()

    reference = np.asarray(Image.open(REFERENCE).convert("L"), dtype=np.float64) / 255.0
    panels = [("Keynote reference", reference)]
    if args.baseline:
        panels.append(("manim Text", render(StockManimSlide)))
    panels.append(("miramesa GlyphText", render(MiramesaSlide)))

    for name, image in panels[1:]:
        report(name, image, reference)
    figure(panels, reference, args.output)


if __name__ == "__main__":
    main()
