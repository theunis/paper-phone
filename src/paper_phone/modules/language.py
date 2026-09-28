"""Words of the day/week/month, and the travel phrasebook."""

from __future__ import annotations

import datetime as dt
from typing import Any

from paper_phone.build import Data
from paper_phone.modules.core import DAY_ABBR, PageCtx, module
from paper_phone.sources import content

# Which phrases (by position in each section) fit on one pocket page.
PHRASE_PICKS = {
    "Basics": [0, 2, 3, 6, 7],
    "Getting around": [0, 2, 5],
    "Eating & drinking": [0, 2, 4],
    "Help & health": [0, 2],
}


def _entry(w: dict[str, Any], native: str) -> dict[str, Any]:
    return {
        "word": w["word"],
        "pos": w.get("pos", ""),
        "say": w.get("romaji") or w.get("say", ""),
        "hint": w.get("say", "") if w.get("romaji") else "",
        "meaning": w.get(native) or w.get("en", ""),
        "example": w.get("example", ""),
        "example_romaji": w.get("example_romaji", ""),
        "example_meaning": w.get(f"example_{native}") or w.get("example_en", ""),
    }


@module("words", title="Words", icon="languages", color="words", half=True)
def words(data: Data, page: PageCtx) -> dict[str, Any]:
    lang = data.cfg.language
    code = lang.learn
    if data.is_trip and data.cfg.trip and (data.cfg.trip.language or data.country.get("language")):
        trip_code = data.cfg.trip.language or data.country["language"]
        if trip_code in content.available("words"):
            code = trip_code
    deck = content.word_deck(code)
    seed = f"words-{code}"
    native = lang.native
    ctx: dict[str, Any] = {"language": deck["language"], "endonym": deck.get("endonym", "")}
    ctx["meta"] = deck.get("endonym", deck["language"])
    if page.size == "half":
        (w,) = content.pick(deck["words"], seed, data.date.toordinal())
        more = content.pick(deck["words"], seed + "-more", data.date.toordinal(), 1)
        return ctx | {
            "view": "one",
            "w": _entry(w, native),
            "more": [_entry(m, native) for m in more],
        }
    if data.edition in ("daily", "travel"):
        day = data.date.toordinal()
        today = content.pick(deck["words"], seed, day)[0]
        more = content.pick(deck["words"], seed + "-more", day, 2)
        yesterday = content.pick(deck["words"], seed, day - 1)[0]
        return ctx | {
            "view": "day",
            "w": _entry(today, native),
            "more": [_entry(m, native) for m in more],
            "quiz": _entry(yesterday, native),
        }
    if data.edition == "weekly":
        week = data.date.isocalendar()[1] + 53 * data.date.year
        picks = content.pick(deck["words"], seed + "-week", week, 7)
        monday = data.date - dt.timedelta(days=data.date.weekday())
        return ctx | {
            "view": "week",
            "list": [
                {"abbr": DAY_ABBR[(monday + dt.timedelta(days=i)).weekday()], **_entry(w, native)}
                for i, w in enumerate(picks)
            ],
        }
    month = data.date.month + 12 * data.date.year
    picks = content.pick(deck["words"], seed + "-month", month, 14)
    return ctx | {"view": "month", "list": [_entry(w, native) for w in picks]}


@module("phrases", title="Phrasebook", icon="message-circle", color="words")
def phrases(data: Data, page: PageCtx) -> dict[str, Any]:
    trip = data.cfg.trip
    code = (
        (trip.language if trip else None) or data.country.get("language") or data.cfg.language.learn
    )
    book = content.phrasebook(code)
    native = data.cfg.language.native
    if book is None:
        return {"meta": code, "missing": code, "available": content.available("phrases")}
    veggie = data.cfg.recipes.diet in ("vegetarian", "vegan")
    sections = []
    for section in book["sections"]:
        picks = list(PHRASE_PICKS.get(section["title"], []))
        if not picks:
            continue
        if veggie and section["title"] == "Eating & drinking":
            picks.append(5)  # "I'm vegetarian"
        title = section.get("title_nl") if native == "nl" else section["title"]
        sections.append(
            {
                "title": title,
                "phrases": [
                    {
                        "phrase": p["phrase"],
                        "say": p.get("romaji") or p.get("say", ""),
                        "meaning": p.get(native) or p["en"],
                    }
                    for i, p in enumerate(section["phrases"])
                    if i in picks
                ],
            }
        )
    return {
        "meta": book.get("endonym", book["language"]),
        "sections": sections,
        "latin": code not in {"ja", "el"},
    }


def numbers_for(data: Data) -> tuple[str, list[dict[str, Any]]]:
    trip = data.cfg.trip
    code = (trip.language if trip else None) or data.country.get("language") or ""
    book = content.phrasebook(code) if code else None
    if not book:
        return "", []
    return book.get("endonym", book["language"]), [
        n for n in book.get("numbers", []) if n["n"] <= 10
    ]
