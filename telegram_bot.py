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
from aiogram.filters import CommandStart
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

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
            return data
        except (json.JSONDecodeError, OSError):
            logger.exception("Не удалось прочитать %s, статистика будет создана заново", STATS_FILE)
    return {
        "total_users": set(),
        "start_count": 0,
        "user_names": {},
        "user_username": {},
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


# ==================== ГЛАВНОЕ МЕНЮ ====================
# get_main_menu() ссылается на глобальное имя therapy_handlers, которое появится в этом модуле
# чуть ниже (после dp = Dispatcher()) — тело функции выполняется только при вызове (уже после
# полной загрузки файла), поэтому порядок определений здесь не важен, как и в vmeda-biology-bot.
def get_main_menu():
    return therapy_handlers.get_therapy_menu_keyboard()


def get_main_menu_text() -> str:
    return "👋 <b>Бот «Терапия» (ВМедА)</b>\n\nВыбери раздел дисциплины:"


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    stats["total_users"].add(user_id)
    stats["start_count"] += 1
    if message.from_user.username:
        stats["user_username"][str(user_id)] = message.from_user.username
    stats["user_names"][str(user_id)] = message.from_user.full_name
    save_stats()

    await message.answer(
        get_main_menu_text(),
        parse_mode="HTML",
        reply_markup=get_main_menu(),
    )


@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        get_main_menu_text(),
        parse_mode="HTML",
        reply_markup=get_main_menu(),
    )


# ==================== АДМИН-ПАНЕЛЬ (минимальная) ====================
@dp.message(F.text == "/admin")
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    lines = [
        "🛠 <b>Админ-панель «Терапия»</b>",
        DIVIDER,
        f"Пользователей: {len(stats['total_users'])}",
        f"Запусков /start: {stats['start_count']}",
        "",
        "Разделов курса: " + str(len(THERAPY["sections"])),
        "Тем: " + str(sum(len(s["topics"]) for s in THERAPY["sections"])),
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


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
    ]
    await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())

    admin_commands = default_commands + [BotCommand(command="admin", description="Админ-панель")]
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            logger.exception("Не удалось установить админ-команды для %s", admin_id)


async def main():
    logger.info("Бот запускается...")
    logger.info("Загружена статистика: %d пользователей", len(stats["total_users"]))
    await setup_bot_commands()
    try:
        await dp.start_polling(bot)
    finally:
        _stats_executor.shutdown(wait=True)


if __name__ == "__main__":
    asyncio.run(main())
