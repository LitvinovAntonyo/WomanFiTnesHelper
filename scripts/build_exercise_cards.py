from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = ROOT / "media_sources" / "fonts" / "NotoSans.ttf"

CANVAS_SIZE = (1254, 1254)
BACKGROUND = "#F4F6F6"
TEXT_COLOR = "#263333"
BORDER_COLOR = "#D7DEDE"
ACCENT_COLOR = "#239B95"
PANEL_WIDTH = 558
PANEL_GAP = 42
PANEL_X = (48, 48 + PANEL_WIDTH + PANEL_GAP)
IMAGE_TOP = 170
IMAGE_BOTTOM = 865
IMAGE_HEIGHT = IMAGE_BOTTOM - IMAGE_TOP


@dataclass(frozen=True, slots=True)
class CardSpec:
    title: str
    start_image: Path
    end_image: Path
    start_label: str
    end_label: str
    start_hint: str
    end_hint: str
    attribution: str


def _font(size: int) -> ImageFont.FreeTypeFont:
    if not FONT_PATH.is_file():
        raise FileNotFoundError(f"vendored card font is missing: {FONT_PATH}")
    return ImageFont.truetype(FONT_PATH, size=size)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def _wrap_two_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> tuple[str, ...]:
    words = text.split()
    if not words:
        return ("",)

    lines: list[str] = []
    current = ""
    for word in words:
        if _text_width(draw, word, font) > max_width:
            raise ValueError("hint does not fit in at most two lines")
        candidate = f"{current} {word}".strip()
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == 2:
            raise ValueError("hint does not fit in at most two lines")
    lines.append(current)
    if len(lines) > 2:
        raise ValueError("hint does not fit in at most two lines")
    return tuple(lines)


def _load_fitted_photo(path: Path) -> Image.Image:
    with Image.open(path) as source:
        rgb_source = source.convert("RGB")
        fitted = ImageOps.fit(
            rgb_source,
            (PANEL_WIDTH, IMAGE_HEIGHT),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    return fitted


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: tuple[str, ...],
    *,
    center_x: int,
    top: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    line_height = font.size + 8
    for index, line in enumerate(lines):
        draw.text(
            (center_x, top + index * line_height),
            line,
            font=font,
            fill=TEXT_COLOR,
            anchor="ma",
        )


def _draw_arrow(draw: ImageDraw.ImageDraw) -> None:
    center_y = (IMAGE_TOP + IMAGE_BOTTOM) // 2
    start_x = PANEL_X[0] + PANEL_WIDTH + 8
    tip_x = PANEL_X[1] - 8
    draw.line((start_x, center_y, tip_x, center_y), fill=ACCENT_COLOR, width=4)
    draw.polygon(
        (
            (tip_x, center_y),
            (tip_x - 10, center_y - 8),
            (tip_x - 10, center_y + 8),
        ),
        fill=ACCENT_COLOR,
    )


def render_card(spec: CardSpec, output: Path) -> None:
    canvas = Image.new("RGB", CANVAS_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    title_font = _font(48)
    label_font = _font(30)
    hint_font = _font(27)
    attribution_font = _font(21)

    draw.text(
        (CANVAS_SIZE[0] // 2, 35),
        spec.title,
        font=title_font,
        fill=TEXT_COLOR,
        anchor="ma",
    )

    phases = (
        (PANEL_X[0], spec.start_image, spec.start_label, spec.start_hint),
        (PANEL_X[1], spec.end_image, spec.end_label, spec.end_hint),
    )
    for x, source_path, label, hint in phases:
        center_x = x + PANEL_WIDTH // 2
        draw.text(
            (center_x, 100),
            label,
            font=label_font,
            fill=TEXT_COLOR,
            anchor="ma",
        )
        photo = _load_fitted_photo(source_path)
        canvas.paste(photo, (x, IMAGE_TOP))
        draw.rectangle(
            (x, IMAGE_TOP, x + PANEL_WIDTH - 1, IMAGE_BOTTOM - 1),
            outline=BORDER_COLOR,
            width=2,
        )
        hint_lines = _wrap_two_lines(draw, hint, hint_font, PANEL_WIDTH - 32)
        _draw_centered_lines(
            draw,
            hint_lines,
            center_x=center_x,
            top=900,
            font=hint_font,
        )

    _draw_arrow(draw)
    draw.text(
        (CANVAS_SIZE[0] // 2, 1210),
        spec.attribution,
        font=attribution_font,
        fill=TEXT_COLOR,
        anchor="ma",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True, compress_level=9)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render deterministic exercise cards from verified local photographs."
    )
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
