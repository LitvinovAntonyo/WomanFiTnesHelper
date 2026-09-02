# Motivation and Safe Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace guilt-based reminders with the approved confident-supportive tone, reset only test workout history, and safely release the integrated v4 bot to the existing VPS.

**Architecture:** Keep the existing persistent reminder scheduler and callback compatibility, change only message content and displayed duration, add a guarded maintenance service for test-history reset, then deploy through a staged copy with database backup and service-level verification.

**Tech Stack:** Python 3.10–3.14, aiogram, APScheduler, SQLAlchemy async, SQLite, systemd, SSH/rsync

**Spec:** `docs/superpowers/specs/2026-09-02-return-to-training-v4-design.md`

## Global Constraints

- Tone is confident and supportive: direct action without guilt, shame, or threats.
- Morning motivation is at 09:00 local time only when it precedes the workout.
- Primary reminder is 120 minutes before the workout.
- Ten-minute reminder is sent only after confirmation.
- Display 50–60 minutes, never 45 minutes.
- Reset workout sessions, set/results/outcomes/feedback, and achievements only.
- Preserve user, settings, whitelist, reminders, conversation history, and secrets.
- Never print or copy the environment file contents.
- Back up SQLite and verify the backup before mutation.
- Restart only `fitness-bot.service`; do not restart the VPS or neighboring services.
- The project directory is not a Git checkout. Do not claim that `main` was updated unless an actual repository and remote are verified during execution.
- The release is blocked until the media plan reports every active card `approved`.

---

### Task 1: Confident-supportive reminder copy and 50–60 minute duration

**Files:**
- Modify: `app/services/scheduler.py`
- Modify: `tests/test_scheduler.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing `morning_motivation_text()` and `pre_workout_motivation_text()`
- Produces: `BANNED_PRESSURE_PHRASES: tuple[str, ...]`
- Preserves: reminder kinds `motivation`, `pre90`, and `pre10` for database compatibility

- [ ] **Step 1: Add tone and duration tests**

```python
def test_pre_workout_copy_is_supportive_and_has_no_pressure_phrases():
    banned = (
        "чувством вины",
        "не слиться",
        "без отговорок",
        "не разрешаю",
        "оправдани",
        "сожаление",
        "ты обещала",
    )
    assert len(PRE_WORKOUT_MOTIVATIONS) >= 10
    assert len(set(PRE_WORKOUT_MOTIVATIONS)) == len(PRE_WORKOUT_MOTIVATIONS)
    assert all(
        fragment not in message.lower()
        for message in PRE_WORKOUT_MOTIVATIONS
        for fragment in banned
    )
    assert all("себ" in message.lower() or "форм" in message.lower() for message in PRE_WORKOUT_MOTIVATIONS)


@pytest.mark.asyncio
async def test_primary_reminder_displays_fifty_to_sixty_minutes(
    app_services, onboarded_user
):
    settings, database, _, _, _, _ = app_services
    fake_bot = FakeBot()
    service = ReminderService(database, settings, fake_bot)
    now = utc_now()
    async with database.session() as session:
        session.add(
            Reminder(
                user_id=onboarded_user.id,
                workout_at=now + timedelta(minutes=PRIMARY_REMINDER_LEAD_MINUTES),
                scheduled_at=now - timedelta(seconds=1),
                kind="pre90",
            )
        )
    async with database.session() as session:
        reminder_id = await session.scalar(
            select(Reminder.id).where(Reminder.user_id == onboarded_user.id)
        )
    await service._deliver(reminder_id)
    assert "50–60 минут" in fake_bot.sent[0][1]
    assert "45 минут" not in fake_bot.sent[0][1]
