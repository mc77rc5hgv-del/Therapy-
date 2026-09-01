# -*- coding: utf-8 -*-
"""repositories/knowledge.validate_therapy() — падает с понятным ValueError на первой же
структурной проблеме в therapy.json (отсутствующее поле, mcq.correct_index вне диапазона,
несовпадение числа колонок сравнительной таблицы, дублирующийся id раздела/темы), вместо того
чтобы дать боту упасть на рендере конкретного экрана посреди разговора со студентом. Строится
каждый раз из МИНИМАЛЬНОГО валидного скелета (через copy.deepcopy), а не общего therapy.json —
так тест независим от того, сколько реальных разделов/тем сейчас в датасете."""
import copy
from _bootstrap import tb  # noqa: F401 — гарантирует, что реальный therapy.json уже прошёл validate_therapy()

from repositories.knowledge import validate_therapy

MINIMAL_VALID = {
    "sections": [
        {
            "id": "s1", "order": 1, "title": "Раздел 1", "short_title": "Р1",
            "anatomy_overview": {"status": "planned", "plan_note": "x", "material": []},
            "comparison_table": {"status": "planned", "plan_note": "x", "table": None},
            "boundary_control": {"status": "planned", "plan_note": "x", "mcq": [], "self_check": []},
            "pharma_overview": {"status": "planned", "plan_note": "x", "material": []},
            "exam_questions": {"status": "planned", "plan_note": "x", "items": []},
            "manipulations": {"status": "planned", "plan_note": "x", "material": []},
            "topics": [
                {
                    "id": "1.1", "order": 1, "title": "Тема 1", "full_title": "Тема 1 полностью",
                    "theory": {"status": "planned", "plan_note": "x", "material": []},
                    "tests": {"status": "planned", "plan_note": "x", "mcq": [], "self_check": []},
                },
            ],
        },
    ],
}


def fresh():
    return copy.deepcopy(MINIMAL_VALID)


def expect_invalid(data, needle: str = ""):
    try:
        validate_therapy(data)
    except ValueError as e:
        if needle:
            assert needle in str(e), (needle, str(e))
        return
    raise AssertionError("ожидался ValueError, но validate_therapy() не упала")


def run():
    validate_therapy(tb.THERAPY)
    print("OK реальный therapy.json проходит валидацию")

    validate_therapy(fresh())
    print("OK минимальный валидный скелет проходит валидацию")

    d = fresh()
    d["sections"] = []
    expect_invalid(d, "sections")

    d = fresh()
    del d["sections"][0]["title"]
    expect_invalid(d, "title")

    d = fresh()
    d["sections"].append(copy.deepcopy(d["sections"][0]))
    expect_invalid(d, "повторяющийся section id")

    d = fresh()
    d["sections"][0]["topics"].append(copy.deepcopy(d["sections"][0]["topics"][0]))
    expect_invalid(d, "повторяющийся topic id")

    d = fresh()
    d["sections"][0]["topics"] = []
    expect_invalid(d, "topics")

    d = fresh()
    d["sections"][0]["topics"][0]["tests"]["mcq"] = [
        {"question": "?", "options": ["a", "b"], "correct_index": 5},
    ]
    expect_invalid(d, "correct_index")

    d = fresh()
    d["sections"][0]["topics"][0]["tests"]["mcq"] = [
        {"question": "?", "options": ["только один вариант"], "correct_index": 0},
    ]
    expect_invalid(d, "options")

    d = fresh()
    d["sections"][0]["boundary_control"]["mcq"] = [{"question": "?", "options": ["a", "b"]}]  # без correct_index
    expect_invalid(d, "correct_index")

    d = fresh()
    d["sections"][0]["comparison_table"]["table"] = {
        "caption": "x", "headers": ["A", "B"], "rows": [{"aspect": "x", "values": ["только одно"]}],
    }
    expect_invalid(d, "rows[0]")

    d = fresh()
    d["sections"][0]["comparison_table"]["table"] = {
        "caption": "x", "headers": ["A", "B"], "rows": [{"aspect": "x", "values": ["a", "b"]}],
    }
    validate_therapy(d)  # совпадающее число колонок — валидно

    d = fresh()
    del d["sections"][0]["exam_questions"]["items"][:]
    d["sections"][0]["exam_questions"]["items"].append({"answer": "без вопроса"})
    expect_invalid(d, "question")

    print("OK все проверки на битые данные корректно ловят ошибку (с понятным сообщением)")
    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    run()
