# -*- coding: utf-8 -*-
"""Раздел «Терапия» — пока единственный предмет бота, поэтому он же выполняет роль главного меню
(в отличие от vmeda-biology-bot, где каждый предмет — один пункт меню среди многих). Контент —
therapy.json, структура 1:1 с планом дисциплины, который прислал пользователь (xlsx, 01.09.2026):
section -> topics[], каждый section дополнительно несёт шесть общих для раздела блоков
(anatomy_overview/comparison_table/boundary_control/pharma_overview/exam_questions/manipulations),
а каждый topic — theory/tests. См. therapy.json meta.provenance_note: ни один медицинский факт
здесь не выдуман, только структура курса и статус-пометки, дословно перенесённые из плана.

Пока реального контента (текст теории, тестовые вопросы, сравнительные таблицы и т.д.) нет —
каждый блок и тема рендерятся «честной заглушкой» (см. `_status_screen()`): статус по плану +
исходная пометка автора плана, без придуманного текста. Это тот же принцип «honest gap, no
invented content», что в vmeda-biology-bot использован для Operative Surgery v1 / Physiology
control_questions — как только появятся реальные материалы (слайды/.ppt/методички кафедры),
соответствующее поле в therapy.json заполняется, и та же функция начинает рендерить настоящий
контент вместо заглушки — код handlers менять не придётся.

**Тесты (topic.tests / section.boundary_control)** — split на `mcq[]` (проверяемые вопросы с
подтверждённым правильным ответом: `{question, options[], correct_index, explanation}`) и
`self_check[]` (список вопросов без ключа ответа — просто строки). Это прямое следствие самого
плана: часть тем помечена «ответы?»/«проверить ответы?» — то есть тесты как текст могут уже быть,
но правильный ответ ещё не подтверждён, и выдавать их как проверяемый quiz было бы риском выдать
неверный ответ как официальный (тот же принцип, что у Operative Surgery/Physiology
`control_questions` в vmeda-biology-bot — там, где источник не даёт проверенного ключа, вопросы
показываются как список для самоконтроля, а не как quiz с проверкой). `mcq[]` даёт кнопку
«▶️ Начать тест» (движок — THERAPY_QUIZ_SESSIONS, тот же паттерн in-memory сессии, что
PHYS_QUIZ_SESSIONS/ANATOMY_LATIN_SESSIONS в vmeda-biology-bot), `self_check[]` — просто
пронумерованный список без ответа. Оба могут быть пустыми одновременно — тогда честная заглушка.

**Сравнительная таблица** (`section.comparison_table.table`) — тот же формат, что
`physiology.json`'s `comparisons[]` в vmeda-biology-bot: `{caption, headers[], rows[{aspect,
values[]}]}`. Рендерится карточками "аспект -> значение по каждому столбцу", НИКОГДА как сырая
markdown-таблица — см. vmeda-biology-bot CLAUDE.md / ai/prompts.py SYSTEM_PROMPT про то, что
таблицы/схемы в Telegram-чате без выравнивания читаются плохо на мобильном.

**Поиск** (`search_therapy()`) — подстрочный поиск по ВСЕМ строковым полям раздела/темы
(`_flatten_texts()` рекурсивно собирает каждую строку из вложенных dict/list) — не нужно вручную
перечислять поля по мере того, как в therapy.json появляется реальный контент (material/mcq/
self_check/table), поиск автоматически начинает находить и его. Сам текстовый ввод запроса
обрабатывается в telegram_bot.py (`TH_SEARCH_PENDING`), а не здесь — тот же приём, что
`OH_SEARCH_PENDING`/`handle_oh_search_query` в vmeda-biology-bot: text-хендлер должен жить в
главном файле, чтобы гарантированно идти раньше любого будущего catch-all хендлера текста.

**Прогресс** (`stats["therapy_progress"][uid]["{sid}:{tid}"]`) — когда тема открыта
(`mark_topic_opened`) и лучший результат по её quiz'у (`record_topic_quiz_completed`, только по
ПОЛНОСТЬЮ пройденной, не прерванной сессии — тот же принцип, что `physiology_progress` в
vmeda-biology-bot). Пока не используется ни для гейтинга, ни для SRS — просто чтобы у бота уже
была основа для «мой прогресс», когда в разделах появится реальный контент, есть что показывать.

**Покрытие контента** (`get_admin_coverage_text()`, за кнопкой «📋 Что не хватает» в /admin) —
чек-лист по структуре плана, какие блоки/темы всё ещё рендерят заглушку, а какие уже реально
заполнены. Отдельная вещь от `search_therapy()` (тот ищет по тексту, этот считает "заполнено/не
заполнено" по каждому листу дерева контента) — нужен, чтобы пользователь как автор контента видел
прогресс наполнения бота, а не только прогресс студентов. Те же предикаты (`_section_content_filled`/
`_topic_content_filled`) теперь ещё и красят кнопки разделов/тем иконкой ✅/📥/🗓 в обычной
навигации — один источник правды "заполнено или нет" на оба применения.

**Навигация** — темы внутри раздела листаются каруселью (◀️/▶️ на экране темы, без возврата к
списку раздела на каждый шаг), у каждой темы есть переключатель «⭐ В избранное»
(`stats["therapy_favorites"]`), главное меню предлагает «▶️ Продолжить» (последняя просмотренная
тема по `therapy_progress`) и «🎲 Случайный вопрос» (одна mcq-вопрос из ВСЕЙ базы, не привязана к
конкретной теме — `start_random_practice()`, тот же `THERAPY_QUIZ_SESSIONS`, просто `kind
="random_practice"` и `total=1`; в progress не пишется, это разовая тренировка, а не прогресс по
теме). `get_back_keyboard()` сама добавляет кнопку «🏠 Меню» на любом экране глубже главного —
чтобы вернуться в начало не нужно было жать «Назад» несколько раз подряд.

Импортирует telegram_bot как tb — тот же паттерн, что и handlers/physiology.py в vmeda-biology-bot
(поздно подключаемый модуль, использующий DIVIDER/safe_edit_text/stats, уже определённые там)."""
import html
import random
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import telegram_bot as tb