```

- [ ] **Step 2: Run scheduler tests and confirm the old copy fails**

Run: `python3 -m pytest tests/test_scheduler.py -q`

- [ ] **Step 3: Replace pre-workout messages with the approved tone**

Use this exact tuple:

```python
PRE_WORKOUT_MOTIVATIONS = (
    "Не откладывай то, что делаешь для себя. Сегодняшняя тренировка — ещё один шаг к форме, которую ты возвращаешь.",
    "Ты уже выделила это время для себя. Осталось начать — дальше программа спокойно проведёт тебя по шагам.",
    "Не нужно ждать идеального настроения. Собирайся и сделай сегодняшнюю тренировку в своём темпе.",
    "Сегодня важна не идеальность, а действие. Приходи и выполни тот объём, который подходит тебе сейчас.",
    "Эта тренировка — время для твоей силы и здоровья. Не переноси себя на потом.",
    "Форма возвращается через обычные последовательные тренировки. Сегодня достаточно выполнить следующий шаг.",
    "Ты делаешь это не ради отчёта перед кем-то. Это твоё время и твой вклад в себя.",
    "Начни с простого: форма, вода, дорога в зал. Остальное бот покажет по порядку.",
    "Решение уже принято — сегодня тренировочный день. Действуй спокойно и без спешки.",
    "Даже неидеальная тренировка поддерживает привычку. Приходи и сделай доступный сегодня объём.",
    "Сегодня можно выбрать облегчённый режим, но не обязательно отказываться от тренировки целиком.",
    "Сохрани это время для себя. Через час ты будешь рада, что не отложила сегодняшний шаг.",
)
```

Keep the existing morning messages that already pass the banned-phrase test. Add the same banned-phrase assertion for `MORNING_MOTIVATIONS`.

- [ ] **Step 4: Update duration and button copy**

Change the primary reminder line to:

```python
f"50–60 минут. Сегодня: {template.name.lower()}.\n\n"
"Ты сегодня будешь?"
```

Use buttons `Буду`, `Перенести`, and `Сегодня пропущу`. Keep callback data unchanged.

- [ ] **Step 5: Run scheduler tests**

Run: `python3 -m pytest tests/test_scheduler.py -q`

Expected: timing, uniqueness, reschedule, supportive tone, and duration tests pass.

- [ ] **Step 6: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/services/scheduler.py tests/test_scheduler.py README.md
  git commit -m "fix: use supportive workout reminders"
fi
```

---

### Task 2: Guarded test-history reset

**Files:**
- Create: `app/services/maintenance.py`
- Create: `deploy/reset_test_history.py`
- Create: `tests/test_maintenance.py`

**Interfaces:**
- Produces: `ResetCounts`
- Produces: `reset_test_history(database: Database) -> ResetCounts`
- Produces: CLI confirmation token `RESET-TEST-HISTORY`

- [ ] **Step 1: Write the preservation test**

```python
@pytest.mark.asyncio
async def test_reset_history_preserves_profile_settings_and_reminders(
    app_services, onboarded_user
):
    _, database, _, workouts, _, reminders = app_services
    await complete_workout(workouts, 10001)
    await reminders.ensure_user_reminders(onboarded_user.id)
    counts = await reset_test_history(database)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(UserSettings)) == 1
        assert await session.scalar(select(func.count()).select_from(Reminder)) > 0
        assert await session.scalar(select(func.count()).select_from(WorkoutSession)) == 0
        assert await session.scalar(select(func.count()).select_from(ExerciseResult)) == 0
        assert await session.scalar(select(func.count()).select_from(ExerciseSetResult)) == 0
        assert await session.scalar(select(func.count()).select_from(Achievement)) == 0
    assert counts.sessions == 1
```

- [ ] **Step 2: Run the test and confirm the service is missing**

Run: `python3 -m pytest tests/test_maintenance.py -q`

- [ ] **Step 3: Implement the reset service in one transaction**

```python
@dataclass(frozen=True, slots=True)
class ResetCounts:
    sessions: int
    exercise_results: int
    set_results: int
    outcomes: int
    session_feedback: int
    achievements: int
```

Count each table first. Delete all `WorkoutSession` rows and rely on verified SQLite foreign-key cascades for exercise results, set results, outcomes, and feedback. Delete all `Achievement` rows explicitly. Flush, recount all six mutable tables as zero, and raise `RuntimeError` if any remain. Never delete from `users`, `settings`, `reminders`, `conversation_history`, or `telegram_media_cache`.

- [ ] **Step 4: Implement a guarded CLI**

`deploy/reset_test_history.py` accepts exactly:

```text
--confirm RESET-TEST-HISTORY
```

Without that value, exit 2 before opening the database. Load settings through `app.config.load_settings()`, call the service, and print counts only; never print the database URL or environment values.

- [ ] **Step 5: Run maintenance tests**

Run: `python3 -m pytest tests/test_maintenance.py -q`

Expected: history disappears and profile/schedule/reminders remain.

- [ ] **Step 6: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/services/maintenance.py deploy/reset_test_history.py tests/test_maintenance.py
  git commit -m "feat: add guarded test history reset"
