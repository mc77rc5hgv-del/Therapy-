# -*- coding: utf-8 -*-
"""Навигация по разделу «Терапия»: главное меню -> раздел -> тема -> теория/тесты, и
раздел -> секционные материалы (обзор анатомии/сравнительная таблица/рубежный контроль/
обзор фармы/экз.вопросы/манипуляции). Проверяет, что каждый экран этого дерева рендерится без
исключений для КАЖДОГО раздела/темы в therapy.json (а не только для одного показательного пути),
что весь HTML сбалансирован и укладывается в лимит Telegram (4096 символов), и что
"честная заглушка" (_status_screen) действительно показывается для пустых material/questions/
table, а не выдуманный контент."""
import asyncio
from _bootstrap import tb
from html.parser import HTMLParser

from handlers import therapy as th

ADMIN_ID = 1


class HtmlBalanceChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.problems = []

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(tag)
        else:
            self.stack.pop()


def check_html(text: str) -> None:
    c = HtmlBalanceChecker()
    c.feed(text)
    assert not c.stack and not c.problems, (text[:300], c.stack, c.problems)
    assert len(text) <= 4096, len(text)


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.username = "tester"
        self.full_name = "Test User"


class FakeMsg:
    def __init__(self):
        self.deleted = False
        self.sent_texts = []

    async def delete(self):
        self.deleted = True

    async def answer(self, text, **kwargs):
        self.sent_texts.append((text, kwargs.get("reply_markup")))
        return self

    async def edit_text(self, text, **kwargs):
        self.sent_texts.append((text, kwargs.get("reply_markup")))
        return self


class FakeCB:
    def __init__(self, data, uid=ADMIN_ID):
        self.data = data
        self.from_user = FakeUser(uid)
        self.message = FakeMsg()
        self._answers = []

    async def answer(self, text=None, show_alert=False):
        self._answers.append((text, show_alert))


