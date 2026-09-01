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
соответствующее поле (`material`/`questions`/`table`) в therapy.json заполняется, и эта же
функция начинает рендерить настоящий контент вместо заглушки — код handlers менять не придётся.

Импортирует telegram_bot как tb — тот же паттерн, что и handlers/physiology.py в vmeda-biology-bot
(поздно подключаемый модуль, использующий DIVIDER/safe_edit_text/stats, уже определённые там)."""
import html

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


# ==================== keyboards ====================

def get_therapy_menu_keyboard():
    builder = InlineKeyboardBuilder()
    for section in tb.THERAPY["sections"]:
        builder.button(text=f"{section['order']}. {section['title']}", callback_data=f"th:section:{section['id']}")
    builder.adjust(1)
    return builder.as_markup()


def get_section_keyboard(section_id: str):
    section = get_section(section_id)
    builder = InlineKeyboardBuilder()
    for topic in section["topics"]:
        builder.button(text=f"{topic['id']} {topic['title']}", callback_data=f"th:topic:{section_id}:{topic['id']}")
    builder.adjust(1)

    content_builder = InlineKeyboardBuilder()
    for ctype, label in SECTION_CONTENT_TYPES:
        content_builder.button(text=label, callback_data=f"th:section_content:{section_id}:{ctype}")
    content_builder.adjust(2)
    builder.attach(content_builder)

    builder.row(InlineKeyboardButton(text="🔙 К разделам", callback_data="th:menu"))
    return builder.as_markup()


def get_topic_keyboard(section_id: str, topic_id: str):
    builder = InlineKeyboardBuilder()
    for ctype, label in TOPIC_CONTENT_TYPES:
        builder.button(text=label, callback_data=f"th:content:{section_id}:{topic_id}:{ctype}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 К разделу", callback_data=f"th:section:{section_id}"))
    return builder.as_markup()


def get_back_keyboard(back_callback: str):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback))
    return builder.as_markup()


# ==================== text rendering ====================

def get_therapy_menu_text() -> str:
    lines = ["🏥 <b>Терапия</b>", "", "Выбери раздел:"]
    return "\n".join(lines)


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
    lines = [
        f"🏥 {esc(section['title'])}",
        f"📄 <b>{esc(topic['id'])} {esc(topic['full_title'])}</b>",
        tb.DIVIDER,
        f"📖 Теория: {status_label(topic['theory']['status'])}",
        f"📝 Тесты: {status_label(topic['tests']['status'])}",
    ]
    return "\n".join(lines)


def _status_screen(title: str, status: str, plan_note: str, breadcrumb: str) -> str:
    lines = [
        breadcrumb,
        f"<b>{esc(title)}</b>",
        tb.DIVIDER,
        f"Статус: {status_label(status)}",
        "",
        f"<i>{esc(plan_note)}</i>",
        "",
        "Материалы по этому пункту ещё не добавлены в бота — они появятся здесь, как только будут перенесены из исходников кафедры.",
    ]
    return "\n".join(lines)


def render_topic_content(section_id: str, topic_id: str, ctype: str) -> str:
    section = get_section(section_id)
    topic = get_topic(section_id, topic_id)
    label = dict(TOPIC_CONTENT_TYPES)[ctype]
    block = topic[ctype]
    breadcrumb = f"🏥 {esc(section['title'])} → {esc(topic['id'])} {esc(topic['title'])}"

    if ctype == "theory" and block["material"]:
        lines = [breadcrumb, f"📖 <b>{esc(topic['full_title'])}</b>", tb.DIVIDER]
        for block_item in block["material"]:
            lines.append(block_item)
            lines.append("")
        return "\n".join(lines).strip()

    if ctype == "tests" and block["questions"]:
        lines = [breadcrumb, f"📝 <b>Тесты: {esc(topic['full_title'])}</b>", tb.DIVIDER]
        for i, q in enumerate(block["questions"], 1):
            lines.append(f"{i}. {q}")
        return "\n".join(lines)

    return _status_screen(f"{label}: {topic['full_title']}", block["status"], block["plan_note"], breadcrumb)


def render_section_content(section_id: str, ctype: str) -> str:
    section = get_section(section_id)
    label = dict(SECTION_CONTENT_TYPES)[ctype]
    block = section[ctype]
    breadcrumb = f"🏥 {esc(section['title'])}"

    content_list = block.get("material") or block.get("questions") or []
    table = block.get("table")

    if content_list:
        lines = [breadcrumb, f"{label}", tb.DIVIDER]
        for item in content_list:
            lines.append(str(item))
            lines.append("")
        return "\n".join(lines).strip()

    if table:
        lines = [breadcrumb, f"{label}", tb.DIVIDER, str(table)]
        return "\n".join(lines)

    return _status_screen(f"{label}: {section['title']}", block["status"], block["plan_note"], breadcrumb)


# ==================== handlers ====================

@router.callback_query(F.data == "th:menu")
async def cb_therapy_menu(callback: CallbackQuery):
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        get_therapy_menu_text(),
        parse_mode="HTML",
        reply_markup=get_therapy_menu_keyboard(),
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
        callback.message,
        get_section_text(section_id),
        parse_mode="HTML",
        reply_markup=get_section_keyboard(section_id),
    )


@router.callback_query(F.data.startswith("th:topic:"))
async def cb_therapy_topic(callback: CallbackQuery):
    _, _, section_id, topic_id = callback.data.split(":")
    topic = get_topic(section_id, topic_id)
    if not topic:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        get_topic_text(section_id, topic_id),
        parse_mode="HTML",
        reply_markup=get_topic_keyboard(section_id, topic_id),
    )


@router.callback_query(F.data.startswith("th:content:"))
async def cb_therapy_content(callback: CallbackQuery):
    _, _, section_id, topic_id, ctype = callback.data.split(":")
    topic = get_topic(section_id, topic_id)
    if not topic or ctype not in dict(TOPIC_CONTENT_TYPES):
        await callback.answer("Материал не найден", show_alert=True)
        return
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        render_topic_content(section_id, topic_id, ctype),
        parse_mode="HTML",
        reply_markup=get_back_keyboard(f"th:topic:{section_id}:{topic_id}"),
    )


@router.callback_query(F.data.startswith("th:section_content:"))
async def cb_therapy_section_content(callback: CallbackQuery):
    _, _, section_id, ctype = callback.data.split(":")
    section = get_section(section_id)
    if not section or ctype not in dict(SECTION_CONTENT_TYPES):
        await callback.answer("Материал не найден", show_alert=True)
        return
    await callback.answer()
    await tb.safe_edit_text(
        callback.message,
        render_section_content(section_id, ctype),
        parse_mode="HTML",
        reply_markup=get_back_keyboard(f"th:section:{section_id}"),
    )