fi
```

---

### Task 3: Integrated local release gate

**Files:**
- Modify: `README.md`
- Modify: `docs/EXERCISE_IMAGE_STYLE.md`
- Read: all implementation files and tests from the core and media plans

**Interfaces:**
- Consumes: completed core plan
- Consumes: completed media plan with all cards approved
- Produces: a local artifact safe to stage

- [ ] **Step 1: Verify the media approval gate**

Run:

```bash
python3 scripts/build_exercise_cards.py --validate-sources
python3 scripts/build_exercise_cards.py --require-all-approved
```

Expected: both exit 0. Stop the release if `glute_kickback` or any other active card is candidate/text-only.

- [ ] **Step 2: Run the full code gate**

```bash
python3 -m pytest -q
python3 -m ruff check app tests scripts deploy/reset_test_history.py
python3 -m compileall -q app deploy/reset_test_history.py
```

Expected: every command exits 0 with a final status.

- [ ] **Step 3: Run an isolated migration rehearsal**

Copy a sanitized local SQLite fixture to a temporary directory, configure `DATABASE_URL` to the copy, run `Database.initialize()`, and assert:

```sql
PRAGMA integrity_check;        -- ok
PRAGMA user_version;           -- 3
```

Confirm `exercise_set_results` and `workout_session_feedback` exist and old v3 templates remain inactive rather than deleted.

- [ ] **Step 4: Scan for stale behavior and secrets**

```bash
rg -n "45 минут|чувством вины|не слиться|без отговорок|одна и та же героиня|татуиров|return_.*_v3" app README.md docs tests
rg -n "TELEGRAM_BOT_TOKEN=.+|LLM_API_KEY=.+" . --glob '!*.example' --glob '!docs/superpowers/**'
```

Expected: no active stale copy and no populated secret assignments. Dated historical deployment notes may mention v3 but must not describe it as current.

- [ ] **Step 5: Record local evidence**

Write command, timestamp, exit code, test count, and artifact checksums to `review/v4-local-verification.md`. Do not write token values, Telegram IDs, database contents, hostnames, or IP addresses.

- [ ] **Step 6: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app tests scripts deploy README.md docs review
  git commit -m "chore: prepare workout v4 release"
fi
```

---

### Task 4: Read-only VPS preflight and verified SQLite backup

**Files:**
- Read: `deploy/audit_vps.sh`
- Read: `deploy/snapshot_services.sh`
- Read: `deploy/compare_services.sh`
- Create remotely: timestamped backup under `/var/backups/fitness-bot/`

**Interfaces:**
- Consumes: existing SSH access supplied outside the repository
- Produces: service baseline, database backup, and pre-deploy counts

- [ ] **Step 1: Resolve the target without embedding credentials**

Set local environment variables `FITNESS_VPS` and `FITNESS_SSH_KEY` from the existing authorized SSH configuration. Verify only:

```bash
ssh -i "$FITNESS_SSH_KEY" "$FITNESS_VPS" \
  'systemctl show fitness-bot.service -p WorkingDirectory -p ExecStart -p MainPID -p NRestarts --no-pager'
```

Expected working directory: `/opt/fitness-bot`. Stop if it differs.

- [ ] **Step 2: Capture baseline without reading secrets**

Run the existing audit and service-snapshot scripts remotely. Record `is-active`, `NRestarts`, `MemoryCurrent`, neighboring running services, and `PRAGMA integrity_check`. Do not `cat`, `grep`, or source the environment file in a command whose output returns to chat.

- [ ] **Step 3: Back up SQLite with Python's backup API**

On the VPS, set `backup_dir="/var/backups/fitness-bot/$(date -u +%Y%m%dT%H%M%SZ)-v4"`, create it with mode `0700`, and write `fitness_bot.sqlite3` inside it. Use Python `sqlite3.Connection.backup()` from `/var/lib/fitness-bot/fitness_bot.sqlite3` to that explicit path, then open the backup read-only and print only `PRAGMA integrity_check`, `PRAGMA user_version`, and table row counts.

- [ ] **Step 4: Verify the backup before any write**

Expected: source and backup both return `ok`; backup file is non-empty; user/settings/reminder/session counts match the source. Stop if any check differs.

---

### Task 5: Stage, install, migrate, and restart only the bot

**Files:**
- Upload: `app/`, `deploy/`, `requirements.txt`, `pyproject.toml`
- Upload for evidence only: `review/v4-local-verification.md`
- Do not upload: `.env`, `media_sources/`, source photos, local databases, `work/`, or SSH keys

**Interfaces:**
- Produces: migrated `/opt/fitness-bot` and one restarted systemd unit

- [ ] **Step 1: Build a clean staging directory**

Use `mktemp -d` locally. Copy only runtime files and approved finished cards. Confirm the staging tree contains no `.env`, SQLite file, private key, source photograph, or `__pycache__`.

- [ ] **Step 2: Upload to a timestamped remote staging path**

Use `rsync -a --delete` to `/tmp/fitness-bot-v4-release/`. Run remote `python3 -m compileall -q app` from staging before touching `/opt/fitness-bot`.

- [ ] **Step 3: Install without replacing the existing environment file**

Run the existing `deploy/install.sh` against the staging directory without an env-file argument. Verify it detects the existing `/etc/fitness-bot/fitness-bot.env`; do not create or print another environment file.

- [ ] **Step 4: Rehearse initialization against a temporary database**

As user `fitnessbot`, set only a temporary `DATABASE_URL` in the subprocess environment, import production code, initialize, seed templates, and verify user version 3 plus the exact v4 template order. Delete the temporary database after success.