router = Router()

SECTION_CONTENT_TYPES = [
    ("anatomy_overview", "🧬 Обзор анатомии"),
    ("comparison_table", "📊 Сравнительная таблица"),
    ("boundary_control", "🎯 Рубежный контроль"),
    ("pharma_overview", "💊 Обзор фармакологии"),
    ("exam_questions", "🎓 Экзаменационные вопросы"),
    ("manipulations", "🩺 Манипуляции"),
]
TOPIC_CONTENT_TYPES = [
    ("theory", "📖 Теория"),
    ("tests", "📝 Тесты"),
]

STATUS_LABELS = {
    "planned": "🗓 В планах",
    "not_started": "🗓 Ещё не начато",
    "pending": "⏳ Ожидаем материалы",
    "in_progress": "🔧 В работе",
    "source_available": "📥 Исходники есть, не перенесено в бота",
    "multiple_variants_unverified": "📥 Есть варианты, требуют сверки",
    "unclear_needs_answers": "❓ Требует проверки ответов",
    "practice_only": "📥 Есть практический вариант",
    "draft_needs_review": "📥 Черновик есть, требует проверки",
}

# in-memory сессии прохождения теста, dict[user_id -> session] — тот же паттерн, что
# PHYS_QUIZ_SESSIONS/ANATOMY_LATIN_SESSIONS в vmeda-biology-bot: попадает в словарь на старте,
# убирается по завершении/прерыванию.
THERAPY_QUIZ_SESSIONS: dict = {}

SEARCH_RESULTS_LIMIT = 15


def esc(text: str) -> str:
    return html.escape(str(text), quote=False)


# ==================== data lookups ====================

def get_section(section_id: str):
    for s in tb.THERAPY["sections"]:
        if s["id"] == section_id:
            return s
    return None


def get_topic(section_id: str, topic_id: str):
    section = get_section(section_id)
    if not section:
        return None
    for t in section["topics"]:
        if t["id"] == topic_id:
            return t
    return None


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, f"ℹ️ {esc(status)}")


# ==================== прогресс ====================
# stats["therapy_progress"][str(uid)]["{sid}:{tid}"] = {opened_at, last_viewed_at, quiz_attempts,
# quiz_best_correct, quiz_best_total} — ключ "sid:tid" (не вложенный dict per sid), потому что
# темы всегда просматриваются вместе со своим разделом, отдельная вложенность не нужна.

def _progress_key(section_id: str, topic_id: str) -> str:
    return f"{section_id}:{topic_id}"


def _progress_entry(user_id: int, section_id: str, topic_id: str) -> dict:
    all_p = tb.stats["therapy_progress"].setdefault(str(user_id), {})
    return all_p.setdefault(_progress_key(section_id, topic_id), {
        "opened_at": None, "last_viewed_at": None,
        "quiz_attempts": 0, "quiz_best_correct": None, "quiz_best_total": None,
    })


def mark_topic_opened(user_id: int, section_id: str, topic_id: str) -> None:
    entry = _progress_entry(user_id, section_id, topic_id)
    now = time.time()
    if entry["opened_at"] is None:
        entry["opened_at"] = now
    entry["last_viewed_at"] = now
    tb.save_stats()


def record_topic_quiz_completed(user_id: int, section_id: str, topic_id: str, correct: int, total: int) -> None:
    entry = _progress_entry(user_id, section_id, topic_id)
    entry["quiz_attempts"] += 1
    best_total = entry["quiz_best_total"]
    best_correct = entry["quiz_best_correct"]
    is_better = (
        best_total is None
        or (total > 0 and best_total > 0 and correct / total > best_correct / best_total)
        or (total > 0 and (best_total or 0) == 0)
    )
    if is_better:
        entry["quiz_best_correct"] = correct
        entry["quiz_best_total"] = total
    tb.save_stats()


