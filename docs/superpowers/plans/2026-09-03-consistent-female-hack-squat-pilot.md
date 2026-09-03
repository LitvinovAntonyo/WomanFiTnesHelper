# Consistent Female Hack-Squat Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one private, non-production `hack_squat` start/end review pair showing the same approved woman and outfit while preserving the verified exercise geometry.

**Architecture:** Stage the six identity references behind a Git-ignored private boundary, then use the built-in ImageGen edit flow on each verified hack-squat phase with identical identity and outfit constraints. Normalize only image size, render labels deterministically, and present an original-versus-output comparison for geometry and identity review before any production asset can change.

**Tech Stack:** Python 3.14, Pillow, pytest, existing deterministic card renderer, built-in ImageGen `identity-preserve` edit workflow.

**Spec:** `docs/superpowers/specs/2026-09-03-consistent-female-exercise-media-design.md`

## Global Constraints

- Process only `hack_squat`; do not start another exercise in this plan.
- The verified source photographs remain the source of truth for pose, phase, equipment, camera, crop, scale, and every body-to-machine contact point.
- Use the same complete six-photo identity pack for both phases.
- The fixed appearance is: the same adult woman, very slim naturally athletic silhouette, natural second-size breast proportions, high smooth ponytail, minimal black sports top, very short fitted high-waisted black sports shorts, opaque logo-free fabric, no jewellery, and no visible tattoos.
- If resemblance conflicts with exercise geometry, preserve geometry and reject the output.
- Personal reference photographs and generated likeness outputs must remain Git-ignored and must not appear in logs, fixtures, committed reports, or production assets.
- Use the built-in ImageGen tool, not the CLI/API fallback.
- AI must not render Russian labels, instructions, logos, or watermarks.
- Allow at most one targeted retry per phase. Never use a distorted output as a new technique source.
- Do not change `app/assets/exercises/manifest.json`, `app/assets/exercises/hack_squat.png`, any workout logic, Telegram delivery, or the VPS.
- Stop at the explicit human review gate.

---

### Task 1: Private identity and pilot-input boundary

**Files:**
- Modify: `.gitignore`
- Create: `scripts/prepare_identity_pilot.py`
- Create: `tests/test_prepare_identity_pilot.py`

**Interfaces:**
- Consumes: six existing local reference-image paths and the verified files `media_sources/exercises/hack_squat/start.jpg` and `media_sources/exercises/hack_squat/end.jpg`
- Produces: `stage_identity_pack(reference_paths: Sequence[Path], private_root: Path) -> tuple[Path, ...]`
- Produces: `stage_technique_pair(start_path: Path, end_path: Path, private_root: Path) -> tuple[Path, Path]`
- Produces private files under `.private/exercise-media/`; no original attachment path is persisted

- [ ] **Step 1: Add failing tests for the private boundary and exact reference count**

```python
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
        ["git", "check-ignore", ".private/exercise-media/reference.png", "review/local-ai-pilot/output.png"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        ".private/exercise-media/reference.png",
        "review/local-ai-pilot/output.png",
    ]
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_prepare_identity_pilot.py
```

Expected: FAIL because `scripts.prepare_identity_pilot` and the ignore rules do not exist.

- [ ] **Step 3: Add narrow Git-ignore rules**

Append exactly:

```gitignore
.private/exercise-media/
review/local-ai-pilot/
```

Do not ignore all of `.private/` or all of `review/`.

- [ ] **Step 4: Implement strict image staging**

```python
from __future__ import annotations

import hashlib
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
        outputs.append(_save_private_png(image, private_root / "hack_squat" / f"source-{phase}.png"))
    return outputs[0], outputs[1]
```

Do not print source paths or image metadata. Remove the unused `hashlib` import if the final implementation does not use it.

- [ ] **Step 5: Add source-lock and minimum-quality tests**

```python
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
```