def kb_data(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


async def run():
    # /start -> главное меню = список разделов
    msg = FakeMsg()
    start_msg = type("M", (), {"from_user": FakeUser(ADMIN_ID), "text": "/start", "answer": msg.answer})()
    await tb.cmd_start(start_msg)
    text, markup = msg.sent_texts[-1]
    check_html(text)
    section_ids = [d.split(":")[2] for d in kb_data(markup) if d.startswith("th:section:")]
    assert section_ids == [s["id"] for s in tb.THERAPY["sections"]], section_ids
    print(f"OK главное меню: {len(section_ids)} раздел(ов)")

    # th:menu callback
    cb = FakeCB("th:menu")
    await th.cb_therapy_menu(cb)
    text, markup = cb.message.sent_texts[-1]
    check_html(text)
    print("OK th:menu")

    for section in tb.THERAPY["sections"]:
        sid = section["id"]
        cb = FakeCB(f"th:section:{sid}")
        await th.cb_therapy_section(cb)
        text, markup = cb.message.sent_texts[-1]
        check_html(text)
        data = kb_data(markup)
        assert "th:menu" in data
        topic_ids = [d.split(":")[3] for d in data if d.startswith("th:topic:")]
        assert topic_ids == [t["id"] for t in section["topics"]], (sid, topic_ids)
        section_ctypes = sorted(d.split(":")[3] for d in data if d.startswith("th:section_content:"))
        assert section_ctypes == sorted(dict(th.SECTION_CONTENT_TYPES).keys()), (sid, section_ctypes)
        print(f"OK раздел {sid}: {len(topic_ids)} тем(а/ы), {len(section_ctypes)} секционных блоков")

        # неизвестный раздел -> alert, без падения
        cb_bad = FakeCB("th:section:no_such_section")
        await th.cb_therapy_section(cb_bad)
        assert cb_bad._answers and cb_bad._answers[0][1] is True
        assert not cb_bad.message.sent_texts

        for ctype, _label in th.SECTION_CONTENT_TYPES:
            cb = FakeCB(f"th:section_content:{sid}:{ctype}")
            await th.cb_therapy_section_content(cb)
            text, markup = cb.message.sent_texts[-1]
            check_html(text)
            block = section[ctype]
            has_content = bool(block.get("material") or block.get("questions") or block.get("table"))
            if not has_content:
                # честная заглушка: статус + исходная пометка плана, без придуманного текста
                assert th.status_label(block["status"]) in text or th.esc(block["status"]) in text, text
                assert th.esc(block["plan_note"]) in text, (ctype, text)
            data = kb_data(markup)
            # get_back_keyboard добавляет «🏠 Меню» на любом экране глубже главного
            assert data == [f"th:section:{sid}", "th:menu"], data
        print(f"OK секционные блоки раздела {sid} отрендерены (заглушки — честные, без контента)")

        topic_ids_in_order = [t["id"] for t in section["topics"]]
        for i, topic in enumerate(section["topics"]):
            tid = topic["id"]
            cb = FakeCB(f"th:topic:{sid}:{tid}")
            await th.cb_therapy_topic(cb)
            text, markup = cb.message.sent_texts[-1]
            check_html(text)
            data = kb_data(markup)
            assert f"th:section:{sid}" in data
            assert "th:menu" in data
            assert f"th:fav_toggle:{sid}:{tid}" in data
            assert any(d.startswith(f"th:content:{sid}:{tid}:") for d in data), data
            # карусель тем: есть "пред." везде кроме первой темы раздела, "след." везде кроме последней
            has_prev = any(d == f"th:topic:{sid}:{topic_ids_in_order[i - 1]}" for d in data) if i > 0 else None
            has_next = (
                any(d == f"th:topic:{sid}:{topic_ids_in_order[i + 1]}" for d in data)
                if i < len(topic_ids_in_order) - 1 else None
            )
            if i > 0:
                assert has_prev, (sid, tid, data)
            if i < len(topic_ids_in_order) - 1:
                assert has_next, (sid, tid, data)

            for ctype, _label in th.TOPIC_CONTENT_TYPES:
                cb = FakeCB(f"th:content:{sid}:{tid}:{ctype}")
                await th.cb_therapy_content(cb)
                text, markup = cb.message.sent_texts[-1]
                check_html(text)
                block = topic[ctype]
                has_content = bool(block.get("material") or block.get("questions"))
                if not has_content:
                    assert th.esc(block["plan_note"]) in text, (sid, tid, ctype, text)
                data = kb_data(markup)
                assert data == [f"th:topic:{sid}:{tid}", "th:menu"], data
        print(f"OK темы раздела {sid}: {len(section['topics'])} шт., теория/тесты/карусель/избранное отрендерены")

    # неизвестная тема/контент -> alert, без падения
    cb_bad = FakeCB(f"th:topic:{tb.THERAPY['sections'][0]['id']}:no_such_topic")
    await th.cb_therapy_topic(cb_bad)
    assert cb_bad._answers and cb_bad._answers[0][1] is True

    cb_bad = FakeCB(f"th:content:{tb.THERAPY['sections'][0]['id']}:no_such_topic:theory")
    await th.cb_therapy_content(cb_bad)
    assert cb_bad._answers and cb_bad._answers[0][1] is True

    cb_bad = FakeCB(f"th:section_content:{tb.THERAPY['sections'][0]['id']}:no_such_ctype")
    await th.cb_therapy_section_content(cb_bad)
    assert cb_bad._answers and cb_bad._answers[0][1] is True
    print("OK неизвестные id/ctype -> alert, без исключений")

    # разделы 4-6 отсутствуют — план их автора ещё не определён (см. CLAUDE.md), не должны быть
    # придуманы
    section_ids_set = {s["id"] for s in tb.THERAPY["sections"]}
    assert len(tb.THERAPY["sections"]) == 3, tb.THERAPY["sections"]
    assert section_ids_set == {"respiratory", "cardiovascular", "digestive"}, section_ids_set
    print("OK разделы 4-6 не выдуманы (в JSON только 3 определённых планом раздела)")

    # /admin недоступен без ADMIN_IDS
    msg = FakeMsg()
    admin_msg = type("M", (), {"from_user": FakeUser(999999), "answer": msg.answer})()
    await tb.cmd_admin(admin_msg)
    assert not msg.sent_texts, "не-админ не должен получать ответ от /admin"

    msg = FakeMsg()
    admin_msg = type("M", (), {"from_user": FakeUser(ADMIN_ID), "answer": msg.answer})()
    await tb.cmd_admin(admin_msg)
    assert msg.sent_texts, "админ должен получить ответ от /admin"
    print("OK /admin: гейт по ADMIN_IDS работает")

    await check_search()
    await check_progress_and_quiz()
    await check_self_check_and_comparison_table()
    await check_admin_coverage()
    await check_admin_broadcast()
    await check_quiz_session_ttl_sweep()
    await check_favorites()
    await check_continue_button()
    await check_random_practice()
    await check_status_icons()
    await check_bot_commands()
    check_back_keyboard_no_duplicate_menu_button()
    await check_quiz_answer_race_condition()
    await check_deep_links()

    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


async def check_search():
    # структурные поля (названия разделов/тем) уже сейчас находимы поиском
    results = th.search_therapy("ХОБЛ")
    assert any(r["callback_data"] == "th:topic:respiratory:1.1" for r in results), results
    assert th.search_therapy("   ") == []
    empty = th.search_therapy("нет_такого_слова_вообще_xyz")
    text = th.get_search_results_text("нет_такого_слова_вообще_xyz", empty)
    assert "ничего не найдено" in text

    # th:search_prompt -> ставит пользователя в TH_SEARCH_PENDING
    tb.TH_SEARCH_PENDING.discard(ADMIN_ID)
    cb = FakeCB("th:search_prompt")
    await th.cb_therapy_search_prompt(cb)
    assert ADMIN_ID in tb.TH_SEARCH_PENDING

    # текстовый хендлер: пользователь НЕ в очереди -> SkipHandler, не отвечает
    tb.TH_SEARCH_PENDING.discard(777)
    msg = FakeMsg()
    text_msg = type("M", (), {"from_user": FakeUser(777), "text": "ХОБЛ", "answer": msg.answer})()
    try:
        await tb.handle_therapy_search_query(text_msg)
        raised = False
    except Exception as e:
        raised = type(e).__name__ == "SkipHandler"
    assert raised, "ожидался SkipHandler для пользователя вне очереди поиска"
    assert not msg.sent_texts

    # пользователь В очереди -> получает результаты и снимается с очереди
    tb.TH_SEARCH_PENDING.add(ADMIN_ID)
    msg = FakeMsg()
    text_msg = type("M", (), {"from_user": FakeUser(ADMIN_ID), "text": "ХОБЛ", "answer": msg.answer})()
    await tb.handle_therapy_search_query(text_msg)
    assert ADMIN_ID not in tb.TH_SEARCH_PENDING
    text, markup = msg.sent_texts[-1]
    assert "найдено" in text
    assert "th:topic:respiratory:1.1" in kb_data(markup)
    print("OK поиск: находит по структурным полям, гейт очереди работает, снимается после ответа")


async def check_progress_and_quiz():
    uid = 555
    # ещё не открывал темы -> прогресс пустой
    tb.stats["therapy_progress"].pop(str(uid), None)
    text = th.get_therapy_progress_text(uid)
    assert "Открыто тем: 0" in text

    # открытие темы фиксируется
    cb = FakeCB("th:topic:respiratory:1.1", uid=uid)
    await th.cb_therapy_topic(cb)
    text = th.get_therapy_progress_text(uid)
    assert "Открыто тем: 1" in text

    # без mcq -> кнопка теста не предлагается, только заглушка
    cb = FakeCB("th:content:respiratory:1.1:tests", uid=uid)
    await th.cb_therapy_content(cb)
    _, markup = cb.message.sent_texts[-1]
    assert not any(d.startswith("th:quiz_start:") for d in kb_data(markup))

    # временно добавляем проверяемый вопрос, чтобы пройти реальный quiz end-to-end
    topic = th.get_topic("respiratory", "1.1")
    original_mcq = topic["tests"]["mcq"]
    topic["tests"]["mcq"] = [
        {"question": "Тестовый вопрос?", "options": ["Верно", "Неверно"], "correct_index": 0, "explanation": "потому что"},
    ]
    try:
        cb = FakeCB("th:content:respiratory:1.1:tests", uid=uid)
        await th.cb_therapy_content(cb)
        _, markup = cb.message.sent_texts[-1]
        quiz_start = next(d for d in kb_data(markup) if d.startswith("th:quiz_start:"))
        assert quiz_start == "th:quiz_start:respiratory:1.1:topic_tests"

        cb = FakeCB(quiz_start, uid=uid)
        await th.cb_therapy_quiz_start(cb)
        assert uid in th.THERAPY_QUIZ_SESSIONS
        text, markup = cb.message.sent_texts[-1]
        check_html(text)
        assert "Вопрос 1/1" in text

        cb = FakeCB("th:quiz_answer:0", uid=uid)
        await th.cb_therapy_quiz_answer(cb)
        assert uid not in th.THERAPY_QUIZ_SESSIONS, "сессия должна закрыться после последнего вопроса"
        assert cb._answers[0][0] == "✅ Верно!"
        text, markup = cb.message.sent_texts[-1]
        assert "Тест завершён" in text and "1 из 1" in text

        progress = tb.stats["therapy_progress"][str(uid)]["respiratory:1.1"]
        assert progress["quiz_attempts"] == 1
        assert progress["quiz_best_correct"] == 1 and progress["quiz_best_total"] == 1

        # повторный неверный ответ -> alert с пояснением, сессия закрывается корректно
        cb = FakeCB(quiz_start, uid=uid)
        await th.cb_therapy_quiz_start(cb)
        cb = FakeCB("th:quiz_answer:1", uid=uid)
        await th.cb_therapy_quiz_answer(cb)
        assert "потому что" in cb._answers[0][0]
        assert cb._answers[0][1] is True  # show_alert=True для неверного ответа

        # прерывание теста (🛑 Закончить) до ответа -> сессия закрывается, без исключения
        cb = FakeCB(quiz_start, uid=uid)
        await th.cb_therapy_quiz_start(cb)
        cb = FakeCB("th:quiz_stop", uid=uid)
        await th.cb_therapy_quiz_stop(cb)
        assert uid not in th.THERAPY_QUIZ_SESSIONS
        text, markup = cb.message.sent_texts[-1]
        assert "прерван" in text
    finally:
        topic["tests"]["mcq"] = original_mcq

    text = th.get_therapy_progress_text(uid)
    assert "ХОБЛ" in text and "1/1" in text
    print("OK прогресс + quiz-движок: открытие темы, полное прохождение, неверный ответ, прерывание")


async def check_self_check_and_comparison_table():
    topic = th.get_topic("digestive", "3.2")
    original_self_check = topic["tests"]["self_check"]
    topic["tests"]["self_check"] = ["Назови основные симптомы."]
    try:
        cb = FakeCB("th:content:digestive:3.2:tests")
        await th.cb_therapy_content(cb)
        text, markup = cb.message.sent_texts[-1]
        check_html(text)
        assert "Назови основные симптомы" in text
        assert "готового ключа ответов пока нет" in text
        assert not any(d.startswith("th:quiz_start:") for d in kb_data(markup))
    finally:
        topic["tests"]["self_check"] = original_self_check

    section = th.get_section("cardiovascular")
    original_table = section["comparison_table"]["table"]
    section["comparison_table"]["table"] = {
        "caption": "ИБС vs АГ vs ОРЛ",
        "headers": ["ИБС", "АГ"],
        "rows": [{"aspect": "Основной механизм", "values": ["Ишемия миокарда", "Повышение ОПСС"]}],
    }
    try:
        cb = FakeCB("th:section_content:cardiovascular:comparison_table")
        await th.cb_therapy_section_content(cb)
        text, markup = cb.message.sent_texts[-1]
        check_html(text)
        assert "ИБС vs АГ vs ОРЛ" in text
        assert "Ишемия миокарда" in text
        assert "|" not in text, "сравнительная таблица не должна рендериться сырой markdown-таблицей"
    finally:
        section["comparison_table"]["table"] = original_table
    print("OK self_check и структурированная сравнительная таблица рендерятся корректно")


async def check_admin_coverage():
    total_leaves = sum(
        len(th.SECTION_CONTENT_TYPES) + len(s["topics"]) * len(th.TOPIC_CONTENT_TYPES)
        for s in tb.THERAPY["sections"]
    )
    text = th.get_admin_coverage_text()
    check_html(text)
    assert "Что ещё нужно наполнить" in text
    assert f"Итого заполнено: 0/{total_leaves} (0%)" in text, text
    assert "1.1 📖 Теория" in text and "1.1 📝 Тесты" in text

    # гейт по админу на callback-обёртке
    cb = FakeCB("admin:coverage", uid=999999)
    await tb.cb_admin_coverage(cb)
    assert not cb.message.sent_texts, "не-админ не должен получать содержимое coverage-экрана"

    cb = FakeCB("admin:coverage", uid=ADMIN_ID)
    await tb.cb_admin_coverage(cb)
    text, markup = cb.message.sent_texts[-1]
    assert "Что ещё нужно наполнить" in text
    assert kb_data(markup) == ["admin:menu"]
    print("OK admin coverage: честный подсчёт заполненности, гейт по ADMIN_IDS")


async def check_admin_broadcast():
    # доступ только у админа
    cb = FakeCB("admin:broadcast_prompt", uid=999999)
    await tb.cb_admin_broadcast_prompt(cb)
    assert 999999 not in tb.ADMIN_BROADCAST_PENDING

    cb = FakeCB("admin:broadcast_prompt", uid=ADMIN_ID)
    await tb.cb_admin_broadcast_prompt(cb)
    assert ADMIN_ID in tb.ADMIN_BROADCAST_PENDING

    tb.stats["total_users"].update({111, 222, 333})
    sent_to = []

    async def fake_send_message(user_id, text, **kwargs):
        if user_id == 222:
            raise RuntimeError("boom")
        sent_to.append((user_id, text))

    original_send = tb.bot.send_message
    tb.bot.send_message = fake_send_message
    try:
        msg = FakeMsg()
        text_msg = type("M", (), {
            "from_user": FakeUser(ADMIN_ID), "text": "Добавлена теория по ХОБЛ!", "answer": msg.answer,
        })()
        await tb.handle_admin_broadcast_text(text_msg)
    finally:
        tb.bot.send_message = original_send

    assert ADMIN_ID not in tb.ADMIN_BROADCAST_PENDING, "флаг ожидания должен сняться после рассылки"
    assert any(uid == 111 for uid, _ in sent_to)
    assert any(uid == 333 for uid, _ in sent_to)
    assert not any(uid == 222 for uid, _ in sent_to), "отправка 222 должна была упасть с исключением"
    text, _ = msg.sent_texts[-1]
    assert "успешно" in text and "не доставлено" in text
    print("OK рассылка: гейт по admin, реально рассылает, отдельно считает успехи/ошибки")

    # не-админ или админ вне очереди -> SkipHandler, сообщение не съедается
    for uid in (999999, ADMIN_ID):
        msg = FakeMsg()
        text_msg = type("M", (), {"from_user": FakeUser(uid), "text": "просто текст", "answer": msg.answer})()
        try:
            await tb.handle_admin_broadcast_text(text_msg)
            raised = False
        except Exception as e:
            raised = type(e).__name__ == "SkipHandler"
        assert raised, uid
        assert not msg.sent_texts
    print("OK рассылка: SkipHandler для не-админа и для админа вне очереди")


async def check_quiz_session_ttl_sweep():
    import time as _time

    stale_uid = 424242
    th.THERAPY_QUIZ_SESSIONS[stale_uid] = {
        "sid": "respiratory", "tid": "1.1", "kind": "topic_tests",
        "questions": [], "idx": 0, "correct": 0, "total": 0,
        "back_callback": "th:menu", "started_at": _time.time() - th.QUIZ_SESSION_TTL_SECONDS - 1,
    }

    topic = th.get_topic("respiratory", "1.1")
    original_mcq = topic["tests"]["mcq"]
    topic["tests"]["mcq"] = [{"question": "?", "options": ["a", "b"], "correct_index": 0, "explanation": ""}]
    try:
        other_uid = 424243
        cb = FakeCB("th:quiz_start:respiratory:1.1:topic_tests", uid=other_uid)
        await th.cb_therapy_quiz_start(cb)
        assert stale_uid not in th.THERAPY_QUIZ_SESSIONS, "просроченная сессия должна быть выметена"
        assert other_uid in th.THERAPY_QUIZ_SESSIONS
        th.THERAPY_QUIZ_SESSIONS.pop(other_uid, None)
    finally:
        topic["tests"]["mcq"] = original_mcq
    print("OK quiz-сессии: просроченные сессии выметаются при старте нового теста")


async def check_favorites():
    uid = 777001
    tb.stats["therapy_favorites"].pop(str(uid), None)

    assert not th.is_topic_favorite(uid, "respiratory", "1.1")
    text = th.get_favorites_text(uid)
    assert "Пока пусто" in text
    assert th.get_favorite_topics(uid) == []

    # экран темы предлагает "☆ В избранное", пока не добавлено
    cb = FakeCB("th:topic:respiratory:1.1", uid=uid)
    await th.cb_therapy_topic(cb)
    _, markup = cb.message.sent_texts[-1]
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "☆ В избранное" in labels

    # переключаем -> добавлено
    cb = FakeCB("th:fav_toggle:respiratory:1.1", uid=uid)
    await th.cb_therapy_fav_toggle(cb)
    assert cb._answers[0][0] == "⭐ Добавлено в избранное"
    assert th.is_topic_favorite(uid, "respiratory", "1.1")
    _, markup = cb.message.sent_texts[-1]
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "★ Убрать из избранного" in labels

    text = th.get_favorites_text(uid)
    assert "ХОБЛ" in text
    kb_markup = th.get_favorites_keyboard(uid)
    assert "th:topic:respiratory:1.1" in kb_data(kb_markup)

    cb = FakeCB("th:favorites", uid=uid)
    await th.cb_therapy_favorites(cb)
    text, markup = cb.message.sent_texts[-1]
    check_html(text)
    assert "ХОБЛ" in text
    assert "th:topic:respiratory:1.1" in kb_data(markup)

    # переключаем обратно -> убрано
    cb = FakeCB("th:fav_toggle:respiratory:1.1", uid=uid)
    await th.cb_therapy_fav_toggle(cb)
    assert cb._answers[0][0] == "☆ Убрано из избранного"
    assert not th.is_topic_favorite(uid, "respiratory", "1.1")
    assert th.get_favorite_topics(uid) == []

    # неизвестная тема -> alert, без падения
    cb = FakeCB("th:fav_toggle:respiratory:no_such_topic", uid=uid)
    await th.cb_therapy_fav_toggle(cb)
    assert cb._answers[0][1] is True

    tb.stats["therapy_favorites"].pop(str(uid), None)
    print("OK избранное: переключение туда-обратно, экран избранного, метка на экране темы")


async def check_continue_button():
    uid = 777002
    tb.stats["therapy_progress"].pop(str(uid), None)

    # без просмотренных тем -> кнопки "Продолжить" нет
    markup = th.get_therapy_menu_keyboard(uid)
    assert "th:topic:respiratory:1.1" not in kb_data(markup)

    cb = FakeCB("th:topic:cardiovascular:2.2", uid=uid)
    await th.cb_therapy_topic(cb)

    markup = th.get_therapy_menu_keyboard(uid)
    buttons = [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]
    assert buttons[0][1] == "th:topic:cardiovascular:2.2", buttons
    assert "Продолжить" in buttons[0][0] and "Артериальная гипертензия" in buttons[0][0]

    # без user_id (например, вызов без контекста пользователя) кнопка не строится, без исключения
    markup_anon = th.get_therapy_menu_keyboard()
    assert "th:topic:cardiovascular:2.2" not in kb_data(markup_anon)

    tb.stats["therapy_progress"].pop(str(uid), None)
    print('OK кнопка "▶️ Продолжить": появляется после первого просмотра темы, ведёт на неё')


async def check_random_practice():
    uid = 777003

    # пока во всей базе нет ни одного mcq -> честный alert, без сессии
    assert th._all_mcq_pool() == []
    cb = FakeCB("th:random_practice", uid=uid)
    await th.cb_therapy_random_practice(cb)
    assert cb._answers[0][1] is True
    assert uid not in th.THERAPY_QUIZ_SESSIONS

    topic = th.get_topic("respiratory", "1.2")
    original_mcq = topic["tests"]["mcq"]
    topic["tests"]["mcq"] = [
        {"question": "Разовый вопрос?", "options": ["Да", "Нет"], "correct_index": 0, "explanation": ""},
    ]
    try:
        cb = FakeCB("th:random_practice", uid=uid)
        await th.cb_therapy_random_practice(cb)
        assert uid in th.THERAPY_QUIZ_SESSIONS
        session = th.THERAPY_QUIZ_SESSIONS[uid]
        assert session["kind"] == "random_practice" and session["total"] == 1
        text, markup = cb.message.sent_texts[-1]
        check_html(text)
        assert "Разовый вопрос?" in text

        cb = FakeCB("th:quiz_answer:0", uid=uid)
        await th.cb_therapy_quiz_answer(cb)
        assert uid not in th.THERAPY_QUIZ_SESSIONS
        # разовая тренировка не по конкретной теме -> не пишется в прогресс темы 1.2
        assert "1.2" not in tb.stats["therapy_progress"].get(str(uid), {})
    finally:
        topic["tests"]["mcq"] = original_mcq
    print('OK "🎲 Случайный вопрос": честный alert при пустой базе, рабочая разовая сессия, не пишется в прогресс темы')


async def check_status_icons():
    topic = th.get_topic("respiratory", "1.3")
    assert th._topic_status_icon(topic) == "🗓"

    original_material = topic["theory"]["material"]
    topic["theory"]["material"] = ["текст"]
    try:
        assert th._topic_status_icon(topic) == "📥"
        markup = th.get_section_keyboard("respiratory")
        labels = [b.text for row in markup.inline_keyboard for b in row]
        assert any(t.startswith("📥 1.3") for t in labels), labels

        topic["tests"]["self_check"] = ["вопрос?"]
        assert th._topic_status_icon(topic) == "✅"
        topic["tests"]["self_check"] = []
    finally:
        topic["theory"]["material"] = original_material
    assert th._topic_status_icon(topic) == "🗓"
    print("OK иконки статуса тем (🗓/📥/✅) отражают реальную заполненность")


async def check_bot_commands():
    uid = 777004
    tb.TH_SEARCH_PENDING.discard(uid)
    tb.ADMIN_BROADCAST_PENDING.add(uid)

    msg = FakeMsg()
    m = type("M", (), {"from_user": FakeUser(uid), "answer": msg.answer})()
    await tb.cmd_menu(m)
    text, markup = msg.sent_texts[-1]
    check_html(text)
    assert any(d.startswith("th:section:") for d in kb_data(markup))

    msg = FakeMsg()
    m = type("M", (), {"from_user": FakeUser(uid), "answer": msg.answer})()
    await tb.cmd_progress(m)
    text, _ = msg.sent_texts[-1]
    assert "Мой прогресс" in text

    msg = FakeMsg()
    m = type("M", (), {"from_user": FakeUser(uid), "answer": msg.answer})()
    await tb.cmd_search(m)
    assert uid in tb.TH_SEARCH_PENDING
    assert uid not in tb.ADMIN_BROADCAST_PENDING, "поиск и рассылка — взаимоисключающие ожидания"
    tb.TH_SEARCH_PENDING.discard(uid)

    msg = FakeMsg()
    m = type("M", (), {"from_user": FakeUser(uid), "answer": msg.answer})()
    await tb.cmd_help(m)
    text, markup = msg.sent_texts[-1]
    check_html(text)
    assert "/menu" in text and "/search" in text and "/progress" in text
    print("OK команды /menu /progress /search /help: отвечают, гейт очередей взаимоисключающий")


def check_back_keyboard_no_duplicate_menu_button():
    markup = th.get_back_keyboard("th:menu")
    assert kb_data(markup) == ["th:menu"], "на самом главном меню не должно быть второй кнопки в меню"
    print('OK get_back_keyboard("th:menu") не дублирует кнопку меню')


async def check_quiz_answer_race_condition():
    """cb_therapy_quiz_answer мутирует всю session ДО первого await — воспроизводим быстрый
    двойной тап реальной конкурентностью (asyncio.gather + принудительная точка переключения
    контекста внутри answer()), а не последовательными вызовами, иначе тест не проверял бы то,
    что действительно было исправлено."""
    uid = 777006
    tb.stats["therapy_progress"].pop(str(uid), None)
    topic = th.get_topic("respiratory", "1.1")
    original_mcq = topic["tests"]["mcq"]
    topic["tests"]["mcq"] = [
        {"question": "Q1", "options": ["A", "B"], "correct_index": 0, "explanation": ""},
        {"question": "Q2", "options": ["A", "B"], "correct_index": 0, "explanation": ""},
    ]
    try:
        th.start_therapy_quiz(uid, "respiratory", "1.1", "topic_tests", "th:topic:respiratory:1.1")

        class SlowFakeCB(FakeCB):
            async def answer(self, text=None, show_alert=False):
                await asyncio.sleep(0)  # настоящая точка переключения контекста, как реальный API-вызов
                self._answers.append((text, show_alert))

        cb1 = SlowFakeCB("th:quiz_answer:0", uid=uid)
        cb2 = SlowFakeCB("th:quiz_answer:0", uid=uid)
        await asyncio.gather(th.cb_therapy_quiz_answer(cb1), th.cb_therapy_quiz_answer(cb2))

        assert uid not in th.THERAPY_QUIZ_SESSIONS, "сессия из 2 вопросов должна закрыться после 2 ответов"
        progress = tb.stats["therapy_progress"][str(uid)]["respiratory:1.1"]
        assert progress["quiz_attempts"] == 1, "запись прогресса не должна задваиваться"
        assert progress["quiz_best_correct"] == 2 and progress["quiz_best_total"] == 2, progress
    finally:
        topic["tests"]["mcq"] = original_mcq
        tb.stats["therapy_progress"].pop(str(uid), None)
    print("OK quiz_answer: гонка при двойном тапе не даёт IndexError/задвоенный счёт")


async def check_deep_links():
    assert th.resolve_deep_link("") is None
    assert th.resolve_deep_link("garbage") is None
    assert th.resolve_deep_link("topic__respiratory__no_such_topic") is None
    assert th.resolve_deep_link("section__no_such_section") is None
    assert th.resolve_deep_link("topic__respiratory") is None  # неполный payload

    payload = th.build_topic_deep_link_payload("respiratory", "1.1")
    assert payload == "topic__respiratory__1.1"
    assert th.resolve_deep_link(payload) == ("topic", "respiratory", "1.1")

    section_payload = th.build_section_deep_link_payload("cardiovascular")
    assert section_payload == "section__cardiovascular"
    assert th.resolve_deep_link(section_payload) == ("section", "cardiovascular", None)

    # /start topic__respiratory__1.1 -> сразу экран темы, а не главное меню, и open засчитан в прогресс
    uid = 777007
    tb.stats["therapy_progress"].pop(str(uid), None)
    msg = FakeMsg()
    start_msg = type("M", (), {"from_user": FakeUser(uid), "text": f"/start {payload}", "answer": msg.answer})()
    await tb.cmd_start(start_msg)
    text, markup = msg.sent_texts[-1]
    check_html(text)
    assert "Хроническая обструктивная болезнь лёгких" in text
    assert any(d.startswith("th:content:respiratory:1.1:") for d in kb_data(markup))
    assert tb.stats["therapy_progress"][str(uid)]["respiratory:1.1"]["opened_at"]

    # /start section__cardiovascular -> сразу экран раздела
    uid2 = 777008
    msg2 = FakeMsg()
    start_msg2 = type(
        "M", (), {"from_user": FakeUser(uid2), "text": f"/start {section_payload}", "answer": msg2.answer},
    )()
    await tb.cmd_start(start_msg2)
    text2, markup2 = msg2.sent_texts[-1]
    assert "Сердечно-сосудистая" in text2
    assert any(d.startswith("th:topic:cardiovascular:") for d in kb_data(markup2))

    # /start с неизвестным/битым payload -> тихий откат на обычное главное меню, без падения
    uid3 = 777009
    msg3 = FakeMsg()
    start_msg3 = type(
        "M", (), {"from_user": FakeUser(uid3), "text": "/start bogus_payload_xyz", "answer": msg3.answer},
    )()
    await tb.cmd_start(start_msg3)
    text3, markup3 = msg3.sent_texts[-1]
    assert any(d.startswith("th:section:") for d in kb_data(markup3))

    # build_deep_link_url: без BOT_USERNAME (как до первого запуска main()) отдаёт заглушку, не падает
    assert tb.BOT_USERNAME == ""
    placeholder = tb.build_deep_link_url(payload)
    assert payload in placeholder and "t.me" not in placeholder

    tb.BOT_USERNAME = "TherapyBot"
    try:
        url = tb.build_deep_link_url(payload)
        assert url == f"https://t.me/TherapyBot?start={payload}"
    finally:
        tb.BOT_USERNAME = ""

    tb.stats["therapy_progress"].pop(str(uid), None)
    print("OK deep links: валидные/битые payload'ы, /start сразу открывает тему/раздел, build_deep_link_url")


if __name__ == "__main__":
    asyncio.run(run())