def get_therapy_progress_text(user_id: int) -> str:
    all_p = tb.stats["therapy_progress"].get(str(user_id), {})
    total_topics = sum(len(s["topics"]) for s in tb.THERAPY["sections"])
    opened = sum(1 for v in all_p.values() if v.get("opened_at"))
    lines = ["📊 <b>Мой прогресс</b>", tb.DIVIDER, f"Открыто тем: {opened} из {total_topics}"]
    quizzed = {k: v for k, v in all_p.items() if v.get("quiz_attempts")}
    if quizzed:
        lines.append("")
        lines.append("Пройденные тесты:")
        for key, entry in quizzed.items():
            sid, tid = key.split(":", 1)
            topic = get_topic(sid, tid)
            title = topic["title"] if topic else key
            lines.append(
                f"  • {esc(title)}: {entry['quiz_best_correct']}/{entry['quiz_best_total']} "
                f"(попыток: {entry['quiz_attempts']})"
            )
    else:
        lines.append("")
        lines.append("Тесты с проверкой ответа появятся, как только по темам будут добавлены проверенные вопросы.")
    return "\n".join(lines)


def get_last_viewed_topic(user_id: int):
    """(section_id, topic_id) последней открытой темы этого пользователя, или None — используется
    кнопкой «▶️ Продолжить» на главном меню."""
    all_p = tb.stats["therapy_progress"].get(str(user_id), {})
    candidates = [(key, entry) for key, entry in all_p.items() if entry.get("last_viewed_at")]
    if not candidates:
        return None
    key, _ = max(candidates, key=lambda kv: kv[1]["last_viewed_at"])
    section_id, topic_id = key.split(":", 1)
    if not get_topic(section_id, topic_id):
        return None
    return section_id, topic_id


# ==================== избранное ====================
# stats["therapy_favorites"][str(uid)] = ["sid:tid", ...] — плоский список ключей той же формы,
# что _progress_key() (JSON не хранит set, а вложенный dict здесь не даёт ничего сверх списка).

def is_topic_favorite(user_id: int, section_id: str, topic_id: str) -> bool:
    return _progress_key(section_id, topic_id) in tb.stats["therapy_favorites"].get(str(user_id), [])


def toggle_topic_favorite(user_id: int, section_id: str, topic_id: str) -> bool:
    """Переключает избранное для темы, возвращает новое состояние (True = теперь в избранном)."""
    favs = tb.stats["therapy_favorites"].setdefault(str(user_id), [])
    key = _progress_key(section_id, topic_id)
    if key in favs:
        favs.remove(key)
        is_fav = False
    else:
        favs.append(key)
        is_fav = True
    tb.save_stats()
    return is_fav


def get_favorite_topics(user_id: int) -> list:
    """Темы из избранного, которые реально существуют в текущем therapy.json — тема могла быть
    переименована/убрана из плана уже после того, как её кто-то отметил звёздочкой."""
    result = []
    for key in tb.stats["therapy_favorites"].get(str(user_id), []):
        section_id, topic_id = key.split(":", 1)
        topic = get_topic(section_id, topic_id)
        if topic:
            result.append((section_id, topic_id, topic))
    return result


def get_favorites_text(user_id: int) -> str:
    favorites = get_favorite_topics(user_id)
    if not favorites:
        return (
            "⭐ <b>Избранное</b>\n\n"
            "Пока пусто — на экране темы есть кнопка «☆ В избранное», отмеченные темы появятся здесь."
        )
    lines = ["⭐ <b>Избранное</b>", tb.DIVIDER]
    for section_id, topic_id, topic in favorites:
        section = get_section(section_id)
        lines.append(f"  • {esc(topic['id'])} {esc(topic['title'])} ({esc(section['short_title'])})")
    return "\n".join(lines)


def get_favorites_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()
    for section_id, topic_id, topic in get_favorite_topics(user_id):
        builder.button(text=f"{topic['id']} {topic['title']}", callback_data=f"th:topic:{section_id}:{topic_id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 Меню", callback_data="th:menu"))
    return builder.as_markup()


# ==================== админ: покрытие контента ====================
# Пока therapy.json — по большей части заглушки (см. модульный docstring), самому пользователю
# предстоит вручную наполнять material/mcq/self_check/table по мере поступления слайдов/.ppt.
# Этот экран — чек-лист "что ещё не заполнено" по структуре ИМЕННО плана (а не общий текстовый
# поиск, который уже есть в search_therapy()) — не гейтит и не блокирует ничего, просто отвечает
# на вопрос "куда наполнять дальше", без похода в raw JSON руками.

def _section_content_filled(section: dict, ctype: str) -> bool:
    block = section[ctype]
    if ctype == "comparison_table":
        return not _table_is_empty(block.get("table"))
    if ctype in ("boundary_control",):
        return bool(block.get("mcq") or block.get("self_check"))
    if ctype == "exam_questions":
        return bool(block.get("items"))
    return bool(block.get("material"))


def _topic_content_filled(topic: dict, ctype: str) -> bool:
    block = topic[ctype]
    if ctype == "tests":
        return bool(block.get("mcq") or block.get("self_check"))
    return bool(block.get("material"))


def _topic_status_icon(topic: dict) -> str:
    """✅ и теория, и тесты заполнены; 📥 заполнено частично; 🗓 пока ничего — используется в
    get_section_keyboard(), чтобы студент видел заполненность темы, не открывая её."""
    has_theory = _topic_content_filled(topic, "theory")
    has_tests = _topic_content_filled(topic, "tests")
    if has_theory and has_tests:
        return "✅"
    if has_theory or has_tests:
        return "📥"
    return "🗓"


