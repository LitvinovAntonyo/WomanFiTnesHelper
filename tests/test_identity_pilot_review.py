from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


def image(path: Path, color: str, size: tuple[int, int]) -> Path:
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_normalize_generated_phase_resizes_square_without_cropping(tmp_path):
    from scripts.build_identity_pilot_review import normalize_generated_phase

    source = image(tmp_path / "source.png", "red", (760, 760))
    generated = image(tmp_path / "generated.png", "blue", (1024, 1024))
    output = normalize_generated_phase(generated, source, tmp_path / "normalized.png")

    with Image.open(output) as result:
        assert result.size == (760, 760)
        assert result.mode == "RGB"
        assert result.getpixel((380, 380)) == (0, 0, 255)


def test_normalize_generated_phase_rejects_changed_aspect_ratio(tmp_path):
    from scripts.build_identity_pilot_review import normalize_generated_phase

    source = image(tmp_path / "source.png", "red", (760, 760))
    generated = image(tmp_path / "generated.png", "blue", (1024, 768))

    with pytest.raises(ValueError, match="aspect ratio"):
        normalize_generated_phase(generated, source, tmp_path / "normalized.png")


def test_review_artifacts_are_deterministic_and_do_not_touch_production(tmp_path):
    from scripts.build_identity_pilot_review import build_comparison, build_pilot_card

    source_start = image(tmp_path / "source-start.png", "red", (760, 760))
    source_end = image(tmp_path / "source-end.png", "blue", (760, 760))
    generated_start = image(tmp_path / "generated-start.png", "green", (760, 760))
    generated_end = image(tmp_path / "generated-end.png", "yellow", (760, 760))
    comparison_1 = build_comparison(
        source_start, source_end, generated_start, generated_end, tmp_path / "comparison-1.png"
    )
    comparison_2 = build_comparison(
        source_start, source_end, generated_start, generated_end, tmp_path / "comparison-2.png"
    )
    card_1 = build_pilot_card(generated_start, generated_end, tmp_path / "card-1.png")
    card_2 = build_pilot_card(generated_start, generated_end, tmp_path / "card-2.png")

    assert digest(comparison_1) == digest(comparison_2)
    assert digest(card_1) == digest(card_2)
    with Image.open(card_1) as card:
        assert card.size == (1254, 1254)


def test_validate_output_dir_rejects_a_path_outside_the_private_review_root(tmp_path):
    from scripts.build_identity_pilot_review import validate_output_dir

    allowed = tmp_path / "review" / "local-ai-pilot"

    with pytest.raises(ValueError, match="outside the private review directory"):
        validate_output_dir(tmp_path / "app" / "assets", allowed)


def test_cli_script_is_runnable_by_path():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "build_identity_pilot_review.py"), "--help"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--private-root" in result.stdout
