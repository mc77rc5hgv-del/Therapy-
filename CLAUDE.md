# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## What this is

A Telegram bot (`telegram_bot.py`, aiogram 3.7.0, Python 3.12) that helps students at ВМедА
(Military Medical Academy) prepare for the **Терапия** (Internal Medicine / Therapy) exam.
Architecture is deliberately modeled on the sister project `vmeda-biology-bot` (multi-subject
exam-prep bot for Biology/Physics/Chemistry/Anatomy/Histology/...): a JSON content bank loaded
once at import via `repositories/knowledge.py`, subject/section logic split into `Router`s under
`handlers/`, `dp.include_router()` at the bottom of `telegram_bot.py`, and a module-level `stats`
dict persisted to disk the same way. Unlike `vmeda-biology-bot`, this bot has exactly **one**
subject (Терапия itself), so there is no multi-subject main menu — `handlers/therapy.py`'s own
section list doubles as the bot's home screen.

**Current state: architecture skeleton, not yet populated with real exam content.** The course
plan (`therapy.json`) was built directly from a course-outline spreadsheet the user provided
(01.09.2026) — section/topic names and the *status* of each material category (theory, tests,
comparison tables, boundary control, pharmacology overview, exam questions, manipulations) are
real and taken verbatim from that plan, but the actual theory text / test questions / tables
themselves have not been written yet, because no source material (lecture slides, .ppt files,
department handouts) has been supplied for them. Every content block that doesn't have real
material yet renders an honest "not added yet" status screen (see `handlers/therapy.py`'s
`_status_screen()`) instead of inventing medical content — the same "honest gap, no invented
content" principle `vmeda-biology-bot` uses for Operative Surgery v1 / Physiology's
`control_questions`. **Never fabricate diagnostic criteria, drug doses, treatment algorithms, or
any other clinical fact to fill these placeholders** — when real source material arrives, add it
to `therapy.json`'s `material`/`questions`/`table` fields; the rendering code already knows how to
show it once those fields are non-empty, no handler changes needed.

## Commands

Install deps: `pip install -r requirements.txt` (`aiogram==3.7.0`).

Syntax-check after any edit:
```
python3 -m py_compile telegram_bot.py handlers/therapy.py repositories/knowledge.py
```

Run the bot locally (needs a real `BOT_TOKEN`):
```
BOT_TOKEN=<token> STATS_DIR=/some/writable/dir ADMIN_IDS=<your_telegram_id> python3 telegram_bot.py
```
`ADMIN_IDS` is a comma-separated list of Telegram numeric user IDs — unlike `vmeda-biology-bot`,
there is no hardcoded admin set in source (this is a different bot/team; never hardcode real
person IDs here without being told them explicitly).

### Tests

Live in `tests/`, same pattern as `vmeda-biology-bot`: standalone async scripts (no pytest) that
import `telegram_bot` via `from _bootstrap import tb` and drive real handler functions with
hand-rolled `FakeUser`/`FakeMsg`/`FakeCB` mocks. Run everything:
```
python3 tests/run_all.py
```
Run a single file:
```
python3 tests/test_therapy.py
```

### Deploy

Railway auto-deploys from `main` (see `railway.json`, `startCommand: python3 telegram_bot.py`).
Standard flow after tests pass:
```
rm -f stats.json stats.json.tmp   # never commit real runtime stats
git add <files> && git commit -m "..."
git push -u origin <dev-branch>
```
No `main`-merge automation has been set up yet for this repo — merge into `main` manually via a
pull request (or ask the user how they want releases handled) rather than assuming the exact
`vmeda-biology-bot` fast-forward-merge recipe applies here without confirming.

## Architecture

### Content data model (`therapy.json`)

Top-level: `meta` (title/institution/scope_note/provenance_note/open_sections_note — documents
that this is a draft plan, not a finished course) and `sections[]`.

Each **section** is `{id, order, title, short_title, topics[], open_note,
anatomy_overview, comparison_table, boundary_control, pharma_overview, exam_questions,
manipulations}` — the last six are the section-level material categories from the course plan
(the "Обзор Анатомия"/"Сравнительная таблица"/"Рубежный контроль"/"Обзор Фарма"/"Экз. вопросы"/
"Манипуляции" columns of the source spreadsheet apply once per section, not per topic — they were
merged cells in the original plan). Each of those six is `{status, plan_note, material[]}` (or
`questions[]` for `boundary_control`/`exam_questions`, or `table` — a single value, not a list —
for `comparison_table`). `status` is one of the values in `handlers/therapy.py`'s `STATUS_LABELS`
dict (`planned`/`not_started`/`pending`/`in_progress`/`source_available`/
`multiple_variants_unverified`/`unclear_needs_answers`/`practice_only`/`draft_needs_review`) —
add a new key to both `STATUS_LABELS` and any `therapy.json` entry that needs it together, or the
label falls back to a generic `ℹ️ <status>` rendering.