- [ ] **Step 6: Run focused and full verification**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_prepare_identity_pilot.py
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check scripts/prepare_identity_pilot.py tests/test_prepare_identity_pilot.py
./.venv/bin/python -m compileall -q scripts tests
git diff --check
```

Expected: all tests and static checks pass.

- [ ] **Step 7: Stage the real private inputs without printing their paths**

Call `stage_identity_pack` with the six current conversation attachments and
`stage_technique_pair` with the two verified hack-squat source paths. Resolve the
attachment paths from the active conversation; do not copy them into a committed
command, report, test, or plan amendment.

Expected private outputs:

```text
.private/exercise-media/identity/reference-01.png through reference-06.png
.private/exercise-media/hack_squat/source-start.png
.private/exercise-media/hack_squat/source-end.png
```

Run:

```bash
git check-ignore .private/exercise-media/identity/reference-01.png
git status --short
```

Expected: the private path is ignored; status lists only the intended code/test/ignore changes.

- [ ] **Step 8: Commit only code, tests, and ignore rules**

```bash
git add .gitignore scripts/prepare_identity_pilot.py tests/test_prepare_identity_pilot.py
git commit -m "feat: stage private exercise identity pilot"
```

Before committing, run `git diff --cached --name-only` and fail if any private image or review output appears.

---

### Task 2: Deterministic pilot normalization and review artifacts

**Files:**
- Create: `scripts/build_identity_pilot_review.py`
- Create: `tests/test_identity_pilot_review.py`
- Reuse: `scripts/build_exercise_cards.py`

**Interfaces:**
- Consumes: the original and generated `hack_squat` phase images from the ignored pilot workspace
- Produces: `normalize_generated_phase(generated: Path, source: Path, output: Path) -> Path`
- Produces: `build_comparison(source_start: Path, source_end: Path, generated_start: Path, generated_end: Path, output: Path) -> Path`
- Produces: `build_pilot_card(generated_start: Path, generated_end: Path, output: Path) -> Path`

- [ ] **Step 1: Write failing tests for aspect-ratio safety and deterministic artifacts**

```python
from __future__ import annotations

import hashlib
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
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_identity_pilot_review.py
```

Expected: FAIL because `scripts.build_identity_pilot_review` does not exist.

- [ ] **Step 3: Implement lossless-shape normalization**

```python
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from scripts.build_exercise_cards import FONT_PATH, CardSpec, render_card


