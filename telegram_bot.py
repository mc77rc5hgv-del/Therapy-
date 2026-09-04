"""Telegram-бот «Терапия» для подготовки к экзамену по терапии — построен по образцу
vmeda-biology-bot (тот же аiogram 3.7.0, тот же паттерн: repositories/knowledge.py грузит JSON
контент один раз при импорте, handlers/*.py — отдельные Router'ы за предмет/раздел, подключаемые
через dp.include_router() в конце файла, stats — module-level dict, сохраняемый в STATS_DIR).

Отличие от vmeda-biology-bot: здесь пока один предмет (Терапия), поэтому у него нет отдельного
пункта в "главном меню" — раздел сам выполняет роль главного меню (см. handlers/therapy.py).
Никакой реферальной системы/платных подписок/AI-модуля пока нет — раздел статистики и админ-панели
сознательно минимальны, это MVP-скелет архитектуры под план курса, а не полнофункциональная копия
vmeda-biology-bot. Расширять по мере необходимости, тем же паттерном (Router в handlers/, JSON в
repositories/knowledge.py, dp.include_router() в конце файла — см. CLAUDE.md)."""
import asyncio
import copy
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand, BotCommandScopeChat, BotCommandScopeDefault, CallbackQuery, InlineKeyboardButton, Message,
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.utils.keyboard import InlineKeyboardBuilder

from repositories import knowledge

# Тот же alias-приём, что в vmeda-biology-bot: Railway стартует файл напрямую
# (python3 telegram_bot.py), поэтому Python грузит его как "__main__" — без этой строки
# `import telegram_bot as tb` внутри handlers/*.py запустил бы файл ВТОРОЙ раз с нуля.
sys.modules.setdefault("telegram_bot", sys.modules[__name__])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Set it as an environment variable (e.g. Railway → Variables) — "
        "never hardcode the token in source code."
    )

# Список Telegram user_id админов — через переменную окружения (запасных/захардкоженных ID из
# vmeda-biology-bot здесь нет и быть не должно, это другой бот и другие люди). Пример:
# ADMIN_IDS=123456789,987654321
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

STATS_DIR = os.getenv("STATS_DIR", ".")
STATS_FILE = os.path.join(STATS_DIR, "stats.json")

# Россия с 2014 года не переходит на летнее/зимнее время — фиксированный offset вместо
# zoneinfo("Europe/Moscow"), тот же приём и по той же причине, что в vmeda-biology-bot.
APP_TIMEZONE = timezone(timedelta(hours=3), name="MSK")


def local_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def local_today() -> date:
    return local_now().date()


DIVIDER = "━━━━━━━━━━━━━━"

# ==================== ЗАГРУЗКА ДАННЫХ ====================
THERAPY = knowledge.THERAPY

# ==================== СТАТИСТИКА (СОХРАНЯЕТСЯ НА ДИСК) ====================
def load_stats() -> dict:
    os.makedirs(STATS_DIR, exist_ok=True)
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["total_users"] = set(data.get("total_users", []))
            data.setdefault("start_count", 0)
            data.setdefault("user_names", {})
            data.setdefault("user_username", {})
            data.setdefault("therapy_progress", {})
            data.setdefault("therapy_favorites", {})
            data.setdefault("broadcast_count", 0)
            return data
        except (json.JSONDecodeError, OSError):
            logger.exception("Не удалось прочитать %s, статистика будет создана заново", STATS_FILE)
    return {
        "total_users": set(),
        "start_count": 0,
        "user_names": {},
        "user_username": {},
        "therapy_progress": {},
        "therapy_favorites": {},
        "broadcast_count": 0,
    }


_stats_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stats-writer")


def _write_stats_file(data: dict) -> None:
    tmp_path = f"{STATS_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATS_FILE)


def _log_stats_write_result(future) -> None:
    exc = future.exception()
    if exc is not None:
        logger.error("Не удалось сохранить статистику: %s", exc)