- [ ] **Step 5: Restart only `fitness-bot.service`**

```bash
systemctl restart fitness-bot.service
systemctl is-active fitness-bot.service
systemctl show fitness-bot.service -p MainPID -p NRestarts -p MemoryCurrent --no-pager
```

Expected: `active`, one new MainPID, and no restart loop. Do not reboot the VPS.

- [ ] **Step 6: Verify the production migration**

Run `PRAGMA integrity_check`, `PRAGMA user_version`, active-template codes, and new table existence without returning personal data. Expected: `ok`, version 3, exactly the three v4 active templates.

---

### Task 6: One-time reset of test history

**Files:**
- Execute remotely: `/tmp/fitness-bot-v4-release/deploy/reset_test_history.py`

**Interfaces:**
- Consumes: backup from Task 4
- Produces: zero test sessions with preserved profile/settings/reminders

- [ ] **Step 1: Capture pre-reset counts**

Print only aggregate counts for users, settings, reminders, sessions, exercise results, set results, outcomes, feedback, and achievements.

- [ ] **Step 2: Run the guarded reset under the service environment**

Invoke the script with `--confirm RESET-TEST-HISTORY` using the existing environment file in a shell whose output does not echo variables. Stop the service only for the short reset transaction, then immediately start it again.

- [ ] **Step 3: Verify preservation and integrity**

Expected after reset:

- users count unchanged;
- settings count unchanged;
- reminders count unchanged;
- sessions, exercise results, set results, outcomes, feedback, and achievements are zero;
- `PRAGMA integrity_check` is `ok`;
- service is `active` with no restart loop.

- [ ] **Step 4: Keep the backup**

Do not delete the timestamped backup. Report its remote directory and that restoring it would also restore the deleted test history.

---

### Task 7: Runtime and Telegram acceptance

**Files:**
- Read remotely: systemd status and journal
- Update after verification: `DEPLOYMENT_STATUS.md`

**Interfaces:**
- Produces: evidence that the deployed bot is ready for the user's Telegram check

- [ ] **Step 1: Verify process and resource behavior**

Run `systemctl is-enabled`, `systemctl is-active`, `NRestarts`, `MemoryCurrent`, and the last ten minutes of warning/error journal lines. Because prior memory use was close to `MemoryHigh=192M`, wait for two scheduler ticks and re-read memory before claiming stability.

- [ ] **Step 2: Compare neighboring services**

Run `deploy/compare_services.sh` against the Task 4 baseline. Expected: no previously running service is missing. Do not restart neighbors to make the comparison pass.

- [ ] **Step 3: Verify bot identity and scheduler without exposing tokens**

Run the bot's existing health/status path or `getMe` through production code and print only the bot username, database health boolean, scheduler running state, and next aggregate reminder time. Never print token, Telegram ID, names, or message content.

- [ ] **Step 4: Ask the user to perform the visible Telegram smoke**

The user verifies:

1. `Начать тренировку` shows v4 and 50–60 minutes.
2. Cardio offers three choices.
3. Strength card shows real approved photos.
4. A set accepts `вес повторы` and starts the exercise-specific timer.
5. `Боль или дискомфорт` advances safely.
6. `Облегчённая тренировка` reduces untouched exercises to two sets.
7. Final feedback is saved.
8. `Сбросить текущий день` works during testing.

- [ ] **Step 5: Update the deployment record with actual evidence only**

Append date, backup directory, deployed template codes, schema version, exact test/ruff results, aggregate reset counts, service state, `NRestarts`, integrity result, and Telegram checks the user actually completed. Do not carry forward old test counts as if they were current.

---

### Task 8: Git/main reconciliation without inventing repository state

**Files:**
- Read: parent directories and configured project metadata
- Modify only if a real repository is found: the verified project checkout

**Interfaces:**
- Produces: either a pushed `main` commit or an explicit unresolved repository-location note

- [ ] **Step 1: Recheck Git context**

Run `git rev-parse --show-toplevel` in the project and inspect saved Codex projects. Do not initialize a new repository merely to satisfy the word `main`.

- [ ] **Step 2: If a real fitness-bot repository is found, verify identity**

Require matching project files, a clean understanding of existing changes, and a configured remote. Compare hashes with the implemented output before copying. Preserve unrelated changes.

- [ ] **Step 3: Commit and push only after verification**

Run the full local release gate inside the actual checkout, commit the exact v4 changes, inspect the diff, then push its existing `main` branch. Do not force-push.

- [ ] **Step 4: If no repository is found, report the boundary**

State that VPS deployment and the local deliverable are complete but GitHub `main` was not updated because the current project has no `.git` or verified remote. Ask for the repository location only at that point; do not guess or publish to an unrelated repository.