def get_admin_coverage_text() -> str:
    lines = ["📋 <b>Что ещё нужно наполнить</b>", tb.DIVIDER]
    total_leaves = 0
    filled_leaves = 0
    for section in tb.THERAPY["sections"]:
        section_missing = [
            label for ctype, label in SECTION_CONTENT_TYPES if not _section_content_filled(section, ctype)
        ]
        total_leaves += len(SECTION_CONTENT_TYPES)
        filled_leaves += len(SECTION_CONTENT_TYPES) - len(section_missing)

        topic_missing = []
        for topic in section["topics"]:
            for ctype, label in TOPIC_CONTENT_TYPES:
                total_leaves += 1
                if _topic_content_filled(topic, ctype):
                    filled_leaves += 1
                else:
                    topic_missing.append(f"{topic['id']} {label}")

        lines.append(f"<b>{esc(section['title'])}</b>")
        if not section_missing and not topic_missing:
            lines.append("  ✅ всё заполнено")
        else:
            if section_missing:
                lines.append("  Раздел: " + ", ".join(section_missing))
            if topic_missing:
                lines.append("  Темы: " + ", ".join(topic_missing))
        lines.append("")

    pct = round(100 * filled_leaves / total_leaves) if total_leaves else 0
    lines.append(f"Итого заполнено: {filled_leaves}/{total_leaves} ({pct}%)")
    return "\n".join(lines).strip()


# ==================== поиск ====================

def _flatten_texts(value) -> list:
    """Рекурсивно собирает каждую строку из вложенного dict/list в один список — так поиск
    автоматически покрывает любое новое поле (material/mcq/self_check/table), появившееся в
    therapy.json, без ручного перечисления полей здесь."""
    out = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(_flatten_texts(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_flatten_texts(v))
    return out


def search_therapy(query: str, limit: int = SEARCH_RESULTS_LIMIT) -> list:
    q = query.strip().lower()
    if not q:
        return []
    results = []
    for section in tb.THERAPY["sections"]:
        section_only = {k: v for k, v in section.items() if k != "topics"}
        if q in " ".join(_flatten_texts(section_only)).lower():
            results.append({"label": f"📂 {section['title']}", "callback_data": f"th:section:{section['id']}"})
        for topic in section["topics"]:
            if q in " ".join(_flatten_texts(topic)).lower():
                results.append({
                    "label": f"📄 {topic['id']} {topic['title']} ({section['short_title']})",
                    "callback_data": f"th:topic:{section['id']}:{topic['id']}",
                })
        if len(results) >= limit:
            break
    return results[:limit]


def get_search_results_keyboard(results: list):
    builder = InlineKeyboardBuilder()
    for r in results:
        builder.button(text=r["label"], callback_data=r["callback_data"])
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔎 Искать ещё", callback_data="th:search_prompt"))
    builder.row(InlineKeyboardButton(text="🔙 К разделам", callback_data="th:menu"))
    return builder.as_markup()


def get_search_results_text(query: str, results: list) -> str:
    if not results:
        return (
            f"🔎 По запросу «{esc(query)}» ничего не найдено.\n\n"
            "Пока в боте нет реального текста тем (только структура курса и статус-пометки) — "
            "поиск начнёт находить содержание тем и вопросов, как только оно будет добавлено."
        )
    return f"🔎 По запросу «{esc(query)}» найдено: {len(results)}"


# ==================== сравнительная таблица ====================
# table: {caption, headers[], rows[{aspect, values[]}]} — тот же формат, что comparisons[] в
# physiology.json (vmeda-biology-bot). Рендерится карточками, никогда как сырая markdown-таблица.

def _table_is_empty(table) -> bool:
    return not table or not table.get("rows")


def render_comparison_table(table: dict) -> str:
    lines = []
    if table.get("caption"):
        lines.append(f"<b>{esc(table['caption'])}</b>")
        lines.append(tb.DIVIDER)
    headers = table.get("headers", [])
    for row in table.get("rows", []):
        lines.append(f"<b>{esc(row.get('aspect', ''))}</b>")
        for h, v in zip(headers, row.get("values", [])):
            lines.append(f"  • {esc(h)}: {esc(v)}")
        lines.append("")
    return "\n".join(lines).strip()


# ==================== keyboards ====================

def get_therapy_menu_keyboard(user_id: int = None):
    builder = InlineKeyboardBuilder()
    if user_id is not None:
        last = get_last_viewed_topic(user_id)
        if last:
            section_id, topic_id = last
            topic = get_topic(section_id, topic_id)
            builder.row(InlineKeyboardButton(
                text=f"▶️ Продолжить: {topic['id']} {topic['title']}",
                callback_data=f"th:topic:{section_id}:{topic_id}",
            ))
    for section in tb.THERAPY["sections"]:
        builder.button(text=f"{section['order']}. {section['title']}", callback_data=f"th:section:{section['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🎲 Случайный вопрос", callback_data="th:random_practice"))
    builder.row(InlineKeyboardButton(text="⭐ Избранное", callback_data="th:favorites"))
    builder.row(InlineKeyboardButton(text="🔎 Поиск по разделам", callback_data="th:search_prompt"))
    builder.row(InlineKeyboardButton(text="📊 Мой прогресс", callback_data="th:progress"))
    return builder.as_markup()


