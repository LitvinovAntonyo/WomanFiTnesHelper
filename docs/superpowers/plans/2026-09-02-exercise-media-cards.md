# Exercise Media Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generated exercise art with manually reviewed cards made from real, openly licensed start/end photographs and guarantee that Telegram never serves a stale card.

**Architecture:** Keep source photographs and their licenses outside the runtime package, generate deterministic 1254×1254 PNG cards offline, and deploy only the finished cards plus a runtime manifest. A dedicated asset module resolves card paths and checksum-versioned Telegram cache keys.

**Tech Stack:** Python 3.10–3.14, Pillow for offline rendering, JSON manifest, pytest, aiogram file upload

**Spec:** `docs/superpowers/specs/2026-09-02-return-to-training-v4-design.md`

## Global Constraints

- Use real photographs only; no image generation or visual likeness synthesis.
- Every source must be public domain or have a license that permits copying and derivative cards.
- Record source URL, author, license, phase assignment, and review status.
- Use `Исходное положение` / `Конечное положение` for strength exercises.
- Use `Настройка` / `Рабочее положение` for cardio.
- Never substitute a floor donkey kick or cable kickback for the dedicated glute kickback machine.
- The user reviews one contact sheet before any card is marked `approved` or deployed.
- If an exact licensed pair is unavailable, keep a text-only fallback and block the final release rather than using an incorrect or unlicensed image.
- The current project directory has no `.git`; conditional commit steps run only in a real Git checkout.
- Do not modify VPS state in this plan.

---

### Task 1: Runtime manifest contract and validation

**Files:**
- Create: `app/exercise_assets.py`
- Create: `app/assets/exercises/manifest.json`
- Create: `tests/test_exercise_assets.py`
- Modify: `app/exercise_library.py`

**Interfaces:**
- Produces: `ExerciseAsset`
- Produces: `asset_for(code: str) -> ExerciseAsset | None`
- Produces: `card_path_for(code: str) -> Path | None`
- Produces: `asset_key_for(code: str) -> str`
- Produces: `approved_asset_codes() -> set[str]`

- [ ] **Step 1: Write manifest parsing tests**

```python
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
                "source_ids": ["free-exercise-db:Leg_Press:1", "free-exercise-db:Leg_Press:0"],
            }
        },
    )
    monkeypatch.setattr(exercise_assets, "ASSET_DIR", tmp_path)
    monkeypatch.setattr(exercise_assets, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert card_path_for("leg_press") == card
    assert asset_key_for("leg_press").startswith("leg_press:")


def test_candidate_or_missing_card_uses_text_fallback(tmp_path, monkeypatch):
    write_manifest(
        tmp_path,
        {"glute_kickback": {"card": None, "status": "text_only", "sha256": None, "source_ids": []}},
    )
    monkeypatch.setattr(exercise_assets, "ASSET_DIR", tmp_path)
    monkeypatch.setattr(exercise_assets, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert card_path_for("glute_kickback") is None
    assert asset_key_for("glute_kickback") == "glute_kickback:text-only"
```

- [ ] **Step 2: Add failing validation tests**

```python
def test_approved_manifest_rejects_checksum_mismatch(tmp_path, monkeypatch):
    card = tmp_path / "row.png"
    card.write_bytes(b"changed")
    write_manifest(
        tmp_path,
        {"seated_row": {"card": "row.png", "status": "approved", "sha256": "0" * 64, "source_ids": ["a", "b"]}},
    )
    monkeypatch.setattr(exercise_assets, "ASSET_DIR", tmp_path)
    monkeypatch.setattr(exercise_assets, "MANIFEST_PATH", tmp_path / "manifest.json")
    with pytest.raises(ValueError, match="checksum"):
        asset_for("seated_row")
```

- [ ] **Step 3: Run tests and confirm imports fail**

Run: `python3 -m pytest tests/test_exercise_assets.py -q`

- [ ] **Step 4: Implement the immutable runtime type**

```python
@dataclass(frozen=True, slots=True)
class ExerciseAsset:
    code: str
    card: Path | None
    status: Literal["candidate", "approved", "text_only"]
    sha256: str | None
    source_ids: tuple[str, ...]
```

Load JSON with `json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))`. For `approved`, require an existing card, exactly two source IDs, and a matching SHA-256. `card_path_for` returns a path only for `approved`; candidate and text-only entries return `None`.

