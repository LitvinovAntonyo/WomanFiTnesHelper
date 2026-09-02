from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FONT_SHA256 = "bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d"


def solid_image(path: Path, size: tuple[int, int], color: str) -> Path:
    Image.new("RGB", size, color).save(path, format="JPEG", quality=95)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def card_spec(tmp_path: Path):
    from scripts.build_exercise_cards import CardSpec

    return CardSpec(
        title="Жим ногами",
        start_image=solid_image(tmp_path / "start.jpg", (220, 180), "red"),
        end_image=solid_image(tmp_path / "end.jpg", (180, 220), "blue"),
        start_label="Исходное положение",
        end_label="Конечное положение",
        start_hint="Колени согнуты, таз на спинке",
        end_hint="Выжми платформу без блокировки коленей",
        attribution="free-exercise-db · Unlicense",
    )


def test_vendored_font_matches_recorded_primary_source():
    license_text = (ROOT / "media_sources" / "fonts" / "OFL.txt").read_text(
        encoding="utf-8"
    )

    assert sha256(ROOT / "media_sources" / "fonts" / "NotoSans.ttf") == FONT_SHA256
    assert (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/"
        "NotoSans%5Bwdth%2Cwght%5D.ttf" in license_text
    )
    assert "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/OFL.txt" in license_text
    assert FONT_SHA256 in license_text
    assert "cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a" in license_text


def test_renderer_modules_are_import_safe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    importlib.import_module("scripts.build_exercise_cards")
    importlib.import_module("scripts.build_exercise_contact_sheet")

    assert list(tmp_path.iterdir()) == []


def test_render_card_has_fixed_size_and_is_deterministic(tmp_path):
    from scripts.build_exercise_cards import render_card

    spec = card_spec(tmp_path)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    render_card(spec, first)
    render_card(spec, second)

    with Image.open(first) as image:
        assert image.size == (1254, 1254)
        assert image.mode == "RGB"
        assert image.info == {}
    assert sha256(first) == sha256(second)


def test_render_card_uses_a_centered_crop(tmp_path):
    from scripts.build_exercise_cards import CardSpec, render_card

    striped = Image.new("RGB", (400, 200), "green")
    draw = ImageDraw.Draw(striped)
    draw.rectangle((0, 0, 119, 199), fill="red")
    draw.rectangle((280, 0, 399, 199), fill="blue")
    source = tmp_path / "striped.png"
    striped.save(source)
    spec = CardSpec(
        title="Центрирование",
        start_image=source,
        end_image=source,
        start_label="Исходное положение",
        end_label="Конечное положение",
        start_hint="Короткая подсказка",
        end_hint="Короткая подсказка",
        attribution="Источник · Лицензия",
    )
    output = tmp_path / "centered.png"

    render_card(spec, output)

    with Image.open(output) as image:
        for x in (52, 300, 602, 652, 900, 1202):
            red, green, blue = image.getpixel((x, 500))
            assert green > red
            assert green > blue


def test_render_card_rejects_a_hint_that_needs_more_than_two_lines(tmp_path):
    from scripts.build_exercise_cards import render_card

    spec = card_spec(tmp_path)
    spec = spec.__class__(
        title=spec.title,
        start_image=spec.start_image,
        end_image=spec.end_image,
        start_label=spec.start_label,
        end_label=spec.end_label,
        start_hint=" ".join(["оченьдлиннаяподсказка"] * 30),
        end_hint=spec.end_hint,
        attribution=spec.attribution,
    )

    with pytest.raises(ValueError, match="two lines"):
        render_card(spec, tmp_path / "overflow.png")


