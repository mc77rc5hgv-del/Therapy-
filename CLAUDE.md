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

Lint (config in `pyproject.toml`, same `ruff` rule set as `vmeda-biology-bot` minus the rules that
don't apply here yet):
```
ruff check .
```
`ruff` isn't in `requirements.txt` (dev-only tool) — `pip install ruff`. CI (`.github/workflows/tests.yml`,
runs on every push/PR) installs it, py_compiles, lints, and runs the full test suite — the same
three-step gate `vmeda-biology-bot` uses.

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
merged cells in the original plan). `status` (every block below carries one) is one of the values
in `handlers/therapy.py`'s `STATUS_LABELS` dict (`planned`/`not_started`/`pending`/`in_progress`/
`source_available`/`multiple_variants_unverified`/`unclear_needs_answers`/`practice_only`/
`draft_needs_review`) — add a new key to both `STATUS_LABELS` and any `therapy.json` entry that
needs it together, or the label falls back to a generic `ℹ️ <status>` rendering. Per-block shape:

- `anatomy_overview` / `pharma_overview` / `manipulations`: `{status, plan_note, material[]}` —
  `material` is a list of HTML-ready prose strings, rendered one per paragraph.
- `comparison_table`: `{status, plan_note, table}` — `table` is `null` until a real table exists,
  then `{caption, headers[], rows[{aspect, values[]}]}` — **exactly** `physiology.json`'s
  `comparisons[]` shape in `vmeda-biology-bot`, reused on purpose for precedent. Rendered by
  `render_comparison_table()` as one card per `aspect` (never a raw markdown table — Telegram on
  mobile has no column alignment, see `vmeda-biology-bot`'s `SYSTEM_PROMPT` note on the same
  failure mode). `_table_is_empty(table)` is the single "has this been filled in yet" check —
  branch on it, never on `status`.
- `boundary_control`: `{status, plan_note, mcq[], self_check[]}` — see "Tests: mcq vs self_check"
  below; this block additionally gets a quiz entry point (`th:quiz_start:{id}:-:boundary_control`)
  when `mcq` is non-empty.
- `exam_questions`: `{status, plan_note, items[]}` — `items` is `[{question, answer}]`, `answer`
  optional (`None`/absent renders as a bare self-check question, present renders as a visible
  Q&A pair — no separate graded quiz for this block, exam questions are for review, not testing).

