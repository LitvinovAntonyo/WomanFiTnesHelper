from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

# Keep the documented ``python scripts/...`` invocation working in addition to
# the package form used by tests and callers.
ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from scripts.build_exercise_cards import FONT_PATH, CardSpec, render_card  # noqa: E402

DEFAULT_PRIVATE_ROOT = ROOT / ".private" / "exercise-media"
DEFAULT_REVIEW_ROOT = ROOT / "review" / "local-ai-pilot"


def normalize_generated_phase(generated: Path, source: Path, output: Path) -> Path:
    with Image.open(source) as source_image, Image.open(generated) as generated_image:
        if (
            source_image.width * generated_image.height
            != generated_image.width * source_image.height
        ):
            raise ValueError("generated phase changed the source aspect ratio")
        normalized = generated_image.convert("RGB").resize(
            source_image.size, Image.Resampling.LANCZOS
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized.save(output, format="PNG", optimize=True, compress_level=9)
    return output


def build_comparison(
    source_start: Path,
    source_end: Path,
    generated_start: Path,
    generated_end: Path,
    output: Path,
) -> Path:
    panel_size = (720, 720)
    canvas = Image.new("RGB", (1560, 1660), "#F4F6F6")
    draw = ImageDraw.Draw(canvas)
    heading = ImageFont.truetype(FONT_PATH, size=36)
    row_label = ImageFont.truetype(FONT_PATH, size=30)
    footer = ImageFont.truetype(FONT_PATH, size=26)
    draw.text((420, 28), "Исходное положение", font=heading, fill="#263333", anchor="ma")
    draw.text((1140, 28), "Конечное положение", font=heading, fill="#263333", anchor="ma")
    draw.text((24, 420), "ОРИГИНАЛ", font=row_label, fill="#263333", anchor="lm")
    draw.text((24, 1160), "AI-ПИЛОТ", font=row_label, fill="#263333", anchor="lm")
    for source_path, position in (
        (source_start, (120, 80)),
        (source_end, (840, 80)),
        (generated_start, (120, 820)),
        (generated_end, (840, 820)),
    ):
        with Image.open(source_path) as source:
            panel = ImageOps.fit(source.convert("RGB"), panel_size, Image.Resampling.LANCZOS)
        canvas.paste(panel, position)
    draw.text(
        (780, 1580),
        "НЕ ОДОБРЕНО · ПРОВЕРИТЬ ГЕОМЕТРИЮ И ЛИЦО",
        font=footer,
        fill="#B3362D",
        anchor="ma",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True, compress_level=9)
    return output


def build_pilot_card(generated_start: Path, generated_end: Path, output: Path) -> Path:
    spec = CardSpec(
        title="Гакк-приседания · AI-пилот",
        start_image=generated_start,
        end_image=generated_end,
        start_label="Исходное положение",
        end_label="Конечное положение",
        start_hint="Спина и таз прижаты к опоре",
        end_hint="Опустись до комфортной глубины под контролем",
        attribution="НЕ ОДОБРЕНО · техника: free-exercise-db (Unlicense)",
    )
    render_card(spec, output)
    return output


def validate_output_dir(output_dir: Path, allowed_root: Path = DEFAULT_REVIEW_ROOT) -> Path:
    resolved = output_dir.resolve()
    if not resolved.is_relative_to(allowed_root.resolve()):
        raise ValueError("output path is outside the private review directory")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, default=DEFAULT_PRIVATE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REVIEW_ROOT)
    args = parser.parse_args()
    output_dir = validate_output_dir(args.output_dir)
    source_dir = args.private_root / "hack_squat"
    generated_start = normalize_generated_phase(
        output_dir / "generated-start-raw.png",
        source_dir / "source-start.png",
        output_dir / "generated-start.png",
    )
    generated_end = normalize_generated_phase(
        output_dir / "generated-end-raw.png",
        source_dir / "source-end.png",
        output_dir / "generated-end.png",
    )
    build_comparison(
        source_dir / "source-start.png",
        source_dir / "source-end.png",
        generated_start,
        generated_end,
        output_dir / "hack_squat-comparison.png",
    )
    build_pilot_card(
        generated_start,
        generated_end,
        output_dir / "hack_squat-card.png",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
