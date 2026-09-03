from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PIL import Image

REFERENCE_COUNT = 6
MIN_REFERENCE_EDGE = 800


def _validated_rgb(path: Path, *, min_edge: int) -> Image.Image:
    if not path.is_file():
        raise ValueError("reference image is missing")
    with Image.open(path) as source:
        source.verify()
    with Image.open(path) as source:
        rgb = source.convert("RGB")
    if min(rgb.size) < min_edge:
        raise ValueError(f"reference image shortest edge must be at least {min_edge}px")
    return rgb


def _save_private_png(image: Image.Image, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True, compress_level=9)
    return output


def stage_identity_pack(
    reference_paths: Sequence[Path], private_root: Path
) -> tuple[Path, ...]:
    if len(reference_paths) != REFERENCE_COUNT:
        raise ValueError("identity pack must contain exactly six images")
    outputs: list[Path] = []
    for index, source_path in enumerate(reference_paths, start=1):
        image = _validated_rgb(source_path, min_edge=MIN_REFERENCE_EDGE)
        outputs.append(
            _save_private_png(image, private_root / "identity" / f"reference-{index:02d}.png")
        )
    return tuple(outputs)


def stage_technique_pair(
    start_path: Path, end_path: Path, private_root: Path
) -> tuple[Path, Path]:
    outputs: list[Path] = []
    for phase, source_path in (("start", start_path), ("end", end_path)):
        image = _validated_rgb(source_path, min_edge=700)
        if image.size != (760, 760):
            raise ValueError("hack-squat source phase must be the verified 760x760 image")
        outputs.append(
            _save_private_png(image, private_root / "hack_squat" / f"source-{phase}.png")
        )
    return outputs[0], outputs[1]
