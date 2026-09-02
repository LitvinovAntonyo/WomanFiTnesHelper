from __future__ import annotations

import hashlib
import json

import pytest

from app import exercise_assets
from app.exercise_assets import (
    approved_asset_codes,
    asset_for,
    asset_key_for,
    card_path_for,
)


def write_manifest(tmp_path, exercises: dict[str, dict[str, object]]) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "licenses": {},
                "sources": {},
                "exercises": exercises,
            }
        ),
        encoding="utf-8",
    )


def use_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(exercise_assets, "ASSET_DIR", tmp_path)
    monkeypatch.setattr(exercise_assets, "MANIFEST_PATH", tmp_path / "manifest.json")


def test_manifest_loads_approved_card_with_checksum(tmp_path, monkeypatch):
    card = tmp_path / "leg_press.png"
    card.write_bytes(b"real-card")
    write_manifest(
        tmp_path,
        {
            "leg_press": {
                "card": "leg_press.png",
                "status": "approved",
                "sha256": hashlib.sha256(b"real-card").hexdigest(),
                "source_ids": [
                    "free-exercise-db:Leg_Press:1",
                    "free-exercise-db:Leg_Press:0",
                ],
            }
        },
    )
    use_manifest(monkeypatch, tmp_path)

    asset = asset_for("leg_press")

    assert asset is not None
    assert card_path_for("leg_press") == card
    assert asset_key_for("leg_press") == f"leg_press:{asset.sha256}"
    assert approved_asset_codes() == {"leg_press"}


def test_candidate_or_text_only_asset_uses_text_fallback(tmp_path, monkeypatch):
    write_manifest(
        tmp_path,
        {
            "candidate": {
                "card": "candidate.png",
                "status": "candidate",
                "sha256": None,
                "source_ids": [],
            },
            "glute_kickback": {
                "card": None,
                "status": "text_only",
                "sha256": None,
                "source_ids": [],
            },
        },
    )
    use_manifest(monkeypatch, tmp_path)

    assert card_path_for("candidate") is None
    assert asset_key_for("candidate") == "candidate:candidate"
    assert card_path_for("glute_kickback") is None
    assert asset_key_for("glute_kickback") == "glute_kickback:text-only"
    assert approved_asset_codes() == set()


def test_approved_manifest_rejects_checksum_mismatch(tmp_path, monkeypatch):
    card = tmp_path / "row.png"
    card.write_bytes(b"changed")
    write_manifest(
        tmp_path,
        {
            "seated_row": {
                "card": "row.png",
                "status": "approved",
                "sha256": "0" * 64,
                "source_ids": ["a", "b"],
            }
        },
    )
    use_manifest(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="checksum"):
        asset_for("seated_row")


def test_manifest_rejects_a_non_string_status(tmp_path, monkeypatch):
    write_manifest(
        tmp_path,
        {
            "seated_row": {
                "card": None,
                "status": ["approved"],
                "sha256": None,
                "source_ids": [],
            }
        },
    )
    use_manifest(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="status"):
        asset_for("seated_row")


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {
                "card": "../outside.png",
                "status": "approved",
                "sha256": "0" * 64,
                "source_ids": ["a", "b"],
            },
            "outside",
        ),
        (
            {
                "card": "row.png",
                "status": "approved",
                "sha256": "not-a-checksum",
                "source_ids": ["a", "b"],
            },
            "sha256",
        ),
        (
            {
                "card": "row.png",
                "status": "approved",
                "sha256": "0" * 64,
                "source_ids": ["a"],
            },
            "source",
        ),
    ],
)
def test_approved_manifest_rejects_unsafe_or_incomplete_entries(
    tmp_path, monkeypatch, entry, message
):
    if entry["card"] == "row.png":
        (tmp_path / "row.png").write_bytes(b"row-card")
    write_manifest(tmp_path, {"seated_row": entry})
    use_manifest(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match=message):
        asset_for("seated_row")


def test_initial_manifest_covers_all_reachable_v4_exercises():
    expected_codes = {
        "cardio_treadmill",
        "cardio_elliptical",
        "cardio_bike",
        "seated_leg_curl",
        "glute_kickback",
        "hip_abduction",
        "lat_pulldown",
        "chest_press",
        "hack_squat",
        "leg_extension",
        "hip_adduction",
        "seated_row",
        "leg_press",
        "machine_shoulder_press",
        "pec_deck",
    }

    assets = {code: asset_for(code) for code in expected_codes}

    assert all(asset is not None for asset in assets.values())
    assert assets["glute_kickback"].status == "text_only"
    assert all(
        assets[code].status == "candidate"
        for code in expected_codes - {"glute_kickback"}
    )
