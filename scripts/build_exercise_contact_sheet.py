from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = ROOT / "media_sources" / "fonts" / "NotoSans.ttf"
DEFAULT_MANIFEST = ROOT / "app" / "assets" / "exercises" / "manifest.json"
DEFAULT_ASSET_DIR = DEFAULT_MANIFEST.parent
DEFAULT_OUTPUT = ROOT / "review" / "exercise-cards-contact-sheet.png"

COLUMNS = 3
THUMBNAIL_SIZE = 300
MARGIN = 36
COLUMN_WIDTH = 336
COLUMN_GAP = 24
ROW_HEIGHT = 360
ROW_GAP = 24
BACKGROUND = "#F4F6F6"
TEXT_COLOR = "#263333"
BORDER_COLOR = "#D7DEDE"


@dataclass(frozen=True, slots=True)
class ContactSheetItem:
    code: str
    card: Path
    status: Literal["candidate", "approved", "text_only"]


def _font(size: int) -> ImageFont.FreeTypeFont:
    if not FONT_PATH.is_file():
        raise FileNotFoundError(f"vendored contact-sheet font is missing: {FONT_PATH}")
    return ImageFont.truetype(FONT_PATH, size=size)


def _safe_asset_path(asset_dir: Path, card_name: str) -> Path:
    resolved_dir = asset_dir.resolve()
    card = (asset_dir / card_name).resolve()
    try:
        card.relative_to(resolved_dir)
    except ValueError as exc:
        raise ValueError("candidate card path points outside the asset directory") from exc
    return card


def candidate_items_from_manifest(
    manifest_path: Path, asset_dir: Path
) -> list[ContactSheetItem]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("exercises"), dict):
        raise ValueError("exercise asset manifest must contain an exercises object")

    candidates: list[ContactSheetItem] = []
    for code, raw_entry in manifest["exercises"].items():
        if not isinstance(code, str) or not code:
            raise ValueError("candidate exercise code must be a non-empty string")
        if not isinstance(raw_entry, dict) or raw_entry.get("status") != "candidate":
            continue
        card_name = raw_entry.get("card")
        if not isinstance(card_name, str) or not card_name:
            continue
        card = _safe_asset_path(asset_dir, card_name)
        if not card.is_file():
            raise FileNotFoundError(f"candidate card is missing: {card}")
        candidates.append(ContactSheetItem(code=code, card=card, status="candidate"))
    return sorted(candidates, key=lambda item: item.code)


def render_contact_sheet(
    items: Sequence[ContactSheetItem],
    output: Path,
) -> None:
    rows = max(1, ceil(len(items) / COLUMNS))
    width = MARGIN * 2 + COLUMNS * COLUMN_WIDTH + (COLUMNS - 1) * COLUMN_GAP
    height = MARGIN * 2 + rows * ROW_HEIGHT + (rows - 1) * ROW_GAP
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    code_font = _font(20)
    status_font = _font(17)
    if not items:
        draw.text(
            (width // 2, height // 2),
            "Нет карточек-кандидатов",
            font=_font(26),
            fill=TEXT_COLOR,
            anchor="mm",
        )

    for index, item in enumerate(items):
        row, column = divmod(index, COLUMNS)
        cell_x = MARGIN + column * (COLUMN_WIDTH + COLUMN_GAP)
        cell_y = MARGIN + row * (ROW_HEIGHT + ROW_GAP)
        image_x = cell_x + (COLUMN_WIDTH - THUMBNAIL_SIZE) // 2
        with Image.open(item.card) as source:
            thumbnail = ImageOps.fit(
                source.convert("RGB"),
                (THUMBNAIL_SIZE, THUMBNAIL_SIZE),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
        sheet.paste(thumbnail, (image_x, cell_y))
        draw.rectangle(
            (
                image_x,
                cell_y,
                image_x + THUMBNAIL_SIZE - 1,
                cell_y + THUMBNAIL_SIZE - 1,
            ),
            outline=BORDER_COLOR,
            width=2,
        )
        center_x = cell_x + COLUMN_WIDTH // 2
        draw.text(
            (center_x, cell_y + 307),
            item.code,
            font=code_font,
            fill=TEXT_COLOR,
            anchor="ma",
        )
        draw.text(
            (center_x, cell_y + 333),
            f"status: {item.status}",
            font=status_font,
            fill=TEXT_COLOR,
            anchor="ma",
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True, compress_level=9)


def build_contact_sheet(
    manifest_path: Path = DEFAULT_MANIFEST,
    asset_dir: Path = DEFAULT_ASSET_DIR,
    output: Path = DEFAULT_OUTPUT,
) -> None:
    items = candidate_items_from_manifest(manifest_path, asset_dir)
    render_contact_sheet(items, output)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic three-column exercise-card review sheet."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    build_contact_sheet(args.manifest, args.asset_dir, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
