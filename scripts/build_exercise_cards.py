from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = ROOT / "media_sources" / "fonts" / "NotoSans.ttf"
DEFAULT_MANIFEST = ROOT / "app" / "assets" / "exercises" / "manifest.json"
DEFAULT_ASSET_DIR = DEFAULT_MANIFEST.parent
DEFAULT_MEDIA_ROOT = ROOT / "media_sources"
DEFAULT_SOURCE_REPO = ROOT.parent / "free-exercise-db"

SOURCE_PROVIDER = "free-exercise-db"
SOURCE_REPOSITORY_URL = "https://github.com/yuhonas/free-exercise-db.git"
SOURCE_WEB_URL = "https://github.com/yuhonas/free-exercise-db"
PINNED_SOURCE_REVISION = "a859101d633a01c4a1a920d6a8ce41dabba0705f"
SOURCE_VERIFIED_AT = "2026-09-02"
LICENSE_BLOCK_START = "<!-- BEGIN managed free-exercise-db license -->"
LICENSE_BLOCK_END = "<!-- END managed free-exercise-db license -->"

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
class SourcePair:
    code: str
    upstream_dir: str
    start_file: str
    end_file: str
    title: str
    start_hint: str
    end_hint: str
    cardio: bool = False


SOURCE_PAIRS = (
    SourcePair(
        "cardio_treadmill",
        "Walking_Treadmill",
        "0.jpg",
        "1.jpg",
        "Ходьба на дорожке",
        "Выпрямись и начни с ходьбы",
        "Двигайся в разговорном темпе",
        cardio=True,
    ),
    SourcePair(
        "cardio_elliptical",
        "Elliptical_Trainer",
        "0.jpg",
        "1.jpg",
        "Эллиптический тренажёр",
        "Стопы полностью на педалях",
        "Двигайся плавно, без рывков",
        cardio=True,
    ),
    SourcePair(
        "cardio_bike",
        "Bicycling_Stationary",
        "0.jpg",
        "1.jpg",
        "Велотренажёр",
        "Колено внизу слегка согнуто",
        "Крути педали без раскачивания таза",
        cardio=True,
    ),
    SourcePair(
        "seated_leg_curl",
        "Seated_Leg_Curl",
        "0.jpg",
        "1.jpg",
        "Сгибание ног сидя",
        "Колени совпадают с осью тренажёра",
        "Согни колени, удерживая таз на сиденье",
    ),
    SourcePair(
        "hip_abduction",
        "Thigh_Abductor",
        "0.jpg",
        "1.jpg",
        "Отведение бёдер",
        "Спина прижата, колени у подушек",
        "Разведи колени без рывка",
    ),
    SourcePair(
        "lat_pulldown",
        "Wide-Grip_Lat_Pulldown",
        "0.jpg",
        "1.jpg",
        "Тяга верхнего блока",
        "Бёдра зафиксированы, плечи опущены",
        "Веди локти вниз к бокам",
    ),
    SourcePair(
        "chest_press",
        "Leverage_Chest_Press",
        "0.jpg",
        "1.jpg",
        "Жим в тренажёре",
        "Рукояти на уровне середины груди",
        "Выжми вперёд без блокировки локтей",
    ),
    SourcePair(
        "hack_squat",
        "Hack_Squat",
        "0.jpg",
        "1.jpg",
        "Гакк-приседания",
        "Спина и таз прижаты к опоре",
        "Опустись до комфортной глубины под контролем",
    ),
    SourcePair(
        "leg_extension",
        "Leg_Extensions",
        "0.jpg",
        "1.jpg",
        "Разгибание ног сидя",
        "Колени совпадают с осью тренажёра",
        "Разогни ноги без жёсткой блокировки",
    ),
    SourcePair(
        "hip_adduction",
        "Thigh_Adductor",
        "0.jpg",
        "1.jpg",
        "Сведение бёдер",
        "Спина прижата, амплитуда комфортная",
        "Сведи колени плавно",
    ),
    SourcePair(
        "seated_row",
        "Seated_Cable_Rows",
        "0.jpg",
        "1.jpg",
        "Горизонтальная тяга",
        "Спина нейтральна, плечи опущены",
        "Веди локти близко к корпусу",
    ),
    SourcePair(
        "leg_press",
        "Leg_Press",
        "1.jpg",
        "0.jpg",
        "Жим ногами",
        "Таз и спина прижаты к опоре",
        "Выжми платформу без блокировки коленей",
    ),
    SourcePair(
        "machine_shoulder_press",
        "Leverage_Shoulder_Press",
        "0.jpg",
        "1.jpg",
        "Жим вверх в тренажёре",
        "Рукояти примерно на уровне плеч",
        "Выжми вверх, не поднимая плечи",
    ),
    SourcePair(
        "pec_deck",
        "Butterfly",
        "1.jpg",
        "0.jpg",
        "Сведение рук в тренажёре",
        "Рукояти на уровне середины груди",
        "Сведи руки, сохраняя угол в локтях",
    ),
)


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