def save_stats() -> None:
    data = copy.deepcopy(stats)
    data["total_users"] = list(data["total_users"])
    future = _stats_executor.submit(_write_stats_file, data)
    future.add_done_callback(_log_stats_write_result)


stats = load_stats()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ==================== ВСПОМОГАТЕЛЬНОЕ ====================
async def safe_edit_text(message, text, **kwargs) -> None:
    """Как edit_text, но если сообщение больше не текстовое, удаляет его и отправляет новое
    вместо падения с ошибкой — тот же helper, что в vmeda-biology-bot."""
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest:
        await message.delete()
        await message.answer(text, **kwargs)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Заполняется в main() через bot.get_me() перед стартом polling — нужно только для того, чтобы
# показать админу готовую ссылку на тему (см. get_admin_menu_text()); до первого запуска main()
# (например, в тестах, которые не поднимают polling) остаётся пустой строкой — build_deep_link_url()
# отдаёт заглушку вместо реального t.me/... в этом случае, а не падает.
BOT_USERNAME: str = ""


def build_deep_link_url(payload: str) -> str:
    if not BOT_USERNAME:
        return f"(имя бота станет известно после первого запуска; payload: {payload})"
    return f"https://t.me/{BOT_USERNAME}?start={payload}"


# ==================== ГЛАВНОЕ МЕНЮ ====================
# get_main_menu() ссылается на глобальное имя therapy_handlers, которое появится в этом модуле
# чуть ниже (после dp = Dispatcher()) — тело функции выполняется только при вызове (уже после
# полной загрузки файла), поэтому порядок определений здесь не важен, как и в vmeda-biology-bot.
def get_main_menu(user_id: int):
    return therapy_handlers.get_therapy_menu_keyboard(user_id)


def get_main_menu_text() -> str:
    return "👋 <b>Бот «Терапия» (ВМедА)</b>\n\nВыбери раздел дисциплины:"


async def _open_deep_link(message: Message, user_id: int, deep_link: tuple) -> None:
    """Отправляет экран, на который ведёт распознанный /start-payload (см.
    therapy_handlers.resolve_deep_link) — тему сразу с отметкой "открыта" в прогрессе, раздел без
    неё (открытие темы, а не самого раздела, — то, что реально считается прогрессом)."""
    kind, section_id, topic_id = deep_link
    if kind == "topic":
        therapy_handlers.mark_topic_opened(user_id, section_id, topic_id)
        await message.answer(
            therapy_handlers.get_topic_text(section_id, topic_id),
            parse_mode="HTML",
            reply_markup=therapy_handlers.get_topic_keyboard(section_id, topic_id, user_id),
        )
    else:  # kind == "section"
        await message.answer(
            therapy_handlers.get_section_text(section_id),
            parse_mode="HTML",
            reply_markup=therapy_handlers.get_section_keyboard(section_id),
        )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    stats["total_users"].add(user_id)
    stats["start_count"] += 1
    if message.from_user.username:
        stats["user_username"][str(user_id)] = message.from_user.username
    stats["user_names"][str(user_id)] = message.from_user.full_name
    save_stats()

    payload_parts = message.text.split(maxsplit=1)
    deep_link = therapy_handlers.resolve_deep_link(payload_parts[1]) if len(payload_parts) > 1 else None
    if deep_link:
        await _open_deep_link(message, user_id, deep_link)
        return

    await message.answer(
        get_main_menu_text(),
        parse_mode="HTML",
        reply_markup=get_main_menu(user_id),
    )


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(get_main_menu_text(), parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id))


@dp.message(Command("progress"))
async def cmd_progress(message: Message):
    await message.answer(
        therapy_handlers.get_therapy_progress_text(message.from_user.id),
        parse_mode="HTML",
        reply_markup=therapy_handlers.get_back_keyboard("th:menu"),
    )