Each **topic** (inside a section's `topics[]`) is `{id, order, title, full_title, theory, tests}`.
`id` follows the plan's own numbering (`"1.1"`, `"2.3"`, ...) — keep this in sync with the section
it belongs to if topics are ever renumbered, since nothing derives it automatically from list
position. `theory` is `{status, plan_note, material[]}` (same shape as the section-level prose
blocks above). `tests` is `{status, plan_note, mcq[], self_check[]}` — see below.

**Tests: `mcq[]` vs `self_check[]`.** This split exists because of the plan itself: several topics
are marked "тесты есть, но ответы не подтверждены" — the question text may already exist, but
nobody has verified which option is actually correct yet. Serving an unverified answer as a graded
"✅/❌" quiz risks teaching a wrong answer with the bot's own authority behind it — same reasoning
`vmeda-biology-bot` uses for Operative Surgery/Physiology `control_questions` (source gives no
answer key → render as a plain self-check list, never a scored quiz). So:
  - `mcq[]`: `{question, options[], correct_index, explanation}` — only ever populate this once the
    correct option is actually confirmed. Non-empty `mcq` is what makes `render_topic_content()`/
    `render_section_content()` show a "▶️ Начать тест" button wired to the quiz engine (see below).
  - `self_check[]`: plain question strings, no answer key — rendered as a numbered list with an
    explicit "ответ ищи в теории" note, never a tappable/graded quiz.
  A topic/block can have both (e.g. a few verified `mcq` plus a longer unverified `self_check`
  list) — `render_topic_content()`/`render_section_content()` check `mcq` first, then `self_check`,
  then fall back to the honest status screen when both are empty.

**Sections 4-6 are deliberately absent from `therapy.json`** — the source plan's own author wrote
"пока не знаю общий план дисциплины" (don't know the overall course plan yet) for those, so
inventing section names/topics for them would be fabricating content the plan's own author
explicitly said doesn't exist yet. Add them for real once the user provides that part of the plan
— same shape as sections 1-3, nothing else needs to change.

**When real content arrives**, fill the relevant field(s) above — the rendering functions already
branch on "is this field non-empty", not on `status`, so no handler code changes are needed. Leave
`status`/`plan_note` in place even after content is added — they stay as historical/provenance
metadata.

### Navigation

`th:menu` (section list, doubles as the bot's home screen) → `th:section:{id}` (section hub: topic
list + six section-level material buttons) → `th:topic:{section_id}:{topic_id}` (topic hub: theory/
tests buttons, marks the topic opened in progress tracking — see below) →
`th:content:{section_id}:{topic_id}:{theory|tests}` (topic-level material) /
`th:section_content:{section_id}:{ctype}` (section-level material, `ctype` one of
`anatomy_overview`/`comparison_table`/`boundary_control`/`pharma_overview`/`exam_questions`/
`manipulations`). All callback handlers live in `handlers/therapy.py`; there is no router/blueprint
split beyond that single file yet — if a second subject/section family is ever added (mirroring how
`vmeda-biology-bot` grew from one JSON bank to a dozen), give it its own `handlers/<name>.py` +
top-level `<name>.json`, following `repositories/knowledge.py`'s existing one-`open()`-per-file
pattern, rather than growing `handlers/therapy.py` to cover unrelated subjects.

### Quiz engine (`mcq[]` questions)

`THERAPY_QUIZ_SESSIONS: dict[user_id -> session]` — plain in-memory dict, same shape/lifecycle as
`vmeda-biology-bot`'s `PHYS_QUIZ_SESSIONS`/`ANATOMY_LATIN_SESSIONS`: created on
`th:quiz_start:{section_id}:{topic_id|-}:{topic_tests|boundary_control}` (`-` stands in for "no
topic_id" when quizzing a section-level `boundary_control` block, since callback_data can't carry
an empty segment cleanly), popped on completion or on `th:quiz_stop`. One active session per user —
starting a new quiz silently replaces whatever session that user had (matches the reference
project's own behavior; there's no cross-session state to lose since nothing is graded until the
session actually completes). `th:quiz_answer:{option_index}` looks the session up by `user_id`
alone, not by any id in its own callback_data, so the option buttons stay small. A **fully
completed** `kind="topic_tests"` session (reached the last question, not stopped early) calls
`record_topic_quiz_completed()` — `kind="boundary_control"` sessions are NOT recorded into
per-topic progress (there's no single topic to attribute a section-wide quiz score to); if
per-section quiz history is ever wanted, add a parallel `stats["therapy_section_progress"]` rather
than overloading the topic-keyed one.

### Search (`search_therapy()`)

Plain case-insensitive substring search, same spirit as `vmeda-biology-bot`'s
`search_physiology()`/`search_operative_surgery()`. `_flatten_texts()` recursively pulls every
string out of a section's or topic's dict/list content into one haystack — this means search
automatically starts matching real content (`material`/`mcq`/`self_check`/`table`) the moment it's
added to `therapy.json`, with zero code change; today it only really matches titles/`plan_note`s
since that's all that's populated. The pending-query text handler
(`handle_therapy_search_query`/`TH_SEARCH_PENDING`, a plain `set[user_id]`) lives in
`telegram_bot.py`, NOT in `handlers/therapy.py` — same load-bearing reason as
`OH_SEARCH_PENDING`/`handle_oh_search_query` in `vmeda-biology-bot`: a text handler registered via
`dp.include_router()` would land after any future unconditional catch-all handler for plain text in
the dispatch chain and never see a search query typed while one exists. There's no such catch-all
in this bot yet, but the ordering is set up defensively now so adding one later can't silently break
search. `handle_therapy_search_query` `raise SkipHandler`s immediately when the sender isn't in
`TH_SEARCH_PENDING`, so it never swallows unrelated text messages (including `/admin`, matched by
`F.text` too) — a future stateful text flow (e.g. an admin content-edit prompt) must do the same.

### Progress tracking (`stats["therapy_progress"]`)

`stats["therapy_progress"][str(user_id)]["{section_id}:{topic_id}"] = {opened_at, last_viewed_at,
quiz_attempts, quiz_best_correct, quiz_best_total}` — flat string key (`"sid:tid"`), not a nested
per-section dict, since a topic is always looked up together with its section and never needs to be
enumerated independently of it. `mark_topic_opened()` is called from `cb_therapy_topic` on every
topic-hub visit (first visit sets `opened_at`, every visit refreshes `last_viewed_at`).
`record_topic_quiz_completed()` keeps a personal-best `(correct, total)` per topic, same
"overwrite only if strictly better" rule as `vmeda-biology-bot`'s `anatomy_latin_scores` — not a
cumulative/running total. `get_therapy_progress_text()` (behind the "📊 Мой прогресс" main-menu
button, `th:progress`) is the only reader today — no gating, SRS, or leaderboard is built on top of
this yet; add those only once the course actually has enough real content to make them meaningful,
rather than pre-building unused machinery.

### Stats persistence

`stats["total_users"]` (a set, serialized to/from a list for JSON, same convention as
`vmeda-biology-bot`), `start_count`, `user_names`/`user_username`, `therapy_progress` (see above).
No referral system or subscriptions exist yet — add them the same way `vmeda-biology-bot` did (a
new top-level `stats` key, `.setdefault()` in both branches of `load_stats()`, a `save_stats()`
call after every mutation) if/when the course actually needs them; don't assume they're wanted just
because the sister project has them.

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