Each **topic** (inside a section's `topics[]`) is `{id, order, title, full_title, theory, tests}`
— `theory`/`tests` are `{status, plan_note, material[]}` / `{status, plan_note, questions[]}`
respectively, same status-vocabulary convention as the section-level blocks above. `id` follows
the plan's own numbering (`"1.1"`, `"2.3"`, ...) — keep this in sync with the section it belongs
to if topics are ever renumbered, since nothing derives it automatically from list position.

**Sections 4-6 are deliberately absent from `therapy.json`** — the source plan's own author wrote
"пока не знаю общий план дисциплины" (don't know the overall course plan yet) for those, so
inventing section names/topics for them would be fabricating content the plan's own author
explicitly said doesn't exist yet. Add them for real once the user provides that part of the plan
— same shape as sections 1-3, nothing else needs to change.

**When real content arrives** (e.g. a topic's lecture slides get transcribed): fill the
corresponding `material[]` (a list of HTML-ready strings, rendered one per paragraph — see
`render_topic_content()`/`render_section_content()` in `handlers/therapy.py`) or `questions[]`
(a list of strings for now — MCQ-with-answer-key structure can be added once real graded tests
exist, following `vmeda-biology-bot`'s `quiz_questions[]` schema as a reference point) or `table`
(currently a single string/rendered block — replace with a real structured table format once an
actual comparison table exists; `render_section_content()` will need a small update to render a
structured table instead of a raw string at that point). Leave `status`/`plan_note` in place even
after content is added — they stay as historical/provenance metadata, not read by any "is this
populated" check (`render_topic_content()`/`render_section_content()` branch on whether
`material`/`questions`/`table` is non-empty, not on `status`).

### Navigation

`th:menu` (section list, doubles as the bot's home screen) → `th:section:{id}` (section hub: topic
list + six section-level material buttons) → `th:topic:{section_id}:{topic_id}` (topic hub: theory/
tests buttons) → `th:content:{section_id}:{topic_id}:{theory|tests}` (topic-level material) /
`th:section_content:{section_id}:{ctype}` (section-level material, `ctype` one of
`anatomy_overview`/`comparison_table`/`boundary_control`/`pharma_overview`/`exam_questions`/
`manipulations`). All four callback handlers live in `handlers/therapy.py`; there is no
router/blueprint split beyond that single file yet — if a second subject/section family is ever
added (mirroring how `vmeda-biology-bot` grew from one JSON bank to a dozen), give it its own
`handlers/<name>.py` + top-level `<name>.json`, following `repositories/knowledge.py`'s existing
one-`open()`-per-file pattern, rather than growing `handlers/therapy.py` to cover unrelated
subjects.

### Stats persistence

Deliberately minimal for now — `stats["total_users"]` (a set, serialized to/from a list for JSON,
same convention as `vmeda-biology-bot`), `start_count`, `user_names`/`user_username`. No
referral system, subscriptions, or per-topic progress tracking exist yet — add them the same way
`vmeda-biology-bot` did (a new top-level `stats` key, `.setdefault()` in both branches of
`load_stats()`, a `save_stats()` call after every mutation) if/when the course actually needs
them; don't assume they're wanted just because the sister project has them.

### Admin

`ADMIN_IDS` (env var, comma-separated numeric Telegram IDs) gates `/admin`, which currently only
shows a one-screen stats summary (`cmd_admin` in `telegram_bot.py`) — no grant/revoke access,
broadcasts, or content moderation yet, unlike `vmeda-biology-bot`'s much larger admin panel. Build
these out only once there's an actual access-control or monetization model for this bot — right
now everything in `handlers/therapy.py` is free/ungated for every user, since the course has no
paid tiers defined.

## Known pitfalls (carried over from vmeda-biology-bot, still apply here)

- **Per-topic keyboard labels hardcoded to one topic/status.** If a status/label lookup is ever
  special-cased for one specific topic instead of driven by its own `status` field, it will quietly
  become wrong the moment a second topic reuses that code path. Keep every screen's label driven by
  `STATUS_LABELS[status]`, never a literal string tied to one topic's current situation.
- **Values duplicated out of `therapy.json` into hand-written text.** Don't hardcode a topic name,
  section title, or status note into a screen's text — always read it from `therapy.json` via
  `get_section()`/`get_topic()`, the same way `vmeda-biology-bot` insists on reading prices from
  `SUBSCRIPTION_TIERS` instead of restating them as literals.