- [ ] **Step 5: Create the initial manifest shell**

The top-level form is:

```json
{
  "schema_version": 1,
  "licenses": {},
  "sources": {},
  "exercises": {}
}
```

Add entries for all v4 exercises, three cardio options, and active alternatives. Initially mark them `candidate`; mark `glute_kickback` `text_only` until Task 4 finds an exact licensed pair.

- [ ] **Step 6: Route image lookup through the new module**

Remove `image_path_for` from `app/exercise_library.py`; technique copy stays there. Import the new asset functions only in handlers and media-focused tests to avoid a circular dependency.

- [ ] **Step 7: Run tests**

Run: `python3 -m pytest tests/test_exercise_assets.py tests/test_exercise_library.py -q`

Expected: manifest and fallback behavior pass.

- [ ] **Step 8: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/exercise_assets.py app/assets/exercises/manifest.json app/exercise_library.py tests/test_exercise_assets.py tests/test_exercise_library.py
  git commit -m "feat: add licensed exercise asset manifest"
fi
```

---

### Task 2: Deterministic card renderer and contact-sheet generator

**Files:**
- Create: `scripts/build_exercise_cards.py`
- Create: `scripts/build_exercise_contact_sheet.py`
- Create: `tests/test_card_renderer.py`
- Create: `media_sources/fonts/OFL.txt`
- Create: `media_sources/fonts/NotoSans.ttf`
- Modify: `requirements-dev.txt`

**Interfaces:**
- Produces: `render_card(spec: CardSpec, output: Path) -> None`
- Produces: `render_contact_sheet(cards: list[Path], output: Path) -> None`
- Produces: 1254×1254 RGB PNG files

- [ ] **Step 1: Add the offline imaging dependency**

Append `Pillow>=11.0,<13.0` to `requirements-dev.txt`. Do not add Pillow to `requirements.txt`; card rendering never runs on the VPS.

- [ ] **Step 2: Add a redistributable Cyrillic font**

Download `Noto Sans` from the Google Fonts repository and save the corresponding OFL 1.1 license. Record both upstream URLs and SHA-256 values in `media_sources/fonts/OFL.txt`. The renderer must use only `media_sources/fonts/NotoSans.ttf`, never a host-specific system font.

- [ ] **Step 3: Write deterministic renderer tests**

```python
def test_render_card_has_fixed_size_and_is_deterministic(tmp_path):
    start = solid_image(tmp_path / "start.jpg", (220, 180), "red")
    end = solid_image(tmp_path / "end.jpg", (180, 220), "blue")
    spec = CardSpec(
        title="Жим ногами",
        start_image=start,
        end_image=end,
        start_label="Исходное положение",
        end_label="Конечное положение",
        start_hint="Колени согнуты, таз на спинке",
        end_hint="Выжми платформу без блокировки коленей",
        attribution="free-exercise-db · Unlicense",
    )
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    render_card(spec, first)
    render_card(spec, second)
    with Image.open(first) as image:
        assert image.size == (1254, 1254)
        assert image.mode == "RGB"
    assert sha256(first) == sha256(second)
```

- [ ] **Step 4: Run the renderer test and confirm it fails**

Run: `python3 -m pytest tests/test_card_renderer.py -q`

- [ ] **Step 5: Implement the exact visual grid**

Use a 1254×1254 RGB canvas, background `#F4F6F6`, outer margin 48 px, 42 px gap, two 558 px panels, title at y=35, panel labels at y=100, images from y=170 to y=865, short hints from y=900, and attribution at y=1210. Use `ImageOps.fit` with centered crop; never stretch a source photograph. Draw a 2 px `#D7DEDE` border and a centered `#239B95` arrow between panels.

Wrap Russian hints to at most two lines per panel and fail with `ValueError` if text still exceeds the allocated box. Strip all EXIF metadata by constructing a new RGB canvas and saving with `optimize=True`.

- [ ] **Step 6: Implement contact-sheet output**

`build_exercise_contact_sheet.py` reads all candidate cards, makes 300 px thumbnails in a three-column grid, prints exercise code and status under each, and saves `review/exercise-cards-contact-sheet.png`.

- [ ] **Step 7: Run renderer tests**

Run: `python3 -m pytest tests/test_card_renderer.py -q`

Expected: deterministic image and contact-sheet tests pass.