def test_hack_squat_card_renders_lowered_end_phase_with_matching_hint(
    tmp_path, monkeypatch
):
    from scripts.build_exercise_cards import SOURCE_PAIRS, card_spec_for, render_card

    pair = next(item for item in SOURCE_PAIRS if item.code == "hack_squat")
    source_dir = tmp_path / "hack_squat"
    source_dir.mkdir()
    solid_image(source_dir / "start.jpg", (220, 180), "red")
    solid_image(source_dir / "end.jpg", (220, 180), "blue")
    spec = card_spec_for(pair, source_dir)
    drawn_text: list[str] = []
    original_text = ImageDraw.ImageDraw.text

    def recording_text(draw, xy, text, *args, **kwargs):
        drawn_text.append(text)
        return original_text(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", recording_text)
    render_card(spec, tmp_path / "hack_squat.png")

    assert (pair.start_file, pair.end_file) == ("0.jpg", "1.jpg")
    assert spec.start_label == "Исходное положение"
    assert spec.end_label == "Конечное положение"
    assert spec.end_hint == "Опустись до комфортной глубины под контролем"
    end_label_index = drawn_text.index(spec.end_label)
    assert " ".join(drawn_text[end_label_index + 1 : -1]) == spec.end_hint
    assert not any("Поднимись" in text for text in drawn_text)


def test_render_contact_sheet_is_deterministic_and_uses_three_columns(tmp_path):
    from scripts.build_exercise_contact_sheet import ContactSheetItem, render_contact_sheet

    items = [
        ContactSheetItem(
            code=code,
            card=solid_image(tmp_path / filename, (1254, 1254), color),
            status="candidate",
        )
        for code, filename, color in (
            ("alpha", "first.png", "red"),
            ("beta", "second.png", "green"),
            ("gamma", "third.png", "blue"),
            ("delta", "fourth.png", "yellow"),
        )
    ]
    first = tmp_path / "sheet-1.png"
    second = tmp_path / "sheet-2.png"

    render_contact_sheet(items, first)
    render_contact_sheet(items, second)

    assert sha256(first) == sha256(second)
    with Image.open(first) as sheet:
        assert sheet.mode == "RGB"
        assert sheet.width > 3 * 300
        assert sheet.height > 2 * 300
        samples = [
            sheet.getpixel((204, 186)),
            sheet.getpixel((564, 186)),
            sheet.getpixel((924, 186)),
            sheet.getpixel((204, 570)),
        ]
    assert samples[0][0] > 200 and samples[0][1] < 80
    assert samples[1][1] > samples[1][0] and samples[1][1] > samples[1][2]
    assert samples[2][2] > 200 and samples[2][0] < 80
    assert samples[3][0] > 200 and samples[3][1] > 200


def test_render_contact_sheet_empty_state_is_readable_and_deterministic(tmp_path):
    from scripts.build_exercise_contact_sheet import render_contact_sheet

    first = tmp_path / "empty-1.png"
    second = tmp_path / "empty-2.png"

    render_contact_sheet([], first)
    render_contact_sheet([], second)

    assert sha256(first) == sha256(second)
    with Image.open(first) as sheet:
        assert sheet.size == (1128, 432)
        background = sheet.getpixel((0, 0))
        center_band = sheet.crop((300, 180, 828, 250))
        blank = Image.new("RGB", center_band.size, background)
        assert ImageChops.difference(center_band, blank).getbbox() is not None


def test_render_contact_sheet_one_card_draws_manifest_code_and_status(
    tmp_path, monkeypatch
):
    from scripts.build_exercise_contact_sheet import ContactSheetItem, render_contact_sheet

    card = solid_image(tmp_path / "row.png", (1254, 1254), "red")
    item = ContactSheetItem(code="seated_row", card=card, status="candidate")
    drawn_text: list[str] = []
    original_text = ImageDraw.ImageDraw.text

    def recording_text(draw, xy, text, *args, **kwargs):
        drawn_text.append(text)
        return original_text(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", recording_text)
    output = tmp_path / "one.png"

    render_contact_sheet([item], output)

    assert drawn_text == ["seated_row", "status: candidate"]
    assert "row" not in drawn_text
    with Image.open(output) as sheet:
        assert sheet.size == (1128, 432)
        assert sheet.getpixel((204, 186))[0] > 200
        assert sheet.getpixel((564, 186)) == sheet.getpixel((0, 0))


def test_candidate_item_discovery_preserves_manifest_code_when_filename_differs(tmp_path):
    from scripts.build_exercise_contact_sheet import (
        ContactSheetItem,
        candidate_items_from_manifest,
    )

    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    for name in ("row.png", "approved.png"):
        solid_image(asset_dir / name, (20, 20), "white")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exercises": {
                    "seated_row": {"card": "row.png", "status": "candidate"},
                    "approved": {"card": "approved.png", "status": "approved"},
                    "text": {"card": None, "status": "text_only"},
                },
            }
        ),
        encoding="utf-8",
    )

    items = candidate_items_from_manifest(manifest, asset_dir)

    assert items == [
        ContactSheetItem(
            code="seated_row",
            card=asset_dir / "row.png",
            status="candidate",
        )
    ]