def normalize_generated_phase(generated: Path, source: Path, output: Path) -> Path:
    with Image.open(source) as source_image, Image.open(generated) as generated_image:
        source_ratio = source_image.width / source_image.height
        generated_ratio = generated_image.width / generated_image.height
        if abs(source_ratio - generated_ratio) > 0.001:
            raise ValueError("generated phase changed the source aspect ratio")
        normalized = generated_image.convert("RGB").resize(
            source_image.size, Image.Resampling.LANCZOS
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized.save(output, format="PNG", optimize=True, compress_level=9)
    return output
```

This function may resize but must never crop, pad, rotate, mirror, or perspective-correct a generated phase.

- [ ] **Step 4: Implement a four-panel comparison**

Create a deterministic 2×2 sheet with columns `Исходное положение` and
`Конечное положение`, rows `ОРИГИНАЛ` and `AI-ПИЛОТ`, and the footer
`НЕ ОДОБРЕНО · ПРОВЕРИТЬ ГЕОМЕТРИЮ И ЛИЦО`. Use the vendored Noto Sans font from
`FONT_PATH`; do not call AI for text. Each photo panel must use the same dimensions
and the same centered fit rule, so source and output can be compared directly.

The callable must have the exact signature:

```python
def build_comparison(
    source_start: Path,
    source_end: Path,
    generated_start: Path,
    generated_end: Path,
    output: Path,
) -> Path:
    panel_size = (720, 720)
    canvas = Image.new("RGB", (1560, 1660), "#F4F6F6")
    draw = ImageDraw.Draw(canvas)
    heading = ImageFont.truetype(FONT_PATH, size=36)
    row_label = ImageFont.truetype(FONT_PATH, size=30)
    footer = ImageFont.truetype(FONT_PATH, size=26)
    draw.text((420, 28), "Исходное положение", font=heading, fill="#263333", anchor="ma")
    draw.text((1140, 28), "Конечное положение", font=heading, fill="#263333", anchor="ma")
    draw.text((24, 420), "ОРИГИНАЛ", font=row_label, fill="#263333", anchor="lm")
    draw.text((24, 1160), "AI-ПИЛОТ", font=row_label, fill="#263333", anchor="lm")
    for source_path, position in (
        (source_start, (120, 80)),
        (source_end, (840, 80)),
        (generated_start, (120, 820)),
        (generated_end, (840, 820)),
    ):
        with Image.open(source_path) as source:
            panel = ImageOps.fit(source.convert("RGB"), panel_size, Image.Resampling.LANCZOS)
        canvas.paste(panel, position)
    draw.text(
        (780, 1580),
        "НЕ ОДОБРЕНО · ПРОВЕРИТЬ ГЕОМЕТРИЮ И ЛИЦО",
        font=footer,
        fill="#B3362D",
        anchor="ma",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True, compress_level=9)
    return output
```

- [ ] **Step 5: Reuse the card renderer for the pilot card**

```python
def build_pilot_card(generated_start: Path, generated_end: Path, output: Path) -> Path:
    spec = CardSpec(
        title="Гакк-приседания · AI-пилот",
        start_image=generated_start,
        end_image=generated_end,
        start_label="Исходное положение",
        end_label="Конечное положение",
        start_hint="Спина и таз прижаты к опоре",
        end_hint="Опустись до комфортной глубины под контролем",
        attribution="НЕ ОДОБРЕНО · техника: free-exercise-db (Unlicense)",
    )
    render_card(spec, output)
    return output
```

- [ ] **Step 6: Add a CLI that writes only inside the ignored review directory**

Add these exact boundaries and wire them through `argparse`:

```python
import argparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE_ROOT = ROOT / ".private" / "exercise-media"
DEFAULT_REVIEW_ROOT = ROOT / "review" / "local-ai-pilot"


def validate_output_dir(output_dir: Path, allowed_root: Path = DEFAULT_REVIEW_ROOT) -> Path:
    resolved = output_dir.resolve()
    if not resolved.is_relative_to(allowed_root.resolve()):
        raise ValueError("output path is outside the private review directory")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, default=DEFAULT_PRIVATE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REVIEW_ROOT)
    args = parser.parse_args()
    output_dir = validate_output_dir(args.output_dir)
    source_dir = args.private_root / "hack_squat"
    generated_start = normalize_generated_phase(
        source_dir / "generated-start-raw.png",
        source_dir / "source-start.png",
        source_dir / "generated-start.png",
    )
    generated_end = normalize_generated_phase(
        source_dir / "generated-end-raw.png",
        source_dir / "source-end.png",
        source_dir / "generated-end.png",
    )
    build_comparison(
        source_dir / "source-start.png",
        source_dir / "source-end.png",
        generated_start,
        generated_end,
        output_dir / "hack_squat-comparison.png",
    )
    build_pilot_card(
        generated_start,
        generated_end,
        output_dir / "hack_squat-card.png",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The CLI accepts `--private-root` and `--output-dir`, defaults respectively to
`.private/exercise-media` and `review/local-ai-pilot`, and refuses an output path
outside `review/local-ai-pilot` when run from the repository. It must build:

```text
review/local-ai-pilot/hack_squat-comparison.png
review/local-ai-pilot/hack_squat-card.png
```

It must not read or modify the production manifest.

- [ ] **Step 7: Run focused and full verification**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_identity_pilot_review.py tests/test_card_renderer.py
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check scripts/build_identity_pilot_review.py tests/test_identity_pilot_review.py
./.venv/bin/python -m compileall -q scripts tests
git diff --check
```

Expected: all tests and static checks pass.

- [ ] **Step 8: Commit only the deterministic builder and its tests**

```bash
git add scripts/build_identity_pilot_review.py tests/test_identity_pilot_review.py
git commit -m "feat: build private identity pilot review"
```

Before committing, run `git diff --cached --name-only` and fail if an image, identity reference, manifest, or production card is staged.

---

### Task 3: Built-in ImageGen identity-preserving pilot

**Files:**
- Read: `.private/exercise-media/identity/reference-01.png` through `reference-06.png`
- Read: `.private/exercise-media/hack_squat/source-start.png`
- Read: `.private/exercise-media/hack_squat/source-end.png`
- Create, ignored: `.private/exercise-media/hack_squat/generated-start.png`
- Create, ignored: `.private/exercise-media/hack_squat/generated-end.png`
- Create, ignored: `review/local-ai-pilot/hack_squat-comparison.png`
- Create, ignored: `review/local-ai-pilot/hack_squat-card.png`

**Interfaces:**
- Consumes: the staged sources from Task 1 and review builder from Task 2
- Produces: one start output and one end output using the same identity pack and fixed visual contract
- Produces: a deterministic review comparison and non-production card

- [ ] **Step 1: Confirm the private boundary before sending images to ImageGen**

Run:

```bash
git check-ignore .private/exercise-media/identity/reference-01.png
git check-ignore review/local-ai-pilot/hack_squat-card.png
git diff -- app/assets/exercises/manifest.json app/assets/exercises/hack_squat.png
```

Expected: both private paths are ignored and the production files have no diff.

- [ ] **Step 2: Inspect the start edit target and all six identity references**

Use `view_image` on the local start target and each reference before editing. Confirm
that the start target is the verified extended-knee phase and that the reference pack
contains the same adult woman in all six images. Do not infer or record her identity.

- [ ] **Step 3: Edit the start phase with the built-in ImageGen tool**

Use the built-in tool in `identity-preserve` edit mode. Supply the start source as the
edit target and all six identity images as references. Use this prompt:

```text
Use case: identity-preserve
Asset type: private non-production exercise-technique pilot, start phase
Input images: Image 1 is the edit target and the sole source of pose, machine, camera, crop, scale, lighting, and composition. Images 2-7 are one identity pack for the same adult woman and define only her facial identity, skin tone, eye colour, hair colour, and stable appearance.
Primary request: replace only the depicted person in Image 1 with the same adult woman from Images 2-7. Give her a very slim naturally athletic silhouette, natural second-size breast proportions, a high smooth ponytail, a minimal black sports top, and very short fitted high-waisted black sports shorts made from opaque logo-free fabric.
Style/medium: photorealistic natural gym photography; realistic skin and fabric texture.
Constraints: preserve Image 1's exact hack-squat start phase. Keep the head direction, gaze, shoulders, hands, spine, torso, pelvis, hips, knees, lower legs, feet, stance width, limb lengths, subject scale, camera, perspective, crop, lighting, shadows, background, and every machine part unchanged. Keep shoulders against the pads and feet at the exact original platform positions. Change only identity, hair, visible skin appearance, body surface styling, and clothing; do not move joints or equipment-contact points. No jewellery, tattoos, logos, text, or watermark.
Avoid: changed knee angle, changed foot placement, changed hand position, changed torso angle, changed machine geometry, extra fingers, merged limbs, exaggerated anatomy, glamour retouching, or a different woman.
```

The output is preview-only. Do not copy it over any project asset.

- [ ] **Step 4: Inspect the start output against the source**

Use `view_image` at original detail for both images. Reject immediately if any machine
part, joint, foot, hand, shoulder-pad contact, perspective, or crop changed. If geometry
passes but identity or outfit drifts, perform one targeted retry that repeats every
invariant and changes only the failed identity/outfit condition. Do not retry a geometry-
distorted output by using it as the edit target.

- [ ] **Step 5: Save the accepted start preview non-destructively**

Copy the selected built-in output from the exact local path returned in the tool's
output hint to:

```text
.private/exercise-media/hack_squat/generated-start-raw.png
```

Then normalize from the original source size without cropping:

```python
normalize_generated_phase(
    Path(".private/exercise-media/hack_squat/generated-start-raw.png"),
    Path(".private/exercise-media/hack_squat/source-start.png"),
    Path(".private/exercise-media/hack_squat/generated-start.png"),
)
```

- [ ] **Step 6: Inspect the end edit target and edit it with the same woman**

Use `view_image` on the verified bent-knee end target. Supply the end source as Image 1,
the same six identity references as Images 2-7, and the accepted start output as Image 8,
whose role is appearance consistency only. Use this prompt:

```text
Use case: identity-preserve
Asset type: private non-production exercise-technique pilot, end phase
Input images: Image 1 is the edit target and the sole source of pose, exercise phase, machine, camera, crop, scale, lighting, and composition. Images 2-7 are one identity pack for the same adult woman. Image 8 is the accepted start-phase pilot and defines only the exact hairstyle, outfit, body styling, and rendered facial consistency to match.
Primary request: replace only the depicted person in Image 1 with the identical adult woman and identical outfit established by Images 2-8. Use the same very slim naturally athletic silhouette, natural second-size breast proportions, high smooth ponytail, minimal black sports top, and very short fitted high-waisted black sports shorts made from opaque logo-free fabric.
Style/medium: photorealistic natural gym photography; match Image 1 lighting and shadows.
Constraints: preserve Image 1's exact hack-squat lowered end phase. Keep the head direction, gaze, shoulders, hands, spine, torso, pelvis, hips, knees, lower legs, feet, stance width, limb lengths, subject scale, camera, perspective, crop, lighting, shadows, background, and every machine part unchanged. Keep shoulders against the pads and feet at the exact original platform positions. Image 8 must not influence pose, machine, camera, or background. Change only identity, hair, visible skin appearance, body surface styling, and clothing. No jewellery, tattoos, logos, text, or watermark.
Avoid: copying the start pose, changed squat depth, changed foot placement, changed hand position, changed torso angle, changed machine geometry, extra fingers, merged limbs, exaggerated anatomy, glamour retouching, outfit drift, or a different woman.
```

- [ ] **Step 7: Inspect and save the end output**

Apply the same geometry-first rejection rule and one-retry limit as the start phase.
Copy the selected raw output to `generated-end-raw.png` and normalize it without crop
to `generated-end.png` using the verified end source.

- [ ] **Step 8: Build the private review artifacts**

Run:

```bash
./.venv/bin/python scripts/build_identity_pilot_review.py \
  --private-root .private/exercise-media \
  --output-dir review/local-ai-pilot
```

Expected: the comparison and pilot card are created, both visibly marked as not
approved. The production manifest and card remain unchanged.

- [ ] **Step 9: Run the complete pilot boundary check**

Run:

```bash
git status --short
git diff -- app/assets/exercises/manifest.json app/assets/exercises/hack_squat.png
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check scripts tests
./.venv/bin/python -m compileall -q app scripts tests
git diff --check
```

Expected: the full suite passes; no private image appears in Git status; production
files have no diff.

---

### Task 4: Human geometry and identity gate

**Files:**
- Review, ignored: `review/local-ai-pilot/hack_squat-comparison.png`
- Review, ignored: `review/local-ai-pilot/hack_squat-card.png`

**Interfaces:**
- Consumes: Task 3 review artifacts
- Produces: explicit user acceptance, card-specific corrections, or rejection of the ImageGen route

- [ ] **Step 1: Show both review artifacts at full readable resolution**

Render the absolute local paths inline and open the comparison in Codex. State that
the images are private previews and have not changed the bot.

- [ ] **Step 2: Report the controller's geometry inspection**

Report separately:

```text
Identity: same/different/uncertain
Outfit: same/drift
Start geometry: preserved/changed/uncertain
End geometry: preserved/changed/uncertain
Machine and contact points: preserved/changed/uncertain
Production files: unchanged
```

Never describe an uncertain item as passed.

- [ ] **Step 3: Stop for explicit user review**

Ask the user to approve or identify the failed phase and defect. Do not change the
manifest, replace the candidate card, process another exercise, or deploy.

- [ ] **Step 4: Apply the approved outcome only in a later plan**

If the user approves the pilot, write a separate expansion plan for one-exercise-at-
a-time processing and review. If the user rejects the pilot, preserve the original
sources and either perform the single allowed targeted retry or report that a local
mask/pose/depth pipeline or dedicated photoshoot is required.
