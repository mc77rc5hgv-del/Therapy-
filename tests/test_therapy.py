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
    start_msg = type("M", (), {"from_user": FakeUser(ADMIN_ID), "answer": msg.answer})()
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
            assert data == [f"th:section:{sid}"], data
        print(f"OK секционные блоки раздела {sid} отрендерены (заглушки — честные, без контента)")

        for topic in section["topics"]:
            tid = topic["id"]
            cb = FakeCB(f"th:topic:{sid}:{tid}")
            await th.cb_therapy_topic(cb)
            text, markup = cb.message.sent_texts[-1]
            check_html(text)
            data = kb_data(markup)
            assert f"th:section:{sid}" in data
            assert any(d.startswith(f"th:content:{sid}:{tid}:") for d in data), data

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
                assert data == [f"th:topic:{sid}:{tid}"], data
        print(f"OK темы раздела {sid}: {len(section['topics'])} шт., теория/тесты отрендерены")

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

    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    asyncio.run(run())