def get_section_keyboard(section_id: str):
    section = get_section(section_id)
    builder = InlineKeyboardBuilder()
    for topic in section["topics"]:
        icon = _topic_status_icon(topic)
        builder.button(
            text=f"{icon} {topic['id']} {topic['title']}", callback_data=f"th:topic:{section_id}:{topic['id']}",
        )
    builder.adjust(1)

    content_builder = InlineKeyboardBuilder()
    for ctype, label in SECTION_CONTENT_TYPES:
        icon = "✅" if _section_content_filled(section, ctype) else "🗓"
        content_builder.button(text=f"{icon} {label}", callback_data=f"th:section_content:{section_id}:{ctype}")
    content_builder.adjust(2)
    builder.attach(content_builder)

    builder.row(InlineKeyboardButton(text="🔙 К разделам", callback_data="th:menu"))
    return builder.as_markup()


def get_topic_keyboard(section_id: str, topic_id: str, user_id: int):
    """Карусель тем (◀️/▶️ на соседние темы того же раздела, без возврата к списку раздела на
    каждый шаг) + переключатель избранного + быстрый переход в меню."""
    section = get_section(section_id)
    topics = section["topics"]
    idx = next(i for i, t in enumerate(topics) if t["id"] == topic_id)

    builder = InlineKeyboardBuilder()
    for ctype, label in TOPIC_CONTENT_TYPES:
        builder.button(text=label, callback_data=f"th:content:{section_id}:{topic_id}:{ctype}")
    builder.adjust(2)

    if idx > 0:
        prev_topic = topics[idx - 1]
        builder.row(InlineKeyboardButton(
            text=f"◀️ {prev_topic['id']} {prev_topic['title']}",
            callback_data=f"th:topic:{section_id}:{prev_topic['id']}",
        ))
    if idx < len(topics) - 1:
        next_topic = topics[idx + 1]
        builder.row(InlineKeyboardButton(
            text=f"{next_topic['id']} {next_topic['title']} ▶️",
            callback_data=f"th:topic:{section_id}:{next_topic['id']}",
        ))

    fav_text = "★ Убрать из избранного" if is_topic_favorite(user_id, section_id, topic_id) else "☆ В избранное"
    builder.row(InlineKeyboardButton(text=fav_text, callback_data=f"th:fav_toggle:{section_id}:{topic_id}"))
    builder.row(InlineKeyboardButton(text="🔙 К разделу", callback_data=f"th:section:{section_id}"))
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="th:menu"))
    return builder.as_markup()


def get_back_keyboard(back_callback: str, extra_buttons=None):
    """Плюс «🏠 Меню» на любом экране глубже главного, чтобы вернуться в начало не нужно было
    жать «Назад» несколько раз подряд по всей цепочке навигации."""
    builder = InlineKeyboardBuilder()
    for text, callback_data in extra_buttons or []:
        builder.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback))
    if back_callback != "th:menu":
        builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="th:menu"))
    return builder.as_markup()


# ==================== text rendering ====================

def get_therapy_menu_text() -> str:
    return "🏥 <b>Терапия</b>\n\nВыбери раздел:"


def get_section_text(section_id: str) -> str:
    section = get_section(section_id)
    lines = [f"🏥 <b>{esc(section['title'])}</b>", tb.DIVIDER]
    ov = section["anatomy_overview"]
    lines.append(f"🧬 <b>Обзор анатомии</b>: {status_label(ov['status'])}")
    lines.append(f"<i>{esc(ov['plan_note'])}</i>")
    lines.append("")
    lines.append("📋 <b>Темы раздела:</b>")
    for topic in section["topics"]:
        lines.append(f"  • {esc(topic['id'])} {esc(topic['title'])}")
    if section.get("open_note"):
        lines.append("")
        lines.append(f"<i>{esc(section['open_note'])}</i>")
    lines.append("")
    lines.append("Ниже — общие материалы по разделу, а темы выше открывают теорию/тесты по конкретному заболеванию.")
    return "\n".join(lines)


def get_topic_text(section_id: str, topic_id: str) -> str:
    section = get_section(section_id)
    topic = get_topic(section_id, topic_id)
    return "\n".join([
        f"🏥 {esc(section['title'])}",
        f"📄 <b>{esc(topic['id'])} {esc(topic['full_title'])}</b>",
        tb.DIVIDER,
        f"📖 Теория: {status_label(topic['theory']['status'])}",
        f"📝 Тесты: {status_label(topic['tests']['status'])}",
    ])


def _status_screen(title: str, status: str, plan_note: str, breadcrumb: str) -> str:
    return "\n".join([
        breadcrumb,
        f"<b>{esc(title)}</b>",
        tb.DIVIDER,
        f"Статус: {status_label(status)}",
        "",
        f"<i>{esc(plan_note)}</i>",
        "",
        "Материалы по этому пункту ещё не добавлены в бота — они появятся здесь, как только будут перенесены из исходников кафедры.",
    ])


def _render_self_check(breadcrumb: str, title: str, questions: list) -> str:
    lines = [breadcrumb, f"<b>{esc(title)}</b>", tb.DIVIDER,
             "<i>Вопросы для самоконтроля — готового ключа ответов пока нет, ответ ищи в теории.</i>", ""]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {esc(q)}")
    return "\n".join(lines)


