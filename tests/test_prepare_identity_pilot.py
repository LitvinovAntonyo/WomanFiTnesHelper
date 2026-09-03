from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image


def image(path: Path, color: str, size: tuple[int, int] = (900, 1200)) -> Path:
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def test_stage_identity_pack_copies_exactly_six_images_without_source_names(tmp_path):
    from scripts.prepare_identity_pilot import stage_identity_pack

    sources = [image(tmp_path / f"personal-name-{index}.png", "white") for index in range(6)]
    private_root = tmp_path / ".private" / "exercise-media"

    staged = stage_identity_pack(sources, private_root)

    assert [path.name for path in staged] == [f"reference-{index:02d}.png" for index in range(1, 7)]
    assert all(path.parent == private_root / "identity" for path in staged)
    assert all(path.is_file() for path in staged)
    assert not any("personal-name" in str(path) for path in private_root.rglob("*"))


def test_stage_identity_pack_rejects_any_count_other_than_six(tmp_path):
    from scripts.prepare_identity_pilot import stage_identity_pack

    sources = [image(tmp_path / f"ref-{index}.png", "white") for index in range(5)]

    with pytest.raises(ValueError, match="exactly six"):
        stage_identity_pack(sources, tmp_path / "private")


def test_repo_private_pilot_paths_are_git_ignored():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            ".private/exercise-media/reference.png",
            "review/local-ai-pilot/output.png",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        ".private/exercise-media/reference.png",
        "review/local-ai-pilot/output.png",
    ]


def test_stage_technique_pair_preserves_pixels_and_dimensions(tmp_path):
    from scripts.prepare_identity_pilot import stage_technique_pair

    start = image(tmp_path / "start.png", "red", (760, 760))
    end = image(tmp_path / "end.png", "blue", (760, 760))

    staged_start, staged_end = stage_technique_pair(start, end, tmp_path / "private")

    with Image.open(staged_start) as staged:
        assert staged.size == (760, 760)
        assert staged.getpixel((380, 380)) == (255, 0, 0)
    with Image.open(staged_end) as staged:
        assert staged.size == (760, 760)
        assert staged.getpixel((380, 380)) == (0, 0, 255)


def test_stage_identity_pack_rejects_a_small_reference(tmp_path):
    from scripts.prepare_identity_pilot import stage_identity_pack

    sources = [image(tmp_path / f"ref-{index}.png", "white") for index in range(5)]
    sources.append(image(tmp_path / "small.png", "white", (799, 1200)))

    with pytest.raises(ValueError, match="shortest edge"):
        stage_identity_pack(sources, tmp_path / "private")
