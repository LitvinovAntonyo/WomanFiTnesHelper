from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ASSET_DIR = Path(__file__).resolve().parent / "assets" / "exercises"
MANIFEST_PATH = ASSET_DIR / "manifest.json"
_STATUS_VALUES = {"candidate", "approved", "text_only"}
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")


@dataclass(frozen=True, slots=True)
class ExerciseAsset:
    code: str
    card: Path | None
    status: Literal["candidate", "approved", "text_only"]
    sha256: str | None
    source_ids: tuple[str, ...]


def _load_entries() -> dict[str, object]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"exercise asset manifest is unavailable: {MANIFEST_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("exercise asset manifest is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("exercise asset manifest must be an object")
    if manifest.get("schema_version") != 1:
        raise ValueError("exercise asset manifest has an unsupported schema version")
    exercises = manifest.get("exercises")
    if not isinstance(exercises, dict):
        raise ValueError("exercise asset manifest must contain exercises")
    return exercises


def _safe_card_path(card_name: str) -> Path:
    asset_dir = ASSET_DIR.resolve()
    card_path = (ASSET_DIR / card_name).resolve()
    try:
        card_path.relative_to(asset_dir)
    except ValueError as exc:
        raise ValueError("exercise card path points outside the asset directory") from exc
    return card_path


def _parse_asset(code: str, raw_asset: object) -> ExerciseAsset:
    if not isinstance(raw_asset, dict):
        raise ValueError(f"exercise asset {code!r} must be an object")

    status = raw_asset.get("status")
    if not isinstance(status, str) or status not in _STATUS_VALUES:
        raise ValueError(f"exercise asset {code!r} has an invalid status")

    raw_card = raw_asset.get("card")
    if raw_card is not None and not isinstance(raw_card, str):
        raise ValueError(f"exercise asset {code!r} has an invalid card")
    card = _safe_card_path(raw_card) if raw_card is not None else None

    sha256 = raw_asset.get("sha256")
    if sha256 is not None and not isinstance(sha256, str):
        raise ValueError(f"exercise asset {code!r} has an invalid sha256")

    raw_source_ids = raw_asset.get("source_ids")
    if not isinstance(raw_source_ids, list) or not all(
        isinstance(source_id, str) and source_id for source_id in raw_source_ids
    ):
        raise ValueError(f"exercise asset {code!r} has invalid source ids")
    source_ids = tuple(raw_source_ids)

    if status == "approved":
        if card is None or not card.is_file():
            raise ValueError(f"approved exercise asset {code!r} needs an existing card")
        if sha256 is None or _SHA256_RE.fullmatch(sha256) is None:
            raise ValueError(f"approved exercise asset {code!r} needs a 64-hex sha256")
        if len(source_ids) != 2:
            raise ValueError(f"approved exercise asset {code!r} needs exactly two source ids")
        digest = hashlib.sha256(card.read_bytes()).hexdigest()
        if digest != sha256.lower():
            raise ValueError(f"approved exercise asset {code!r} checksum does not match card")

    return ExerciseAsset(
        code=code,
        card=card,
        status=status,
        sha256=sha256.lower() if sha256 is not None else None,
        source_ids=source_ids,
    )


def asset_for(code: str) -> ExerciseAsset | None:
    raw_asset = _load_entries().get(code)
    if raw_asset is None:
        return None
    return _parse_asset(code, raw_asset)


def card_path_for(code: str) -> Path | None:
    asset = asset_for(code)
    if asset is None or asset.status != "approved":
        return None
    return asset.card


def asset_key_for(code: str) -> str:
    asset = asset_for(code)
    if asset is None or asset.status == "text_only":
        return f"{code}:text-only"
    if asset.status == "approved":
        assert asset.sha256 is not None
        return f"{code}:{asset.sha256}"
    return f"{code}:candidate"


def approved_asset_codes() -> set[str]:
    return {
        code
        for code, raw_asset in _load_entries().items()
        if _parse_asset(code, raw_asset).status == "approved"
    }
