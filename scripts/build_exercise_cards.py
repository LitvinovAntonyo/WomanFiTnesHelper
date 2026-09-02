from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

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
        "Поднимись, не блокируя колени",
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
        "# Exercise photo licenses\n\n"
        "## free-exercise-db\n\n"
        f"- Repository: {SOURCE_WEB_URL}\n"
        f"- Pinned revision: `{revision}`\n"
        "- License: Unlicense\n"
        f"- License file: {SOURCE_WEB_URL}/blob/{revision}/LICENSE.md\n\n"
        "Upstream license text at the pinned revision:\n\n"
        "```text\n"
        f"{license_text.rstrip()}\n"
        "```\n"
    )


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
    license_path.write_text(_license_markdown(revision, license_text), encoding="utf-8")

    manifest["licenses"] = {
        SOURCE_PROVIDER: {
            "provider": SOURCE_PROVIDER,
            "repository_url": SOURCE_WEB_URL,
            "repository_revision": revision,
            "license": "Unlicense",
            "license_url": f"{SOURCE_WEB_URL}/blob/{revision}/LICENSE.md",
        }
    }
    source_records: dict[str, object] = {}

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
            }
            exercise_source_ids.append(source_id)

        output = asset_dir / f"{pair.code}.png"
        labels = (
            ("Настройка", "Рабочее положение")
            if pair.cardio
            else ("Исходное положение", "Конечное положение")
        )
        render_card(
            CardSpec(
                title=pair.title,
                start_image=copied_dir / "start.jpg",
                end_image=copied_dir / "end.jpg",
                start_label=labels[0],
                end_label=labels[1],
                start_hint=pair.start_hint,
                end_hint=pair.end_hint,
                attribution="free-exercise-db · Unlicense",
            ),
            output,
        )
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


def validate_sources(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    asset_dir: Path = DEFAULT_ASSET_DIR,
    media_root: Path = DEFAULT_MEDIA_ROOT,
) -> None:
    manifest = _load_manifest(manifest_path)
    licenses = manifest.get("licenses")
    if not isinstance(licenses, dict) or not isinstance(licenses.get(SOURCE_PROVIDER), dict):
        raise ValueError("free-exercise-db license metadata is missing")
    license_record = licenses[SOURCE_PROVIDER]
    assert isinstance(license_record, dict)
    if license_record.get("license") != "Unlicense":
        raise ValueError("free-exercise-db license metadata is invalid")
    if license_record.get("repository_revision") != PINNED_SOURCE_REVISION:
        raise ValueError("free-exercise-db manifest revision is not pinned")

    sources = manifest.get("sources")
    exercises = manifest["exercises"]
    if not isinstance(sources, dict) or not isinstance(exercises, dict):
        raise ValueError("exercise source metadata is missing")
    expected_source_ids: set[str] = set()

    for pair in SOURCE_PAIRS:
        raw_exercise = exercises.get(pair.code)
        if not isinstance(raw_exercise, dict):
            raise ValueError(f"manifest exercise is missing: {pair.code}")
        source_ids = raw_exercise.get("source_ids")
        if not isinstance(source_ids, list) or len(source_ids) != 2:
            raise ValueError(f"exercise source ids are incomplete: {pair.code}")
        roles = ("setup", "working") if pair.cardio else ("start", "end")

        for local_name, upstream_name, role, actual_id in zip(
            ("start.jpg", "end.jpg"),
            (pair.start_file, pair.end_file),
            roles,
            source_ids,
            strict=True,
        ):
            relative_source = _relative_source(pair, upstream_name)
            expected_id = _source_id(relative_source)
            if actual_id != expected_id:
                raise ValueError(f"exercise phase mapping is invalid: {pair.code}/{local_name}")
            if expected_id in expected_source_ids:
                raise ValueError(f"duplicate exercise source id: {expected_id}")
            expected_source_ids.add(expected_id)
            record = sources.get(expected_id)
            if not isinstance(record, dict):
                raise ValueError(f"exercise source record is missing: {expected_id}")
            expected_local = f"media_sources/exercises/{pair.code}/{local_name}"
            expected_values = {
                "provider": SOURCE_PROVIDER,
                "repository_revision": PINNED_SOURCE_REVISION,
                "upstream_path": relative_source,
                "local_path": expected_local,
                "author": "free-exercise-db contributors",
                "license": "Unlicense",
                "license_url": (
                    f"{SOURCE_WEB_URL}/blob/{PINNED_SOURCE_REVISION}/LICENSE.md"
                ),
                "role": role,
            }
            if any(record.get(key) != value for key, value in expected_values.items()):
                raise ValueError(f"exercise source metadata is invalid: {expected_id}")
            expected_url = (
                "https://raw.githubusercontent.com/yuhonas/free-exercise-db/"
                f"{PINNED_SOURCE_REVISION}/{relative_source}"
            )
            if record.get("source_url") != expected_url:
                raise ValueError(f"exercise source URL is invalid: {expected_id}")
            copied = media_root / "exercises" / pair.code / local_name
            checksum = record.get("sha256")
            if not isinstance(checksum, str) or len(checksum) != 64:
                raise ValueError(f"exercise source checksum is invalid: {expected_id}")
            if _sha256(copied) != checksum:
                raise ValueError(f"exercise source checksum mismatch: {expected_id}")

        card_name = raw_exercise.get("card")
        card_checksum = raw_exercise.get("sha256")
        if card_name != f"{pair.code}.png":
            raise ValueError(f"exercise candidate card path is invalid: {pair.code}")
        if not isinstance(card_checksum, str) or len(card_checksum) != 64:
            raise ValueError(f"exercise candidate card checksum is invalid: {pair.code}")
        if _sha256(asset_dir / card_name) != card_checksum:
            raise ValueError(f"exercise candidate card checksum mismatch: {pair.code}")

    if set(sources) != expected_source_ids:
        raise ValueError("manifest contains unexpected or missing exercise source records")


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
        card_name = raw_exercise.get("card")
        checksum = raw_exercise.get("sha256")
        if not isinstance(card_name, str) or not isinstance(checksum, str):
            raise ValueError(f"approved exercise card metadata is incomplete: {code}")
        card = asset_dir / card_name
        if _sha256(card) != checksum:
            raise ValueError(f"approved exercise card checksum mismatch: {code}")


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