- [ ] **Step 8: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add scripts tests/test_card_renderer.py media_sources/fonts requirements-dev.txt
  git commit -m "feat: render deterministic exercise cards"
fi
```

---

### Task 3: Import the verified public-domain base photographs

**Files:**
- Create: `media_sources/exercises/<code>/start.jpg`
- Create: `media_sources/exercises/<code>/end.jpg`
- Modify: `app/assets/exercises/manifest.json`
- Create or replace: `app/assets/exercises/<code>.png`
- Create: `media_sources/LICENSES.md`

**Interfaces:**
- Consumes: `render_card`
- Produces: candidate cards and complete source metadata for all available v4 exercises

- [ ] **Step 1: Pin the source repository revision**

From the existing checkout `../../work/free-exercise-db`, record `git rev-parse HEAD`, repository URL `https://github.com/yuhonas/free-exercise-db`, and the Unlicense text from `LICENSE.md` in `media_sources/LICENSES.md`. Do not claim the license until both the repository and license file are present at the pinned revision.

- [ ] **Step 2: Copy only the required source pairs**

Use this exact phase map:

| Bot code | Upstream directory | Start/setup | End/working |
|---|---|---|---|
| `cardio_treadmill` | `Walking_Treadmill` | `0.jpg` | `1.jpg` |
| `cardio_elliptical` | `Elliptical_Trainer` | `0.jpg` | `1.jpg` |
| `cardio_bike` | `Bicycling_Stationary` | `0.jpg` | `1.jpg` |
| `seated_leg_curl` | `Seated_Leg_Curl` | `0.jpg` | `1.jpg` |
| `hip_abduction` | `Thigh_Abductor` | `0.jpg` | `1.jpg` |
| `lat_pulldown` | `Wide-Grip_Lat_Pulldown` | `0.jpg` | `1.jpg` |
| `chest_press` | `Leverage_Chest_Press` | `0.jpg` | `1.jpg` |
| `hack_squat` | `Hack_Squat` | `0.jpg` | `1.jpg` |
| `leg_extension` | `Leg_Extensions` | `0.jpg` | `1.jpg` |
| `hip_adduction` | `Thigh_Adductor` | `0.jpg` | `1.jpg` |
| `seated_row` | `Seated_Cable_Rows` | `0.jpg` | `1.jpg` |
| `leg_press` | `Leg_Press` | `1.jpg` | `0.jpg` |
| `machine_shoulder_press` | `Leverage_Shoulder_Press` | `0.jpg` | `1.jpg` |
| `pec_deck` | `Butterfly` | `1.jpg` | `0.jpg` |

Copy each phase to the bot-code directory using stable names `start.jpg` and `end.jpg`. The reversed mappings for `leg_press` and `pec_deck` are intentional and must have regression tests.

- [ ] **Step 3: Fill exact source records**

Build each source record from verified command output rather than hand-written revision placeholders:

```python
revision = subprocess.run(
    ["git", "-C", str(source_repo), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
if len(revision) != 40:
    raise ValueError("free-exercise-db revision must be a full commit hash")
relative_source = "exercises/Leg_Press/1.jpg"
source_file = source_repo / relative_source
checksum = hashlib.sha256(source_file.read_bytes()).hexdigest()
record = {
    "provider": "free-exercise-db",
    "repository_revision": revision,
    "source_url": f"https://raw.githubusercontent.com/yuhonas/free-exercise-db/{revision}/{relative_source}",
    "author": "free-exercise-db contributors",
    "license": "Unlicense",
    "license_url": f"https://github.com/yuhonas/free-exercise-db/blob/{revision}/LICENSE.md",
    "sha256": checksum,
    "role": "start",
}
```

Use the same construction for every row in the phase map and reject an empty source file or checksum.

- [ ] **Step 4: Render all base candidate cards**

Run: `python3 scripts/build_exercise_cards.py --status candidate`

Expected: one 1254×1254 card per imported exercise and updated card checksums in the manifest. `glute_kickback` remains text-only.

- [ ] **Step 5: Validate source integrity and phase mapping**

Add tests that compare every copied source SHA-256 to the manifest, ensure each strength card has `start` and `end`, ensure cardio has `setup` and `working`, and assert the two intentional reversed mappings.

- [ ] **Step 6: Run media tests**

Run: `python3 -m pytest tests/test_exercise_assets.py tests/test_card_renderer.py -q`