@dp.message(Command("search"))
async def cmd_search(message: Message):
    ADMIN_BROADCAST_PENDING.discard(message.from_user.id)  # взаимоисключающие текстовые ожидания
    TH_SEARCH_PENDING.add(message.from_user.id)
    await message.answer(
        "🔎 Напиши слово или фразу для поиска по разделам и темам «Терапии».",
        reply_markup=therapy_handlers.get_back_keyboard("th:menu"),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    lines = [
        "ℹ️ <b>Как пользоваться ботом</b>",
        DIVIDER,
        "/menu — открыть главное меню разделов",
        "/search — поиск по разделам и темам",
        "/progress — мой прогресс",
        "",
        "🎲 «Случайный вопрос» на главном меню — тренировка сразу по всей базе.",
        "⭐ На экране темы можно добавить её в избранное.",
        "▶️ «Продолжить» на главном меню возвращает к последней открытой теме.",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id))


@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        get_main_menu_text(),
        parse_mode="HTML",
        reply_markup=get_main_menu(callback.from_user.id),
    )


# ==================== ПОИСК ПО ТЕРАПИИ ====================
# Ожидающие ввода поискового запроса user_id — тот же приём, что OH_SEARCH_PENDING в
# vmeda-biology-bot (plain set, а не многошаговый dict вроде ADMIN_PENDING, потому что здесь
# ровно один шаг: получить текст запроса). Сам text-хендлер намеренно живёт здесь, в
# telegram_bot.py, а не в handlers/therapy.py — если в боте когда-нибудь появится безусловный
# catch-all для текста (по аналогии с handle_keyword_search в vmeda-biology-bot), хендлеры,
# зарегистрированные позже через dp.include_router(), окажутся ПОСЛЕ него в цепочке диспетчера и
# просто не получат управление. Регистрируя поиск здесь и раньше катча-всего (которого пока нет,
# но который не должен незаметно всё сломать, если появится), эта проблема исключена заранее —
# см. handlers/operative_surgery.py в vmeda-biology-bot, тот же аргумент.
TH_SEARCH_PENDING: set = set()


@dp.message(F.text)
async def handle_therapy_search_query(message: Message):
    if message.from_user.id not in TH_SEARCH_PENDING:
        raise SkipHandler
    TH_SEARCH_PENDING.discard(message.from_user.id)
    query = message.text.strip()
    results = therapy_handlers.search_therapy(query)
    await message.answer(
        therapy_handlers.get_search_results_text(query, results),
        parse_mode="HTML",
        reply_markup=therapy_handlers.get_search_results_keyboard(results),
    )


# ==================== АДМИН-ПАНЕЛЬ (минимальная) ====================
def get_admin_menu_text() -> str:
    lines = [
        "🛠 <b>Админ-панель «Терапия»</b>",
        DIVIDER,
        f"Пользователей: {len(stats['total_users'])}",
        f"Запусков /start: {stats['start_count']}",
        "",
        "Разделов курса: " + str(len(THERAPY["sections"])),
        "Тем: " + str(sum(len(s["topics"]) for s in THERAPY["sections"])),
        "",
        "🔗 Ссылка на тему для рассылки: "
        + build_deep_link_url(therapy_handlers.build_topic_deep_link_payload("<sid>", "<tid>")),
    ]
    return "\n".join(lines)


def get_admin_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Что не хватает", callback_data="admin:coverage"))
    builder.row(InlineKeyboardButton(text="📣 Разослать всем", callback_data="admin:broadcast_prompt"))
    return builder.as_markup()


@dp.message(F.text == "/admin")
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(get_admin_menu_text(), parse_mode="HTML", reply_markup=get_admin_menu_keyboard())


