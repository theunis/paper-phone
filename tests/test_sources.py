from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from paper_phone.config import Config, Event, Place
from paper_phone.http import Http
from paper_phone.sources import agenda, astro, content
from paper_phone.sources.agenda import Item


def test_markdown_tasks() -> None:
    tasks = agenda.parse_tasks_markdown(
        """
# Tasks
- [ ] Renew passport due:2026-10-02 ! #admin
- [x] Already done
* [ ] Call the plumber #home #urgent
not a task
"""
    )
    assert [t.title for t in tasks] == ["Renew passport", "Already done", "Call the plumber"]
    first, done, third = tasks
    assert first.due == dt.date(2026, 10, 2)
    assert first.priority and first.tags == ["admin"]
    assert done.done
    assert third.tags == ["home", "urgent"] and not third.priority


def test_items_sort_all_day_first() -> None:
    day = dt.date(2026, 9, 28)
    items = [
        Item(day, dt.time(9, 30), title="b"),
        Item(day, title="a"),
        Item(day, dt.time(8), title="c"),
    ]
    assert [i.title for i in sorted(items, key=lambda i: i.sort_key)] == ["a", "c", "b"]


def test_config_events_and_holidays(tmp_path) -> None:
    cfg = Config(events=[Event(title="Dentist", date=dt.date(2026, 9, 30), start=dt.time(8, 30))])
    http = Http(tmp_path, offline=True)
    items = agenda.calendar_items(
        http, cfg, dt.date(2026, 9, 28), dt.date(2026, 10, 4), ZoneInfo("UTC")
    )
    assert [i.title for i in items] == ["Dentist"]
    kings_day = agenda.holiday_items("NL", dt.date(2026, 4, 27), dt.date(2026, 4, 27))
    assert kings_day and kings_day[0].kind == "holiday"


def test_recurring_ics(tmp_path) -> None:
    ics = tmp_path / "cal.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:x\n"
        "DTSTART;TZID=Europe/Amsterdam:20260105T093000\nDTEND;TZID=Europe/Amsterdam:20260105T094500\n"
        "RRULE:FREQ=WEEKLY;BYDAY=MO,WE\nSUMMARY:Stand-up\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    cfg = Config(calendars=[str(ics)], base_dir=tmp_path)
    tz = ZoneInfo("Europe/Amsterdam")
    http = Http(tmp_path, offline=True)
    items = agenda.calendar_items(http, cfg, dt.date(2026, 9, 28), dt.date(2026, 10, 4), tz)
    assert [(i.date, i.start) for i in items] == [
        (dt.date(2026, 9, 28), dt.time(9, 30)),
        (dt.date(2026, 9, 30), dt.time(9, 30)),
    ]


def test_moon_phases_match_known_events() -> None:
    # 2024-04-08: total solar eclipse (new moon 18:21 UTC); 2024-09-18: partial lunar eclipse.
    ((new_moon, name),) = astro.phase_times(dt.date(2024, 4, 8), dt.date(2024, 4, 8))
    assert name == "New moon" and abs(new_moon.hour * 60 + new_moon.minute - (18 * 60 + 21)) <= 5
    ((full, name),) = astro.phase_times(dt.date(2024, 9, 18), dt.date(2024, 9, 18))
    assert name == "Full moon" and full.hour == 2
    assert astro.moon(dt.date(2024, 9, 18)).illumination > 0.97


def test_sun_times_utrecht_midsummer() -> None:
    times = astro.sun_times(dt.date(2026, 6, 21), 52.09, 5.12, ZoneInfo("Europe/Amsterdam"))
    assert times is not None
    rise, set_ = times
    assert rise.date() == dt.date(2026, 6, 21)
    assert (rise.hour, set_.hour) == (5, 22)


def test_clock_change_detected() -> None:
    tz = ZoneInfo("Europe/Amsterdam")
    assert astro.clock_changes(dt.date(2026, 10, 1), dt.date(2026, 10, 31), tz) == [
        (dt.date(2026, 10, 25), -1.0)
    ]


def test_picks_are_stable_and_vary_by_index() -> None:
    items = list(range(50))
    assert content.pick(items, "seed", 3, 2) == content.pick(items, "seed", 3, 2)
    assert content.pick(items, "seed", 3, 2) != content.pick(items, "seed", 4, 2)


def test_bundled_content_is_complete() -> None:
    for code in content.available("words"):
        deck = content.word_deck(code)
        assert len(deck["words"]) >= 60
        for w in deck["words"]:
            assert w["word"] and w["en"] and w["nl"]
    for code in content.available("phrases"):
        book = content.phrasebook(code)
        assert book is not None and book["sections"]
    assert len(content.recipes()) >= 20
    assert "NO" in content.countries()  # quoted keys: YAML would otherwise read `NO` as False


def test_recipe_respects_diet() -> None:
    for i in range(20):
        (r,) = content.choose_recipes(dt.date(2026, 1, 1), i, diet="vegan", forced=None, extra=None)
        assert "vegan" in r["diet"]


def test_place_label() -> None:
    assert Place(query="Oudwijk, Utrecht").label == "Oudwijk"