Expected: all imported candidates validate; the release completeness test still fails only for `glute_kickback` and unapproved statuses.

- [ ] **Step 7: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add media_sources app/assets/exercises app/assets/exercises/manifest.json tests
  git commit -m "feat: add public-domain exercise photo sources"
fi
```

---

### Task 4: Licensed dedicated glute-kickback pair

**Files:**
- Create: `media_sources/exercises/glute_kickback/start.jpg`
- Create: `media_sources/exercises/glute_kickback/end.jpg`
- Modify: `media_sources/LICENSES.md`
- Modify: `app/assets/exercises/manifest.json`
- Create or replace: `app/assets/exercises/glute_kickback.png`

**Interfaces:**
- Produces: an exact machine-matched candidate or an explicit release blocker

- [ ] **Step 1: Search only sources that expose a usable license**

Check Wikimedia Commons first, followed by manufacturer media explicitly licensed for reuse. Reject search-result thumbnails, Pinterest, stock-photo previews, ordinary blogs, YouTube thumbnails, and pages without a license permitting derivative use.

- [ ] **Step 2: Apply the semantic acceptance checklist**

Both phases must show the same dedicated standing or prone glute-kickback machine, the same person, the same camera angle, and the same equipment setup. The start must show hip flexion/neutral leg position; the end must show controlled hip extension. Reject floor donkey kicks, cable ankle kickbacks, and generic hip-abduction machines.

- [ ] **Step 3: Record one of two exact outcomes**

If a valid pair exists, save both files and record source URLs, author, license, license URL, retrieval date, checksums, and roles, then render the candidate card.

If no valid pair exists, keep:

```json
{
  "card": null,
  "status": "text_only",
  "sha256": null,
  "source_ids": []
}
```

and write `BLOCKED: no exact reusable glute-kickback photo pair found` to `review/media-gate.txt`. Do not substitute another movement.

- [ ] **Step 4: Run the license and semantics gate**

Run: `python3 scripts/build_exercise_cards.py --validate-sources`

Expected: success only when metadata and checksums are complete. A text-only result is safe for local behavior but blocks final production release because the user requested photographs for every exercise.

- [ ] **Step 5: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add media_sources app/assets/exercises/manifest.json app/assets/exercises/glute_kickback.png review/media-gate.txt
  git commit -m "feat: add licensed glute machine technique card"
fi
```

---

### Task 5: Human visual review and approval gate

**Files:**
- Create: `review/exercise-cards-contact-sheet.png`
- Create: `review/exercise-cards-review.md`
- Modify: `app/assets/exercises/manifest.json`
- Replace as needed: `app/assets/exercises/*.png`

**Interfaces:**
- Consumes: all candidate cards
- Produces: `approved` manifest statuses only after explicit user review

- [ ] **Step 1: Build the review sheet**

Run:

```bash
python3 scripts/build_exercise_contact_sheet.py \
  --manifest app/assets/exercises/manifest.json \
  --output review/exercise-cards-contact-sheet.png
```

Expected: all cardio, v4 exercises, and active alternatives appear exactly once with readable codes.

- [ ] **Step 2: Create the review checklist**

For every code, include checkboxes for source license, correct start phase, correct end phase, unchanged machine setup, readable Russian text, and no misleading crop. The glute-kickback row additionally states `dedicated machine, not floor or cable`.

- [ ] **Step 3: Show the contact sheet to the user and stop for review**

Do not change any `candidate` status to `approved` before the user explicitly accepts the sheet or gives card-specific corrections.

- [ ] **Step 4: Apply requested corrections and rebuild**

Change only the rejected card source mapping, crop, or two-line hint, regenerate it, update the checksum, and rebuild the contact sheet. Preserve accepted cards byte-for-byte.

- [ ] **Step 5: Mark accepted cards approved**

Set `status` to `approved`, write the review date to the manifest, and record `approved_by: user`. Do not store a personal name or Telegram ID.

- [ ] **Step 6: Run the complete approval gate**

Run: `python3 scripts/build_exercise_cards.py --require-all-approved`

Expected: exit 0 only when every v4/cardio/alternative code has an approved, checksum-valid card.

- [ ] **Step 7: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add review app/assets/exercises app/assets/exercises/manifest.json
  git commit -m "feat: approve exercise technique cards"