def render_topic_content(section_id: str, topic_id: str, ctype: str):
    """Возвращает (text, keyboard) для одного из TOPIC_CONTENT_TYPES."""
    section = get_section(section_id)
    topic = get_topic(section_id, topic_id)
    label = dict(TOPIC_CONTENT_TYPES)[ctype]
    block = topic[ctype]
    breadcrumb = f"🏥 {esc(section['title'])} → {esc(topic['id'])} {esc(topic['title'])}"
    back_cb = f"th:topic:{section_id}:{topic_id}"

    if ctype == "theory":
        if block["material"]:
            lines = [breadcrumb, f"📖 <b>{esc(topic['full_title'])}</b>", tb.DIVIDER]
            for item in block["material"]:
                lines.append(item)
                lines.append("")
            return "\n".join(lines).strip(), get_back_keyboard(back_cb)
        return _status_screen(f"{label}: {topic['full_title']}", block["status"], block["plan_note"], breadcrumb), \
            get_back_keyboard(back_cb)

    # ctype == "tests"
    if block["mcq"]:
        text = "\n".join([
            breadcrumb, f"📝 <b>Тесты: {esc(topic['full_title'])}</b>", tb.DIVIDER,
            f"Вопросов с проверкой ответа: {len(block['mcq'])}",
        ])
        quiz_button = ("▶️ Начать тест", f"th:quiz_start:{section_id}:{topic_id}:topic_tests")
        return text, get_back_keyboard(back_cb, extra_buttons=[quiz_button])
    if block["self_check"]:
        return _render_self_check(breadcrumb, f"Тесты: {topic['full_title']}", block["self_check"]), \
            get_back_keyboard(back_cb)
    return _status_screen(f"{label}: {topic['full_title']}", block["status"], block["plan_note"], breadcrumb), \
        get_back_keyboard(back_cb)


def render_section_content(section_id: str, ctype: str):
    """Возвращает (text, keyboard) для одного из SECTION_CONTENT_TYPES."""
    section = get_section(section_id)
    label = dict(SECTION_CONTENT_TYPES)[ctype]
    block = section[ctype]
    breadcrumb = f"🏥 {esc(section['title'])}"
    back_cb = f"th:section:{section_id}"

    if ctype == "comparison_table":
        table = block.get("table")
        if not _table_is_empty(table):
            text = "\n".join([breadcrumb, f"{label}", tb.DIVIDER, render_comparison_table(table)])
            return text, get_back_keyboard(back_cb)
        return _status_screen(f"{label}: {section['title']}", block["status"], block["plan_note"], breadcrumb), \
            get_back_keyboard(back_cb)

    if ctype == "boundary_control":
        if block["mcq"]:
            text = "\n".join([
                breadcrumb, f"{label}", tb.DIVIDER, f"Вопросов с проверкой ответа: {len(block['mcq'])}",
            ])
            quiz_button = ("▶️ Начать тест", f"th:quiz_start:{section_id}:-:boundary_control")
            return text, get_back_keyboard(back_cb, extra_buttons=[quiz_button])
        if block["self_check"]:
            return _render_self_check(breadcrumb, f"{label}: {section['title']}", block["self_check"]), \
                get_back_keyboard(back_cb)
        return _status_screen(f"{label}: {section['title']}", block["status"], block["plan_note"], breadcrumb), \
            get_back_keyboard(back_cb)

    if ctype == "exam_questions":
        items = block.get("items", [])
        if items:
            lines = [breadcrumb, f"{label}", tb.DIVIDER]
            for i, item in enumerate(items, 1):
                lines.append(f"{i}. {esc(item['question'])}")
                if item.get("answer"):
                    lines.append(f"   💬 {esc(item['answer'])}")
                lines.append("")
            return "\n".join(lines).strip(), get_back_keyboard(back_cb)
        return _status_screen(f"{label}: {section['title']}", block["status"], block["plan_note"], breadcrumb), \
            get_back_keyboard(back_cb)

    # anatomy_overview / pharma_overview / manipulations — material[]
    if block.get("material"):
        lines = [breadcrumb, f"{label}", tb.DIVIDER]
        for item in block["material"]:
            lines.append(item)
            lines.append("")
        return "\n".join(lines).strip(), get_back_keyboard(back_cb)
    return _status_screen(f"{label}: {section['title']}", block["status"], block["plan_note"], breadcrumb), \
        get_back_keyboard(back_cb)


# ==================== quiz engine (topic tests / boundary control) ====================
# THERAPY_QUIZ_SESSIONS живёт, пока не завершится/не прервётся сессия — но если студент просто
# закрыл чат посреди теста, ни то, ни другое никогда не случится, и запись осталась бы в словаре
# навсегда (тихая утечка памяти на долго работающем процессе). Явного фонового таска для очистки
# заводить не стали — вместо этого ленивый sweep при каждом НОВОМ старте теста (единственная
# точка входа, где размер словаря вообще растёт), тот же компромисс "просто и достаточно", что и
# остальная часть этого MVP.
QUIZ_SESSION_TTL_SECONDS = 3 * 3600