@dataclass(frozen=True, slots=True)
class SinglePhotoCardSpec:
    title: str
    image: Path
    hint: str
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


def render_single_photo_card(spec: SinglePhotoCardSpec, output: Path) -> None:
    canvas = Image.new("RGB", CANVAS_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    title_font = _font(48)
    hint_font = _font(30)
    attribution_font = _font(21)
    image_box = (48, 125, CANVAS_SIZE[0] - 48, 1010)
    image_width = image_box[2] - image_box[0]
    image_height = image_box[3] - image_box[1]

    draw.text(
        (CANVAS_SIZE[0] // 2, 35),
        spec.title,
        font=title_font,
        fill=TEXT_COLOR,
        anchor="ma",
    )
    with Image.open(spec.image) as source:
        photo = ImageOps.fit(
            source.convert("RGB"),
            (image_width, image_height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    canvas.paste(photo, image_box[:2])
    draw.rectangle(image_box, outline=BORDER_COLOR, width=2)
    hint_lines = _wrap_two_lines(draw, spec.hint, hint_font, image_width - 64)
    _draw_centered_lines(
        draw,
        hint_lines,
        center_x=CANVAS_SIZE[0] // 2,
        top=1045,
        font=hint_font,
    )
    draw.text(
        (CANVAS_SIZE[0] // 2, 1210),
        spec.attribution,
        font=attribution_font,
        fill=TEXT_COLOR,
        anchor="ma",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True, compress_level=9)


def card_spec_for(
    pair: SourcePair, source_dir: Path
) -> CardSpec | SinglePhotoCardSpec:
    if pair.cardio:
        return SinglePhotoCardSpec(
            title=pair.title,
            image=source_dir / "start.jpg",
            hint=f"{pair.start_hint}. {pair.end_hint}",
            attribution="free-exercise-db · Unlicense",
        )
    return CardSpec(
        title=pair.title,
        start_image=source_dir / "start.jpg",
        end_image=source_dir / "end.jpg",
        start_label="Исходное положение",
        end_label="Конечное положение",
        start_hint=pair.start_hint,
        end_hint=pair.end_hint,
        attribution="free-exercise-db · Unlicense",
    )


def _git_output(source_repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(source_repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _relative_source(pair: SourcePair, filename: str) -> str:
    return f"exercises/{pair.upstream_dir}/{filename}"


def _source_id(relative_source: str) -> str:
    return f"{SOURCE_PROVIDER}:{PINNED_SOURCE_REVISION}:{relative_source}"


def _sha256(path: Path) -> str:
    data = path.read_bytes()
    if not data:
        raise ValueError(f"source file is empty: {path}")
    return hashlib.sha256(data).hexdigest()


def _load_manifest(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("exercise asset manifest must use schema version 1")
    if not isinstance(manifest.get("exercises"), dict):
        raise ValueError("exercise asset manifest must contain exercises")
    return manifest


def _verify_source_checkout(source_repo: Path) -> tuple[str, str]:
    if not source_repo.is_dir():
        raise ValueError(f"free-exercise-db checkout is missing: {source_repo}")
    revision = _git_output(source_repo, "rev-parse", "HEAD")
    if revision != PINNED_SOURCE_REVISION or len(revision) != 40:
        raise ValueError("free-exercise-db checkout is not at the pinned revision")
    origin = _git_output(source_repo, "remote", "get-url", "origin")
    if origin != SOURCE_REPOSITORY_URL:
        raise ValueError("free-exercise-db checkout has an unexpected origin")

    license_path = source_repo / "LICENSE.md"
    license_text = license_path.read_text(encoding="utf-8")
    if "released into the public domain" not in license_text:
        raise ValueError("free-exercise-db Unlicense text is unavailable")

    required_paths = ["LICENSE.md"]
    for pair in SOURCE_PAIRS:
        required_paths.extend(
            (_relative_source(pair, pair.start_file), _relative_source(pair, pair.end_file))
        )
    drift = _git_output(source_repo, "status", "--short", "--", *required_paths)
    if drift:
        raise ValueError("free-exercise-db required source files differ from the pinned revision")
    for relative_source in required_paths[1:]:
        if not (source_repo / relative_source).is_file():
            raise ValueError(f"free-exercise-db source file is missing: {relative_source}")
    return revision, license_text


def _license_markdown(revision: str, license_text: str) -> str:
    return (
        f"{LICENSE_BLOCK_START}\n"
        "## free-exercise-db\n\n"
        f"- Repository: {SOURCE_WEB_URL}\n"
        f"- Pinned revision: `{revision}`\n"
        "- License: Unlicense\n"
        f"- License file: {SOURCE_WEB_URL}/blob/{revision}/LICENSE.md\n\n"
        f"Source records use `verified_at: {SOURCE_VERIFIED_AT}` for the date when "
        "the local bytes, attribution, and license metadata were checked.\n\n"
        "Upstream license text at the pinned revision:\n\n"
        "```text\n"
        f"{license_text.rstrip()}\n"
        "```\n"
        f"{LICENSE_BLOCK_END}\n"
    )


def _merge_license_markdown(existing: str, managed_block: str) -> str:
    if LICENSE_BLOCK_START in existing or LICENSE_BLOCK_END in existing:
        if existing.count(LICENSE_BLOCK_START) != 1 or existing.count(LICENSE_BLOCK_END) != 1:
            raise ValueError("managed free-exercise-db license block is malformed")
        start = existing.index(LICENSE_BLOCK_START)
        end = existing.index(LICENSE_BLOCK_END, start) + len(LICENSE_BLOCK_END)
        return existing[:start] + managed_block.rstrip() + existing[end:]

    heading = "## free-exercise-db"
    if heading not in existing:
        prefix = existing.rstrip()
        return f"{prefix}\n\n{managed_block}" if prefix else f"# Exercise photo licenses\n\n{managed_block}"

    start = existing.index(heading)
    next_heading = existing.find("\n## ", start + len(heading))
    prefix = existing[:start]
    suffix = existing[next_heading + 1 :] if next_heading != -1 else ""
    merged = f"{prefix}{managed_block.rstrip()}\n"
    if suffix:
        merged += f"\n{suffix.lstrip()}"
    return merged


def build_candidate_cards(
    *,
    source_repo: Path = DEFAULT_SOURCE_REPO,
    manifest_path: Path = DEFAULT_MANIFEST,
    asset_dir: Path = DEFAULT_ASSET_DIR,
    media_root: Path = DEFAULT_MEDIA_ROOT,
) -> None:
    revision, license_text = _verify_source_checkout(source_repo)
    manifest = _load_manifest(manifest_path)
    exercises = manifest["exercises"]
    assert isinstance(exercises, dict)

    license_path = media_root / "LICENSES.md"
    license_path.parent.mkdir(parents=True, exist_ok=True)
    existing_license_text = (
        license_path.read_text(encoding="utf-8") if license_path.is_file() else ""
    )
    license_path.write_text(
        _merge_license_markdown(
            existing_license_text,
            _license_markdown(revision, license_text),
        ),
        encoding="utf-8",
    )

    existing_licenses = manifest.get("licenses")
    if not isinstance(existing_licenses, dict):
        raise ValueError("exercise asset manifest licenses must be an object")
    licenses = dict(existing_licenses)
    licenses[SOURCE_PROVIDER] = {
        "provider": SOURCE_PROVIDER,
        "repository_url": SOURCE_WEB_URL,
        "repository_revision": revision,
        "license": "Unlicense",
        "license_url": f"{SOURCE_WEB_URL}/blob/{revision}/LICENSE.md",
    }
    manifest["licenses"] = licenses

    existing_sources = manifest.get("sources")
    if not isinstance(existing_sources, dict):
        raise ValueError("exercise asset manifest sources must be an object")
    source_records: dict[str, object] = {
        source_id: record
        for source_id, record in existing_sources.items()
        if not (
            source_id.startswith(f"{SOURCE_PROVIDER}:")
            or (isinstance(record, dict) and record.get("provider") == SOURCE_PROVIDER)
        )
    }

    for pair in SOURCE_PAIRS:
        raw_exercise = exercises.get(pair.code)
        if not isinstance(raw_exercise, dict):
            raise ValueError(f"manifest exercise is missing: {pair.code}")
        exercise_source_ids: list[str] = []
        copied_dir = media_root / "exercises" / pair.code
        copied_dir.mkdir(parents=True, exist_ok=True)
        roles = ("setup", "working") if pair.cardio else ("start", "end")

        for local_name, upstream_name, role in zip(
            ("start.jpg", "end.jpg"),
            (pair.start_file, pair.end_file),
            roles,
            strict=True,
        ):
            relative_source = _relative_source(pair, upstream_name)
            source_file = source_repo / relative_source
            checksum = _sha256(source_file)
            copied_file = copied_dir / local_name
            shutil.copyfile(source_file, copied_file)
            if _sha256(copied_file) != checksum:
                raise ValueError(f"copied source checksum mismatch: {pair.code}/{local_name}")

            source_id = _source_id(relative_source)
            if source_id in source_records:
                raise ValueError(f"duplicate exercise source id: {source_id}")
            source_records[source_id] = {
                "provider": SOURCE_PROVIDER,
                "repository_revision": revision,
                "source_url": (
                    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/"
                    f"{revision}/{relative_source}"
                ),
                "upstream_path": relative_source,
                "local_path": f"media_sources/exercises/{pair.code}/{local_name}",
                "author": "free-exercise-db contributors",
                "license": "Unlicense",
                "license_url": f"{SOURCE_WEB_URL}/blob/{revision}/LICENSE.md",
                "sha256": checksum,
                "role": role,
                "verified_at": SOURCE_VERIFIED_AT,
            }
            exercise_source_ids.append(source_id)

        output = asset_dir / f"{pair.code}.png"
        card_spec = card_spec_for(pair, copied_dir)
        if isinstance(card_spec, SinglePhotoCardSpec):
            render_single_photo_card(card_spec, output)
        else:
            render_card(card_spec, output)
        raw_exercise.update(
            {
                "card": output.name,
                "status": "candidate",
                "sha256": _sha256(output),
                "source_ids": exercise_source_ids,
            }
        )

    manifest["sources"] = source_records
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _required_text(record: dict[str, object], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} needs a non-empty {key}")
    return value


def _required_https_url(record: dict[str, object], key: str, context: str) -> str:
    value = _required_text(record, key, context)
    if not value.startswith("https://") or len(value) <= len("https://"):
        raise ValueError(f"{context} has an invalid {key}")
    return value


def _validate_license_records(licenses: object) -> dict[str, dict[str, object]]:
    if not isinstance(licenses, dict) or not licenses:
        raise ValueError("exercise license metadata is missing")
    validated: dict[str, dict[str, object]] = {}
    for provider, raw_license in licenses.items():
        if not isinstance(provider, str) or not provider or not isinstance(raw_license, dict):
            raise ValueError("exercise license record is malformed")
        context = f"license record {provider!r}"
        if raw_license.get("provider") != provider:
            raise ValueError(f"{context} has an invalid provider")
        _required_text(raw_license, "license", context)
        _required_https_url(raw_license, "license_url", context)
        validated[provider] = raw_license
    return validated


def _local_source_path(local_path: str, media_root: Path, context: str) -> Path:
    relative = PurePosixPath(local_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.parts[0] != "media_sources"
        or ".." in relative.parts
    ):
        raise ValueError(f"{context} has an unsafe local_path")
    root = media_root.resolve()
    source_path = root.joinpath(*relative.parts[1:]).resolve()
    try:
        source_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{context} points outside media_sources") from exc
    return source_path


def _validate_source_record(
    *,
    source_id: str,
    record: object,
    expected_role: str,
    licenses: dict[str, dict[str, object]],
    media_root: Path,
) -> tuple[str, str]:
    context = f"exercise source {source_id!r}"
    if not isinstance(record, dict):
        raise ValueError(f"{context} record is missing")
    provider = _required_text(record, "provider", context)
    author = _required_text(record, "author", context)
    if not author:
        raise ValueError(f"{context} has no author")
    source_url = _required_https_url(record, "source_url", context)
    license_url = _required_https_url(record, "license_url", context)
    license_name = _required_text(record, "license", context)
    license_record = licenses.get(provider)
    if license_record is None:
        raise ValueError(f"{context} has no provider license record")
    if license_record.get("license") != license_name:
        raise ValueError(f"{context} license does not match its provider record")
    if license_record.get("license_url") != license_url:
        raise ValueError(f"{context} license URL does not match its provider record")
    if record.get("role") != expected_role:
        raise ValueError(f"{context} has invalid complementary phase roles")

    verified_at = _required_text(record, "verified_at", context)
    try:
        date.fromisoformat(verified_at)
    except ValueError as exc:
        raise ValueError(f"{context} has an invalid verified_at date") from exc

    checksum = _required_text(record, "sha256", context).lower()
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise ValueError(f"{context} has an invalid sha256")
    local_path = _required_text(record, "local_path", context)
    source_path = _local_source_path(local_path, media_root, context)
    if _sha256(source_path) != checksum:
        raise ValueError(f"{context} checksum does not match its source file")
    return local_path, source_url


def _validate_exercise_code(code: str) -> None:
    if re.fullmatch(r"[a-z][a-z0-9_]*", code) is None:
        raise ValueError(f"exercise code is unsafe: {code!r}")


def _safe_card_path(asset_dir: Path, card_name: object, code: str) -> Path:
    if not isinstance(card_name, str) or card_name != f"{code}.png":
        raise ValueError(f"exercise card path is invalid: {code}")
    root = asset_dir.resolve()
    card = (asset_dir / card_name).resolve()
    try:
        relative = card.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"exercise card points outside asset directory: {code}") from exc
    if not relative.parts:
        raise ValueError(f"exercise card path is invalid: {code}")
    return card


def _validate_card(code: str, exercise: dict[str, object], asset_dir: Path) -> None:
    card_name = exercise.get("card")
    checksum = exercise.get("sha256")
    card = _safe_card_path(asset_dir, card_name, code)
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise ValueError(f"exercise card checksum is invalid: {code}")
    if _sha256(card) != checksum.lower():
        raise ValueError(f"exercise card checksum mismatch: {code}")


def _validate_base_source_mapping(
    *,
    sources: dict[str, object],
    exercises: dict[str, object],
) -> None:
    for pair in SOURCE_PAIRS:
        exercise = exercises.get(pair.code)
        if not isinstance(exercise, dict):
            raise ValueError(f"manifest exercise is missing: {pair.code}")
        source_ids = exercise.get("source_ids")
        if not isinstance(source_ids, list):
            raise ValueError(f"exercise source ids are incomplete: {pair.code}")
        for local_name, upstream_name, actual_id in zip(
            ("start.jpg", "end.jpg"),
            (pair.start_file, pair.end_file),
            source_ids,
            strict=True,
        ):
            relative_source = _relative_source(pair, upstream_name)
            expected_id = _source_id(relative_source)
            if actual_id != expected_id:
                raise ValueError(f"exercise phase mapping is invalid: {pair.code}/{local_name}")
            record = sources.get(expected_id)
            if not isinstance(record, dict):
                raise ValueError(f"exercise source record is missing: {expected_id}")
            expected_values = {
                "provider": SOURCE_PROVIDER,
                "repository_revision": PINNED_SOURCE_REVISION,
                "upstream_path": relative_source,
                "local_path": f"media_sources/exercises/{pair.code}/{local_name}",
                "author": "free-exercise-db contributors",
                "license": "Unlicense",
                "license_url": (
                    f"{SOURCE_WEB_URL}/blob/{PINNED_SOURCE_REVISION}/LICENSE.md"
                ),
                "source_url": (
                    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/"
                    f"{PINNED_SOURCE_REVISION}/{relative_source}"
                ),
                "verified_at": SOURCE_VERIFIED_AT,
            }
            if any(record.get(key) != value for key, value in expected_values.items()):
                raise ValueError(f"exercise source metadata is invalid: {expected_id}")


def validate_sources(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    asset_dir: Path = DEFAULT_ASSET_DIR,
    media_root: Path = DEFAULT_MEDIA_ROOT,
) -> None:
    manifest = _load_manifest(manifest_path)
    licenses = _validate_license_records(manifest.get("licenses"))
    base_license = licenses.get(SOURCE_PROVIDER)
    if (
        base_license is None
        or base_license.get("license") != "Unlicense"
        or base_license.get("repository_revision") != PINNED_SOURCE_REVISION
    ):
        raise ValueError("free-exercise-db license metadata is invalid")

    sources = manifest.get("sources")
    exercises = manifest["exercises"]
    if not isinstance(sources, dict) or not isinstance(exercises, dict):
        raise ValueError("exercise source metadata is missing")

    referenced_source_ids: set[str] = set()
    local_paths: set[str] = set()
    for code, raw_exercise in exercises.items():
        if not isinstance(code, str) or not code or not isinstance(raw_exercise, dict):
            raise ValueError("exercise manifest entry is malformed")
        _validate_exercise_code(code)
        status = raw_exercise.get("status")
        source_ids = raw_exercise.get("source_ids")
        if status == "text_only":
            if source_ids != [] or raw_exercise.get("card") is not None:
                raise ValueError(f"text-only exercise has media metadata: {code}")
            continue
        if status not in {"candidate", "approved"}:
            raise ValueError(f"exercise has an invalid media status: {code}")
        if (
            not isinstance(source_ids, list)
            or len(source_ids) != 2
            or not all(isinstance(source_id, str) and source_id for source_id in source_ids)
            or len(set(source_ids)) != 2
        ):
            raise ValueError(f"exercise needs exactly two unique source ids: {code}")

        roles = ("setup", "working") if code.startswith("cardio_") else ("start", "end")
        for source_id, role in zip(source_ids, roles, strict=True):
            if source_id in referenced_source_ids:
                raise ValueError(f"exercise source id is referenced more than once: {source_id}")
            referenced_source_ids.add(source_id)
            local_path, _ = _validate_source_record(
                source_id=source_id,
                record=sources.get(source_id),
                expected_role=role,
                licenses=licenses,
                media_root=media_root,
            )
            if local_path in local_paths:
                raise ValueError(f"duplicate exercise source record: {source_id}")
            local_paths.add(local_path)
        _validate_card(code, raw_exercise, asset_dir)

    if set(sources) != referenced_source_ids:
        raise ValueError("manifest contains unreferenced or missing exercise source records")
    _validate_base_source_mapping(sources=sources, exercises=exercises)


def require_all_approved(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    asset_dir: Path = DEFAULT_ASSET_DIR,
    media_root: Path = DEFAULT_MEDIA_ROOT,
) -> None:
    validate_sources(
        manifest_path=manifest_path,
        asset_dir=asset_dir,
        media_root=media_root,
    )
    manifest = _load_manifest(manifest_path)
    exercises = manifest["exercises"]
    assert isinstance(exercises, dict)
    for code, raw_exercise in exercises.items():
        if not isinstance(raw_exercise, dict) or raw_exercise.get("status") != "approved":
            raise ValueError(f"exercise card is not approved: {code}")
        _validate_card(code, raw_exercise, asset_dir)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render deterministic exercise cards from verified local photographs."
    )
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--status", choices=("candidate",))
    actions.add_argument("--validate-sources", action="store_true")
    actions.add_argument("--require-all-approved", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--media-root", type=Path, default=DEFAULT_MEDIA_ROOT)
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE_REPO)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.status == "candidate":
            build_candidate_cards(
                source_repo=args.source_repo,
                manifest_path=args.manifest,
                asset_dir=args.asset_dir,
                media_root=args.media_root,
            )
        elif args.validate_sources:
            validate_sources(
                manifest_path=args.manifest,
                asset_dir=args.asset_dir,
                media_root=args.media_root,
            )
        else:
            require_all_approved(
                manifest_path=args.manifest,
                asset_dir=args.asset_dir,
                media_root=args.media_root,
            )
    except (FileNotFoundError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"exercise card build failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