fi
```

---

### Task 6: Checksum-versioned Telegram delivery

**Files:**
- Modify: `app/handlers/workout.py`
- Modify: `tests/test_handlers.py`
- Modify: `tests/test_exercise_assets.py`

**Interfaces:**
- Consumes: `card_path_for(code)` and `asset_key_for(code)`
- Consumes: existing `media_file_id(asset_key)` and `remember_media_file_id(asset_key, file_id)`
- Produces: text fallback on file/read/send failure

- [ ] **Step 1: Add delivery tests**

```python
def test_asset_key_changes_when_card_checksum_changes(tmp_path, monkeypatch):
    first = approved_manifest(tmp_path, "leg_press", b"first")
    monkeypatch_manifest(first)
    key1 = asset_key_for("leg_press")
    second = approved_manifest(tmp_path, "leg_press", b"second")
    monkeypatch_manifest(second)
    key2 = asset_key_for("leg_press")
    assert key1 != key2


@pytest.mark.asyncio
async def test_photo_send_failure_falls_back_to_text(
    app_services, onboarded_user
):
    class PhotoFailingSession(RecordingSession):
        async def make_request(self, bot, method, timeout=None):
            if isinstance(method, SendPhoto):
                raise TelegramNetworkError(method=method, message="synthetic photo failure")
            return await super().make_request(bot, method, timeout)

    settings, database, users, workouts, progress, _ = app_services
    session = PhotoFailingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(
        settings=settings,
        database=database,
        bot=bot,
        users=users,
        workouts=workouts,
        progress=progress,
        reminders=reminders,
        llm=llm,
    )
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))
    await dispatcher.feed_update(bot, user_message(50, "🏋️ Начать тренировку"))
    workout = await workouts.active_or_new(10001)
    await dispatcher.feed_update(
        bot,
        callback_update(51, f"cardio:select:{workout.id}:cardio_treadmill"),
    )
    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("Исходное положение" in text for text in sent_texts)
    await llm.close()
    await bot.session.close()
```

- [ ] **Step 2: Run handler tests and confirm old code-key behavior fails**

Run: `python3 -m pytest tests/test_handlers.py tests/test_exercise_assets.py -q`

- [ ] **Step 3: Use the checksum key in `send_current_step`**

Resolve `card_path = card_path_for(code)` and `asset_key = asset_key_for(code)`. Query and save Telegram `file_id` using the full key. Wrap local file read and `answer_photo` in a narrow exception handler that logs the exception type without file contents or tokens, sends the caption as text, and always continues to the technique message.

- [ ] **Step 4: Run delivery tests**

Run: `python3 -m pytest tests/test_handlers.py tests/test_exercise_assets.py -q`

Expected: a changed card uses a new cache key; photo failure still sends technique and buttons.

- [ ] **Step 5: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/handlers/workout.py tests/test_handlers.py tests/test_exercise_assets.py
  git commit -m "fix: version Telegram exercise media cache"
fi
```

---

### Task 7: Media regression verification

**Files:**
- Modify: `README.md`
- Modify: `docs/EXERCISE_IMAGE_STYLE.md`
- Test: `tests/test_exercise_assets.py`
- Test: `tests/test_card_renderer.py`

**Interfaces:**
- Produces: a production-gated, reproducible media library

- [ ] **Step 1: Document the reproducible build**

Add exact install, render, contact-sheet, approval-gate, and checksum-validation commands. State that only finished `app/assets/exercises/*.png` files are needed at runtime.

- [ ] **Step 2: Run the media gate**

```bash
python3 scripts/build_exercise_cards.py --validate-sources
python3 scripts/build_exercise_cards.py --require-all-approved
python3 -m pytest tests/test_exercise_assets.py tests/test_card_renderer.py tests/test_handlers.py -q
python3 -m ruff check app tests scripts
```

Expected: all commands exit 0 and no active exercise is text-only, candidate, checksum-mismatched, or unlicensed.

- [ ] **Step 3: Confirm no generated imagery is active**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("app/assets/exercises/manifest.json").read_text())
assert all(item["status"] == "approved" for item in manifest["exercises"].values())
assert all(item.get("generator") is None for item in manifest["exercises"].values())
print("active exercise media: real licensed cards only")
PY
```

- [ ] **Step 4: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add README.md docs/EXERCISE_IMAGE_STYLE.md app media_sources scripts tests review
  git commit -m "docs: verify exercise media provenance"
fi
```