def _sweep_stale_quiz_sessions() -> None:
    now = time.time()
    stale = [uid for uid, s in THERAPY_QUIZ_SESSIONS.items() if now - s["started_at"] > QUIZ_SESSION_TTL_SECONDS]
    for uid in stale:
        THERAPY_QUIZ_SESSIONS.pop(uid, None)


def _quiz_questions_for(section_id: str, topic_id, kind: str) -> list:
    if kind == "topic_tests":
        topic = get_topic(section_id, topic_id)
        return topic["tests"]["mcq"] if topic else []
    if kind == "boundary_control":
        section = get_section(section_id)
        return section["boundary_control"]["mcq"] if section else []
    return []


def start_therapy_quiz(user_id: int, section_id: str, topic_id, kind: str, back_callback: str) -> dict:
    _sweep_stale_quiz_sessions()
    questions = _quiz_questions_for(section_id, topic_id, kind)
    session = {
        "sid": section_id, "tid": topic_id, "kind": kind,
        "questions": questions, "idx": 0, "correct": 0, "total": len(questions),
        "back_callback": back_callback, "started_at": time.time(),
    }
    THERAPY_QUIZ_SESSIONS[user_id] = session
    return session


def render_quiz_question(session: dict):
    q = session["questions"][session["idx"]]
    text = "\n".join([
        f"❓ Вопрос {session['idx'] + 1}/{session['total']}", tb.DIVIDER, esc(q["question"]),
    ])
    builder = InlineKeyboardBuilder()
    for i, opt in enumerate(q["options"]):
        builder.button(text=opt, callback_data=f"th:quiz_answer:{i}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🛑 Закончить", callback_data="th:quiz_stop"))
    return text, builder.as_markup()


def render_quiz_summary(session: dict, aborted: bool):
    answered = session["idx"]
    pct = round(100 * session["correct"] / answered) if answered else 0
    text = "\n".join([
        "🛑 Тест прерван" if aborted else "🏁 Тест завершён",
        tb.DIVIDER,
        f"Правильно: {session['correct']} из {answered} ({pct}%)",
    ])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=session["back_callback"]))
    if session["back_callback"] != "th:menu":
        builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="th:menu"))
    return text, builder.as_markup()


def _all_mcq_pool() -> list:
    """Каждый проверяемый вопрос во всей базе (topic.tests.mcq + section.boundary_control.mcq) —
    для «🎲 Случайный вопрос» на главном меню, единственного способа тренироваться сразу по всем
    темам, а не заходить в каждую по очереди."""
    pool = []
    for section in tb.THERAPY["sections"]:
        pool.extend(section["boundary_control"]["mcq"])
        for topic in section["topics"]:
            pool.extend(topic["tests"]["mcq"])
    return pool


def start_random_practice(user_id: int):
    """Одна случайная mcq-вопрос из всей базы как разовая сессия (kind="random_practice",
    total=1) — использует тот же движок THERAPY_QUIZ_SESSIONS/render_quiz_question, что и обычный
    тест по теме, но не привязана к конкретной теме, поэтому НЕ пишется в therapy_progress (там
    результат имеет смысл только в разрезе одной темы). Возвращает None, если во всей базе ещё
    нет ни одного mcq-вопроса — вызывающий код должен явно это обработать, а не звать вслепую."""
    _sweep_stale_quiz_sessions()
    pool = _all_mcq_pool()
    if not pool:
        return None
    session = {
        "sid": None, "tid": None, "kind": "random_practice",
        "questions": [random.choice(pool)], "idx": 0, "correct": 0, "total": 1,
        "back_callback": "th:menu", "started_at": time.time(),
    }
    THERAPY_QUIZ_SESSIONS[user_id] = session
    return session


@router.callback_query(F.data.startswith("th:quiz_start:"))
async def cb_therapy_quiz_start(callback: CallbackQuery):
    _, _, section_id, tid_raw, kind = callback.data.split(":")
    topic_id = None if tid_raw == "-" else tid_raw
    questions = _quiz_questions_for(section_id, topic_id, kind)
    if not questions:
        await callback.answer("Проверяемых вопросов пока нет", show_alert=True)
        return
    back_callback = f"th:topic:{section_id}:{topic_id}" if kind == "topic_tests" else f"th:section:{section_id}"
    session = start_therapy_quiz(callback.from_user.id, section_id, topic_id, kind, back_callback)
    await callback.answer()
    text, keyboard = render_quiz_question(session)
    await tb.safe_edit_text(callback.message, text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("th:quiz_answer:"))
