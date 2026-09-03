from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from app import exercise_assets
from app.exercise_assets import (
    approved_asset_codes,
    asset_for,
    asset_key_for,
    card_path_for,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPO = ROOT.parent / "free-exercise-db"
PINNED_REVISION = "a859101d633a01c4a1a920d6a8ce41dabba0705f"
EXPECTED_PHASES = {
    "cardio_treadmill": ("Walking_Treadmill", "0.jpg", "1.jpg"),
    "cardio_elliptical": ("Elliptical_Trainer", "0.jpg", "1.jpg"),
    "cardio_bike": ("Bicycling_Stationary", "0.jpg", "1.jpg"),
    "seated_leg_curl": ("Seated_Leg_Curl", "0.jpg", "1.jpg"),
    "hip_abduction": ("Thigh_Abductor", "0.jpg", "1.jpg"),
    "lat_pulldown": ("Wide-Grip_Lat_Pulldown", "0.jpg", "1.jpg"),
    "chest_press": ("Leverage_Chest_Press", "0.jpg", "1.jpg"),
    "hack_squat": ("Hack_Squat", "0.jpg", "1.jpg"),
    "leg_extension": ("Leg_Extensions", "0.jpg", "1.jpg"),
    "hip_adduction": ("Thigh_Adductor", "0.jpg", "1.jpg"),
    "seated_row": ("Seated_Cable_Rows", "0.jpg", "1.jpg"),
    "leg_press": ("Leg_Press", "1.jpg", "0.jpg"),
    "machine_shoulder_press": ("Leverage_Shoulder_Press", "0.jpg", "1.jpg"),
    "pec_deck": ("Butterfly", "1.jpg", "0.jpg"),
}


def batch_paths(tmp_path):
    manifest_path = tmp_path / "assets" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        (ROOT / "app" / "assets" / "exercises" / "manifest.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    asset_dir = manifest_path.parent
    media_root = tmp_path / "media_sources"
    args = [
        "--manifest",
        str(manifest_path),
        "--asset-dir",
        str(asset_dir),
        "--media-root",
        str(media_root),
        "--source-repo",
        str(SOURCE_REPO),
    ]
    return manifest_path, asset_dir, media_root, args


def add_glute_card(asset_dir: Path, media_root: Path) -> tuple[Path, Path, Path]:
    glute_dir = media_root / "exercises" / "glute_kickback"
    glute_dir.mkdir(parents=True, exist_ok=True)
    start = glute_dir / "start.jpg"
    end = glute_dir / "end.jpg"
    card = asset_dir / "glute_kickback.png"
    Image.new("RGB", (40, 40), "red").save(start, format="JPEG")
    Image.new("RGB", (40, 40), "blue").save(end, format="JPEG")
    Image.new("RGB", (1254, 1254), "white").save(card, format="PNG")
    return start, end, card


def second_provider_glute_records(start: Path, end: Path) -> tuple[dict, dict]:
    provider = "synthetic-commons"
    license_url = "https://creativecommons.org/publicdomain/zero/1.0/"
    license_record = {
        "provider": provider,
        "license": "CC0-1.0",
        "license_url": license_url,
    }
    records = {}
    for role, path in (("start", start), ("end", end)):
        source_id = f"{provider}:glute-kickback:{role}"
        records[source_id] = {
            "provider": provider,
            "source_url": f"https://example.invalid/glute-kickback/{role}.jpg",
            "local_path": f"media_sources/exercises/glute_kickback/{role}.jpg",
            "author": "Synthetic fixture author",
            "license": "CC0-1.0",
            "license_url": license_url,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "role": role,
            "verified_at": "2026-09-02",
        }
    return license_record, records


def write_manifest(tmp_path, exercises: object) -> None:
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


def test_manifest_rejects_a_present_null_exercise_entry(tmp_path, monkeypatch):
    write_manifest(tmp_path, {"leg_press": None})
    use_manifest(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="must be an object"):
        asset_for("leg_press")


def test_manifest_rejects_a_non_object_exercises_section(tmp_path, monkeypatch):
    write_manifest(tmp_path, [])
    use_manifest(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="must contain exercises"):
        asset_for("leg_press")


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
    glute_card = ROOT / "app" / "assets" / "exercises" / "glute_kickback.png"

    assert all(asset is not None for asset in assets.values())
    assert assets["glute_kickback"].status == "text_only"
    assert not glute_card.exists()
    assert card_path_for("glute_kickback") is None
    assert all(
        assets[code].status == "candidate"
        for code in expected_codes - {"glute_kickback"}
    )
    assert all(card_path_for(code) is None for code in expected_codes)


def test_public_domain_sources_match_pinned_upstream_bytes_and_phase_roles():
    manifest = json.loads(
        (ROOT / "app" / "assets" / "exercises" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["licenses"]["free-exercise-db"]["license"] == "Unlicense"
    assert manifest["licenses"]["free-exercise-db"]["repository_revision"] == PINNED_REVISION
    assert len(manifest["sources"]) == 28
    assert len(set(manifest["sources"])) == 28
    licenses_text = (ROOT / "media_sources" / "LICENSES.md").read_text(encoding="utf-8")
    assert f"Pinned revision: `{PINNED_REVISION}`" in licenses_text
    assert (SOURCE_REPO / "LICENSE.md").read_text(encoding="utf-8").strip() in licenses_text

    for code, (upstream_dir, first, second) in EXPECTED_PHASES.items():
        expected_roles = (
            ("setup", "working") if code.startswith("cardio_") else ("start", "end")
        )
        expected_files = (first, second)
        source_ids = manifest["exercises"][code]["source_ids"]
        assert len(source_ids) == 2

        for local_name, upstream_name, role, source_id in zip(
            ("start.jpg", "end.jpg"),
            expected_files,
            expected_roles,
            source_ids,
            strict=True,
        ):
            relative_source = f"exercises/{upstream_dir}/{upstream_name}"
            expected_id = f"free-exercise-db:{PINNED_REVISION}:{relative_source}"
            source = manifest["sources"][source_id]
            upstream = SOURCE_REPO / relative_source
            copied = ROOT / "media_sources" / "exercises" / code / local_name
            expected_sha = hashlib.sha256(upstream.read_bytes()).hexdigest()

            assert source_id == expected_id
            assert source["repository_revision"] == PINNED_REVISION
            assert source["upstream_path"] == relative_source
            assert source["local_path"] == f"media_sources/exercises/{code}/{local_name}"
            assert source["role"] == role
            assert source["sha256"] == expected_sha
            assert source["verified_at"] == "2026-09-02"
            assert date.fromisoformat(source["verified_at"]) == date(2026, 9, 2)
            assert copied.read_bytes() == upstream.read_bytes()

        card = ROOT / "app" / "assets" / "exercises" / f"{code}.png"
        with Image.open(card) as image:
            assert image.size == (1254, 1254)
        assert manifest["exercises"][code]["card"] == f"{code}.png"
        assert manifest["exercises"][code]["status"] == "candidate"
        assert manifest["exercises"][code]["sha256"] == hashlib.sha256(
            card.read_bytes()
        ).hexdigest()


def test_batch_cli_builds_deterministically_and_keeps_incomplete_approval_gate(
    tmp_path,
):
    from scripts.build_exercise_cards import main

    manifest_path, asset_dir, _, common_args = batch_paths(tmp_path)

    assert main(["--status", "candidate", *common_args]) == 0
    first_manifest = manifest_path.read_bytes()
    first_cards = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in asset_dir.glob("*.png")
    }
    assert len(first_cards) == 14
    assert "glute_kickback.png" not in first_cards
    assert main(["--validate-sources", *common_args]) == 0

    (asset_dir / "leg_press.png").write_bytes(b"tampered candidate")
    assert main(["--validate-sources", *common_args]) == 1

    assert main(["--status", "candidate", *common_args]) == 0
    second_cards = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in asset_dir.glob("*.png")
    }
    assert manifest_path.read_bytes() == first_manifest
    assert second_cards == first_cards
    assert main(["--require-all-approved", *common_args]) == 1
    assert manifest_path.read_bytes() == first_manifest


def test_base_rebuild_preserves_and_validates_a_second_provider_glute_pair(tmp_path):
    from scripts.build_exercise_cards import main

    manifest_path, asset_dir, media_root, common_args = batch_paths(tmp_path)
    assert main(["--status", "candidate", *common_args]) == 0
    start, end, card = add_glute_card(asset_dir, media_root)
    license_record, source_records = second_provider_glute_records(start, end)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_ids = list(source_records)
    stale_source_id = (
        "free-exercise-db:0000000000000000000000000000000000000000:"
        "exercises/Walking_Treadmill/0.jpg"
    )
    stale_source = deepcopy(next(iter(manifest["sources"].values())))
    stale_source["repository_revision"] = "0" * 40
    manifest["sources"][stale_source_id] = stale_source
    manifest["licenses"]["synthetic-commons"] = license_record
    manifest["sources"].update(source_records)
    manifest["exercises"]["glute_kickback"] = {
        "card": card.name,
        "status": "approved",
        "sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
        "source_ids": source_ids,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    license_doc = media_root / "LICENSES.md"
    license_doc.write_text(
        license_doc.read_text(encoding="utf-8")
        + "\n## synthetic-commons\n\nSynthetic fixture license notes.\n",
        encoding="utf-8",
    )

    assert main(["--status", "candidate", *common_args]) == 0

    rebuilt = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert stale_source_id not in rebuilt["sources"]
    assert rebuilt["licenses"]["synthetic-commons"] == license_record
    assert {source_id: rebuilt["sources"][source_id] for source_id in source_ids} == (
        source_records
    )
    assert rebuilt["exercises"]["glute_kickback"] == manifest["exercises"][
        "glute_kickback"
    ]
    assert "Synthetic fixture license notes." in license_doc.read_text(encoding="utf-8")
    assert main(["--validate-sources", *common_args]) == 0
    for exercise in rebuilt["exercises"].values():
        exercise["status"] = "approved"
    manifest_path.write_text(
        json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assert main(["--require-all-approved", *common_args]) == 0


def test_require_all_approved_rejects_glute_provenance_bypasses(tmp_path):
    from scripts.build_exercise_cards import main

    manifest_path, asset_dir, media_root, common_args = batch_paths(tmp_path)
    assert main(["--status", "candidate", *common_args]) == 0
    start, end, card = add_glute_card(asset_dir, media_root)
    base = json.loads(manifest_path.read_text(encoding="utf-8"))
    for exercise in base["exercises"].values():
        exercise["status"] = "approved"
    base["exercises"]["glute_kickback"].update(
        {
            "card": card.name,
            "sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
        }
    )
    _, unlicensed_records = second_provider_glute_records(start, end)
    scenarios = (
        ([], {}),
        (["missing:start", "missing:end"], {}),
        (list(unlicensed_records), unlicensed_records),
    )

    for source_ids, extra_sources in scenarios:
        manifest = deepcopy(base)
        manifest["exercises"]["glute_kickback"]["source_ids"] = source_ids
        manifest["sources"].update(extra_sources)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        assert main(["--require-all-approved", *common_args]) == 1


def test_validate_sources_rejects_unreferenced_duplicate_and_malformed_records(
    tmp_path,
):
    from scripts.build_exercise_cards import main

    manifest_path, asset_dir, media_root, common_args = batch_paths(tmp_path)
    assert main(["--status", "candidate", *common_args]) == 0
    start, end, card = add_glute_card(asset_dir, media_root)
    license_record, glute_records = second_provider_glute_records(start, end)
    base = json.loads(manifest_path.read_text(encoding="utf-8"))

    unreferenced = deepcopy(base)
    first_source = deepcopy(next(iter(unreferenced["sources"].values())))
    unreferenced["sources"]["unreferenced:record"] = first_source

    duplicate = deepcopy(base)
    duplicate["exercises"]["glute_kickback"] = {
        "card": card.name,
        "status": "approved",
        "sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
        "source_ids": duplicate["exercises"]["hack_squat"]["source_ids"],
    }

    malformed = deepcopy(base)
    malformed["licenses"]["synthetic-commons"] = license_record
    malformed["sources"].update(glute_records)
    malformed["sources"][next(iter(glute_records))].pop("author")
    malformed["exercises"]["glute_kickback"] = {
        "card": card.name,
        "status": "approved",
        "sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
        "source_ids": list(glute_records),
    }

    for manifest in (unreferenced, duplicate, malformed):
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        assert main(["--validate-sources", *common_args]) == 1


def test_validation_rejects_unsafe_exercise_codes_and_card_paths_without_hashing_outside(
    tmp_path, monkeypatch
):
    from scripts import build_exercise_cards as card_builder

    manifest_path, asset_dir, media_root, common_args = batch_paths(tmp_path)
    assert card_builder.main(["--status", "candidate", *common_args]) == 0
    start, end, _ = add_glute_card(asset_dir, media_root)
    license_record, source_records = second_provider_glute_records(start, end)
    base = json.loads(manifest_path.read_text(encoding="utf-8"))
    outside = tmp_path / "outside.png"
    Image.new("RGB", (32, 32), "purple").save(outside, format="PNG")
    outside_checksum = hashlib.sha256(outside.read_bytes()).hexdigest()
    symlink_card = asset_dir / "extra_symlink.png"
    symlink_card.symlink_to(outside)
    original_sha256 = card_builder._sha256

    def reject_outside_hash(path: Path) -> str:
        if path.resolve() == outside.resolve():
            raise AssertionError("validator attempted to hash a file outside asset_dir")
        return original_sha256(path)

    monkeypatch.setattr(card_builder, "_sha256", reject_outside_hash)
    scenarios = (
        ("../outside", "../outside.png"),
        ("extra_relative", "../outside.png"),
        ("extra_absolute", str(outside.resolve())),
        ("extra_symlink", symlink_card.name),
    )
    for code, card_name in scenarios:
        manifest = deepcopy(base)
        manifest["licenses"]["synthetic-commons"] = license_record
        manifest["sources"].update(source_records)
        manifest["exercises"][code] = {
            "card": card_name,
            "status": "approved",
            "sha256": outside_checksum,
            "source_ids": list(source_records),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        assert card_builder.main(["--validate-sources", *common_args]) == 1