@dp.callback_query(F.data == "admin:coverage")
async def cb_admin_coverage(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu"))
    await safe_edit_text(
        callback.message,
        therapy_handlers.get_admin_coverage_text(),
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "admin:menu")
async def cb_admin_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    await safe_edit_text(
        callback.message, get_admin_menu_text(), parse_mode="HTML", reply_markup=get_admin_menu_keyboard(),
    )


# Рассылка всем пользователям — тот же двухшаговый приём, что ADMIN_PENDING в vmeda-biology-bot
# (нажал кнопку -> следующее сообщение админа берётся как текст рассылки), но упрощён до plain
# set[user_id], потому что здесь всего одно действие, а не целый switch по action — тот же выбор,
# что уже сделан для TH_SEARCH_PENDING выше.
ADMIN_BROADCAST_PENDING: set = set()


@dp.callback_query(F.data == "admin:broadcast_prompt")
async def cb_admin_broadcast_prompt(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    TH_SEARCH_PENDING.discard(callback.from_user.id)  # взаимоисключающие текстовые ожидания
    ADMIN_BROADCAST_PENDING.add(callback.from_user.id)
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin:menu"))
    await safe_edit_text(
        callback.message,
        "📣 Пришли текст, который нужно разослать всем пользователям бота.",
        reply_markup=builder.as_markup(),
    )


async def _broadcast_to_all(text: str) -> tuple:
    """Рассылает text каждому user_id из stats["total_users"]. Небольшая пауза между отправками —
    не throttling-защита в полном смысле (для реального масштаба нужна очередь/лимитер), а просто
    вежливость к Bot API при рассылке уже не единицам, а десяткам/сотням пользователей."""
    success = 0
    failed = 0
    for user_id in list(stats["total_users"]):
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            success += 1
        except TelegramForbiddenError:
            failed += 1
        except Exception:
            logger.exception("Не удалось разослать сообщение %s", user_id)
            failed += 1
        await asyncio.sleep(0.05)
    return success, failed


@dp.message(F.text)
async def handle_admin_broadcast_text(message: Message):
    admin_id = message.from_user.id
    if not is_admin(admin_id) or admin_id not in ADMIN_BROADCAST_PENDING:
        raise SkipHandler
    ADMIN_BROADCAST_PENDING.discard(admin_id)
    success, failed = await _broadcast_to_all(message.text)
    stats["broadcast_count"] = stats.get("broadcast_count", 0) + 1
    save_stats()
    await message.answer(f"📣 Разослано: {success} успешно, {failed} не доставлено.", parse_mode="HTML")


# ==================== ПОДКЛЮЧЕНИЕ РОУТЕРОВ ПРЕДМЕТОВ ====================
# handlers/therapy.py импортирует telegram_bot как tb — тот же приём, что vmeda-biology-bot
# использует для handlers/physiology.py и др. (поздно подключаемый модуль, использующий
# DIVIDER/safe_edit_text/stats, уже определённые выше в этом файле), поэтому импорт роутера идёт
# именно здесь, после того как все нужные ему имена уже существуют в этом модуле.
from handlers import therapy as therapy_handlers  # noqa: E402

dp.include_router(therapy_handlers.router)


# ==================== ЗАПУСК ====================
async def setup_bot_commands() -> None:
    default_commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="menu", description="Главное меню разделов"),
        BotCommand(command="search", description="Поиск по разделам и темам"),
        BotCommand(command="progress", description="Мой прогресс"),
        BotCommand(command="help", description="Как пользоваться ботом"),
    ]
    await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())

    admin_commands = default_commands + [BotCommand(command="admin", description="Админ-панель")]
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            logger.exception("Не удалось установить админ-команды для %s", admin_id)


async def main():
    global BOT_USERNAME
    logger.info("Бот запускается...")
    logger.info("Загружена статистика: %d пользователей", len(stats["total_users"]))
    me = await bot.get_me()
    BOT_USERNAME = me.username
    await setup_bot_commands()
    try:
        await dp.start_polling(bot)
    finally:
        _stats_executor.shutdown(wait=True)


if __name__ == "__main__":
    asyncio.run(main())