async def cb_therapy_quiz_answer(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = THERAPY_QUIZ_SESSIONS.get(user_id)
    if not session:
        await callback.answer()
        return
    chosen = int(callback.data.split(":")[2])
    q = session["questions"][session["idx"]]
    is_correct = chosen == q["correct_index"]
    if is_correct:
        session["correct"] += 1
    alert_text = "✅ Верно!" if is_correct else f"❌ Неверно.{(' ' + q['explanation']) if q.get('explanation') else ''}"
    await callback.answer(alert_text, show_alert=not is_correct)

    session["idx"] += 1
    if session["idx"] >= session["total"]:
        THERAPY_QUIZ_SESSIONS.pop(user_id, None)
        if session["kind"] == "topic_tests":
            record_topic_quiz_completed(user_id, session["sid"], session["tid"], session["correct"], session["total"])
        text, keyboard = render_quiz_summary(session, aborted=False)
    else:
        text, keyboard = render_quiz_question(session)
    await tb.safe_edit_text(callback.message, text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "th:quiz_stop")
async def cb_therapy_quiz_stop(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = THERAPY_QUIZ_SESSIONS.pop(user_id, None)
    await callback.answer()
    if not session:
        await tb.safe_edit_text(
            callback.message,
            get_therapy_menu_text(),
            parse_mode="HTML",
            reply_markup=get_therapy_menu_keyboard(user_id),
        )
        return
    text, keyboard = render_quiz_summary(session, aborted=True)
    await tb.safe_edit_text(callback.message, text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "th:random_practice")
async def cb_therapy_random_practice(callback: CallbackQuery):
    session = start_random_practice(callback.from_user.id)
    if not session:
        await callback.answer(
            "Пока во всей базе нет ни одного проверяемого вопроса — появится, как только темы наполнятся.",
            show_alert=True,
        )
        return
    await callback.answer()
    text, keyboard = render_quiz_question(session)
    await tb.safe_edit_text(callback.message, text, parse_mode="HTML", reply_markup=keyboard)


# ==================== handlers ====================

@router.callback_query(F.data == "th:menu")
async def cb_therapy_menu(callback: CallbackQuery):
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        get_therapy_menu_text(),
        parse_mode="HTML",
        reply_markup=get_therapy_menu_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "th:favorites")
async def cb_therapy_favorites(callback: CallbackQuery):
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        get_favorites_text(callback.from_user.id),
        parse_mode="HTML",
        reply_markup=get_favorites_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data.startswith("th:fav_toggle:"))
async def cb_therapy_fav_toggle(callback: CallbackQuery):
    _, _, section_id, topic_id = callback.data.split(":")
    topic = get_topic(section_id, topic_id)
    if not topic:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    is_fav = toggle_topic_favorite(callback.from_user.id, section_id, topic_id)
    await callback.answer("⭐ Добавлено в избранное" if is_fav else "☆ Убрано из избранного")
    await tb.safe_edit_text(
        callback.message,
        get_topic_text(section_id, topic_id),
        parse_mode="HTML",
        reply_markup=get_topic_keyboard(section_id, topic_id, callback.from_user.id),
    )


@router.callback_query(F.data == "th:progress")
async def cb_therapy_progress(callback: CallbackQuery):
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        get_therapy_progress_text(callback.from_user.id),
        parse_mode="HTML",
        reply_markup=get_back_keyboard("th:menu"),
    )


@router.callback_query(F.data == "th:search_prompt")
async def cb_therapy_search_prompt(callback: CallbackQuery):
    tb.ADMIN_BROADCAST_PENDING.discard(callback.from_user.id)  # взаимоисключающие текстовые ожидания
    tb.TH_SEARCH_PENDING.add(callback.from_user.id)
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        "🔎 Напиши слово или фразу для поиска по разделам и темам «Терапии».",
        reply_markup=get_back_keyboard("th:menu"),
    )


@router.callback_query(F.data.startswith("th:section:"))
async def cb_therapy_section(callback: CallbackQuery):
    section_id = callback.data.split(":")[2]
    section = get_section(section_id)
    if not section:
        await callback.answer("Раздел не найден", show_alert=True)
        return
    await callback.answer()
    await tb.safe_edit_text(
        callback.message, get_section_text(section_id), parse_mode="HTML", reply_markup=get_section_keyboard(section_id),
    )


@router.callback_query(F.data.startswith("th:topic:"))
async def cb_therapy_topic(callback: CallbackQuery):
    _, _, section_id, topic_id = callback.data.split(":")
    topic = get_topic(section_id, topic_id)
    if not topic:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    mark_topic_opened(callback.from_user.id, section_id, topic_id)
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        get_topic_text(section_id, topic_id),
        parse_mode="HTML",
        reply_markup=get_topic_keyboard(section_id, topic_id, callback.from_user.id),
    )


@router.callback_query(F.data.startswith("th:content:"))
async def cb_therapy_content(callback: CallbackQuery):
    _, _, section_id, topic_id, ctype = callback.data.split(":")
    topic = get_topic(section_id, topic_id)
    if not topic or ctype not in dict(TOPIC_CONTENT_TYPES):
        await callback.answer("Материал не найден", show_alert=True)
        return
    await callback.answer()
    text, keyboard = render_topic_content(section_id, topic_id, ctype)
    await tb.safe_edit_text(callback.message, text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("th:section_content:"))
async def cb_therapy_section_content(callback: CallbackQuery):
    _, _, section_id, ctype = callback.data.split(":")
    section = get_section(section_id)
    if not section or ctype not in dict(SECTION_CONTENT_TYPES):
        await callback.answer("Материал не найден", show_alert=True)
        return
    await callback.answer()
    text, keyboard = render_section_content(section_id, ctype)
    await tb.safe_edit_text(callback.message, text, parse_mode="HTML", reply_markup=keyboard)
