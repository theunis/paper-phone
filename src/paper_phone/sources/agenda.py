"""Events (ICS calendars, config), public holidays and tasks."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays as holidays_lib
import icalendar
import recurring_ical_events

from paper_phone.config import Config, Task
from paper_phone.http import Http


@dataclass
class Item:
    date: dt.date
    start: dt.time | None = None
    end: dt.time | None = None
    title: str = ""
    location: str | None = None
    kind: str = "event"  # event | holiday | transport | plan

    @property
    def sort_key(self) -> tuple:
        return (self.date, self.start is not None, self.start or dt.time.min, self.title)

    @property
    def all_day(self) -> bool:
        return self.start is None

    @property
    def minutes(self) -> tuple[int, int] | None:
        if self.start is None:
            return None
        start = self.start.hour * 60 + self.start.minute
        end = self.end.hour * 60 + self.end.minute if self.end else start + 60
        return start, max(end, start + 30)


def _read_ics(http: Http, source: str, base: Path) -> bytes:
    if source.startswith(("http://", "https://", "webcal://")):
        return http.get_text(source.replace("webcal://", "https://"), ttl=900).encode()
    path = Path(source).expanduser()
    return (path if path.is_absolute() else base / path).read_bytes()


def calendar_items(
    http: Http, cfg: Config, start: dt.date, end: dt.date, tz: ZoneInfo
) -> list[Item]:
    items: list[Item] = []
    for source in cfg.calendars:
        cal = icalendar.Calendar.from_ical(_read_ics(http, source, cfg.base_dir))
        for ev in recurring_ical_events.of(cal).between(start, end + dt.timedelta(days=1)):
            begin = ev.get("DTSTART").dt
            finish = ev.get("DTEND").dt if ev.get("DTEND") else None
            title = str(ev.get("SUMMARY", "")).strip()
            location = str(ev.get("LOCATION", "")).split(",")[0].strip() or None
            if isinstance(begin, dt.datetime):
                begin = begin.astimezone(tz) if begin.tzinfo else begin
                stop = finish.astimezone(tz) if isinstance(finish, dt.datetime) else None
                if stop and stop.tzinfo is None:
                    stop = None
                items.append(
                    Item(
                        date=begin.date(),
                        start=begin.time(),
                        end=stop.time() if stop and stop.date() == begin.date() else None,
                        title=title,
                        location=location,
                    )
                )
            else:
                last = (finish - dt.timedelta(days=1)) if isinstance(finish, dt.date) else begin
                day = begin
                while day <= last:
                    if start <= day <= end:
                        items.append(Item(date=day, title=title, location=location))
                    day += dt.timedelta(days=1)
    for ev in cfg.events:
        if start <= ev.date <= end:
            items.append(Item(ev.date, ev.start, ev.end, title=ev.title, location=ev.location))
    return sorted((i for i in items if start <= i.date <= end), key=lambda i: i.sort_key)


def holiday_items(country: str, start: dt.date, end: dt.date) -> list[Item]:
    try:
        table = holidays_lib.country_holidays(country, years=range(start.year, end.year + 1))
    except NotImplementedError:
        return []
    return [
        Item(date=day, title=name, kind="holiday")
        for day, name in sorted(table.items())
        if start <= day <= end
    ]


_TASK = re.compile(r"^\s*[-*]\s*\[(?P<done>[ xX])\]\s*(?P<body>.+)$")


def parse_tasks_markdown(text: str) -> list[Task]:
    """`- [ ] Call the plumber due:2026-09-30 ! #home` style task lists."""
    tasks = []
    for line in text.splitlines():
        match = _TASK.match(line)
        if not match:
            continue
        body = match.group("body")
        due = None
        if m := re.search(r"\bdue:(\d{4}-\d{2}-\d{2})\b", body):
            due = dt.date.fromisoformat(m.group(1))
            body = body.replace(m.group(0), "")
        tags = re.findall(r"(?<!\S)#([\w-]+)", body)
        body = re.sub(r"(?<!\S)#[\w-]+", "", body)
        priority = bool(re.search(r"(?<!\S)!(?!\S)", body))
        body = re.sub(r"(?<!\S)!(?!\S)", "", body)
        tasks.append(
            Task(
                title=" ".join(body.split()),
                due=due,
                priority=priority,
                tags=tags,
                done=match.group("done") != " ",
            )
        )
    return tasks


def load_tasks(cfg: Config) -> list[Task]:
    tasks = list(cfg.tasks)
    if cfg.tasks_file:
        tasks += parse_tasks_markdown(cfg.resolve(cfg.tasks_file).read_text(encoding="utf-8"))
    return [t for t in tasks if not t.done]
