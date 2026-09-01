"""Загрузка контента бота из JSON-файлов репозитория — единая точка входа, по образцу
vmeda-biology-bot/repositories/knowledge.py. Пока в боте один предмет (Терапия), поэтому файл
короткий, но структура (модуль сам открывает JSON, telegram_bot.py просто реэкспортирует имя)
сохранена — так добавление следующего предмета/раздела не потребует менять сам паттерн загрузки,
только дописать ещё один open()/json.load() здесь.

Путь — относительный, как и в исходном боте: модуль должен импортироваться с корнем репозитория
в качестве текущей рабочей директории (см. CLAUDE.md).

validate_therapy() запускается сразу после загрузки и падает с понятным ValueError при первой же
структурной проблеме (отсутствующее поле, mcq.correct_index вне диапазона, несовпадение числа
колонок сравнительной таблицы, дублирующийся id) — лучше сломать деплой на старте с ясным
сообщением, чем дать боту упасть на рендере конкретного экрана посреди разговора с студентом.
Проверяет только ФОРМУ данных (то, что в типизированной схеме дал бы sanity-check типов), а не
медицинскую корректность содержания — за неё по-прежнему отвечает автор контента."""
import json


def _require_keys(where: str, obj: dict, keys) -> None:
    missing = set(keys) - obj.keys()
    if missing:
        raise ValueError(f"{where}: отсутствуют поля {sorted(missing)}")


def _validate_prose_block(where: str, block: dict, list_field: str = "material") -> None:
    _require_keys(where, block, {"status", "plan_note", list_field})
    if not isinstance(block[list_field], list):
        raise ValueError(f"{where}: '{list_field}' должно быть списком")


def _validate_mcq_question(where: str, q: dict) -> None:
    _require_keys(where, q, {"question", "options", "correct_index"})
    options = q["options"]
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError(f"{where}: 'options' должно быть списком минимум из 2 вариантов")
    idx = q["correct_index"]
    if not isinstance(idx, int) or not (0 <= idx < len(options)):
        raise ValueError(f"{where}: 'correct_index' вне диапазона options (0..{len(options) - 1})")


def _validate_tests_block(where: str, block: dict) -> None:
    _require_keys(where, block, {"status", "plan_note", "mcq", "self_check"})
    if not isinstance(block["mcq"], list) or not isinstance(block["self_check"], list):
        raise ValueError(f"{where}: 'mcq'/'self_check' должны быть списками")
    for i, q in enumerate(block["mcq"]):
        _validate_mcq_question(f"{where}.mcq[{i}]", q)


def _validate_comparison_table_block(where: str, block: dict) -> None:
    _require_keys(where, block, {"status", "plan_note", "table"})
    table = block["table"]
    if table is None:
        return
    if not isinstance(table, dict):
        raise ValueError(f"{where}: 'table' должно быть null или объектом {{caption, headers, rows}}")
    headers = table.get("headers", [])
    for i, row in enumerate(table.get("rows", [])):
        values = row.get("values", [])
        if len(values) != len(headers):
            raise ValueError(
                f"{where}: rows[{i}] содержит {len(values)} значений, а headers — {len(headers)}"
            )


def _validate_exam_questions_block(where: str, block: dict) -> None:
    _require_keys(where, block, {"status", "plan_note", "items"})
    if not isinstance(block["items"], list):
        raise ValueError(f"{where}: 'items' должно быть списком")
    for i, item in enumerate(block["items"]):
        if "question" not in item:
            raise ValueError(f"{where}.items[{i}]: отсутствует 'question'")


def _validate_topic(section_id: str, topic: dict, seen_topic_ids: set) -> None:
    _require_keys(f"section '{section_id}' topic", topic, {"id", "order", "title", "full_title", "theory", "tests"})
    tid = topic["id"]
    if tid in seen_topic_ids:
        raise ValueError(f"section '{section_id}': повторяющийся topic id '{tid}'")
    seen_topic_ids.add(tid)
    _validate_prose_block(f"{section_id}:{tid}.theory", topic["theory"])
    _validate_tests_block(f"{section_id}:{tid}.tests", topic["tests"])


def validate_therapy(data: dict) -> None:
    if not isinstance(data.get("sections"), list) or not data["sections"]:
        raise ValueError("therapy.json: 'sections' должно быть непустым списком")

    seen_section_ids = set()
    for section in data["sections"]:
        _require_keys("section", section, {
            "id", "order", "title", "short_title", "topics", "anatomy_overview",
            "comparison_table", "boundary_control", "pharma_overview", "exam_questions", "manipulations",
        })
        sid = section["id"]
        if sid in seen_section_ids:
            raise ValueError(f"повторяющийся section id '{sid}'")
        seen_section_ids.add(sid)

        _validate_prose_block(f"{sid}.anatomy_overview", section["anatomy_overview"])
        _validate_comparison_table_block(f"{sid}.comparison_table", section["comparison_table"])
        _validate_tests_block(f"{sid}.boundary_control", section["boundary_control"])
        _validate_prose_block(f"{sid}.pharma_overview", section["pharma_overview"])
        _validate_exam_questions_block(f"{sid}.exam_questions", section["exam_questions"])
        _validate_prose_block(f"{sid}.manipulations", section["manipulations"])

        if not isinstance(section["topics"], list) or not section["topics"]:
            raise ValueError(f"section '{sid}': 'topics' должно быть непустым списком")
        seen_topic_ids = set()
        for topic in section["topics"]:
            _validate_topic(sid, topic, seen_topic_ids)


with open("therapy.json", "r", encoding="utf-8") as f:
    THERAPY = json.load(f)
validate_therapy(THERAPY)
