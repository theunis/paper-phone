"""Training schedule: today's session with a log, a week plan, or a month grid."""

from __future__ import annotations

import datetime as dt
from typing import Any

from paper_phone.build import Data
from paper_phone.config import DAY_KEYS, Session, TrainingConfig
from paper_phone.modules.core import DAY_ABBR, PageCtx, d_short, module

TYPE_ICON = {
    "run": "footprints",
    "walk": "footprints",
    "bike": "bike",
    "swim": "waves",
    "strength": "dumbbell",
    "yoga": "heart-pulse",
    "cross": "activity",
    "rest": "moon",
    "race": "trophy",
}

# Used when the config has no training section: a gentle all-round week.
DEFAULT_WEEK = TrainingConfig(
    name="Move every day",
    weekly={
        "mon": Session(
            title="Bodyweight circuit",
            type="strength",
            duration_min=20,
            intensity="moderate",
            detail="3 rounds: 12 squats · 8 push-ups · 30 s plank · 10 lunges/leg · 12 bridges",
        ),
        "tue": Session(title="Brisk walk", type="walk", duration_min=30, intensity="easy"),
        "wed": Session(
            title="Easy run or ride",
            type="run",
            duration_min=30,
            intensity="easy",
            detail="Conversational pace; walk breaks are fine",
        ),
        "thu": Session(
            title="Mobility",
            type="yoga",
            duration_min=15,
            intensity="easy",
            detail="Cat-cow · hip flexor stretch · thoracic rotations · hamstring fold",
        ),
        "fri": Session(
            title="Bodyweight circuit",
            type="strength",
            duration_min=20,
            intensity="moderate",
            detail="3 rounds: 12 squats · 8 push-ups · 30 s side plank · 10 step-ups/leg",
        ),
        "sat": Session(
            title="Long walk or ride",
            type="walk",
            duration_min=60,
            intensity="easy",
            detail="Somewhere green, no headphones",
        ),
        "sun": Session(title="Rest", type="rest"),
    },
)


def plan(data: Data) -> TrainingConfig:
    return data.cfg.training or DEFAULT_WEEK


def session_for(cfg: TrainingConfig, day: dt.date) -> Session | None:
    key = DAY_KEYS[day.weekday()]
    if cfg.plan and cfg.start:
        week = (day - cfg.start).days // 7
        if 0 <= week < len(cfg.plan):
            return cfg.plan[week].get(key)
    return cfg.weekly.get(key)


def week_number(cfg: TrainingConfig, day: dt.date) -> int | None:
    if cfg.plan and cfg.start:
        week = (day - cfg.start).days // 7
        if 0 <= week < len(cfg.plan):
            return week + 1
    return None


def summary(s: Session | None) -> str:
    if s is None:
        return ""
    bits = []
    if s.distance_km:
        bits.append(f"{s.distance_km:g} km")
    if s.duration_min:
        bits.append(f"{s.duration_min} min")
    return " · ".join(bits)


def short(s: Session | None) -> str:
    """Tiny label for the month grid."""
    if s is None:
        return ""
    if s.type == "rest":
        return "rest"
    if s.distance_km:
        return f"{s.title.split()[0][:5]} {s.distance_km:g}k"
    if s.duration_min:
        return f"{s.title.split()[0][:5]} {s.duration_min}′"
    return s.title[:9]


@module("training", title="Training", icon="dumbbell", color="training")
def training(data: Data, page: PageCtx) -> dict[str, Any]:
    cfg = plan(data)
    goal = None
    if cfg.goal and cfg.goal.date >= data.date:
        goal = {
            "name": cfg.goal.name,
            "days": (cfg.goal.date - data.date).days,
            "date": cfg.goal.date,
        }
    ctx: dict[str, Any] = {
        "name": cfg.name,
        "goal": goal,
        "icon_for": lambda s: TYPE_ICON.get(s.type if s else "rest", "activity"),
        "summary": summary,
        "short": short,
        "fallback": data.cfg.training is None,
    }
    monday = data.date - dt.timedelta(days=data.date.weekday())
    week_days = [monday + dt.timedelta(days=i) for i in range(7)]
    wk = week_number(cfg, data.date)
    ctx["meta"] = f"Week {wk} of {len(cfg.plan)}" if wk else cfg.name
    if data.edition in ("daily", "travel"):
        ctx |= {
            "view": "day",
            "today": session_for(cfg, data.date),
            "week": [
                {
                    "date": d,
                    "abbr": DAY_ABBR[d.weekday()],
                    "s": session_for(cfg, d),
                    "today": d == data.date,
                    "past": d < data.date,
                }
                for d in week_days
            ],
        }
    elif data.edition == "weekly":
        sessions = [session_for(cfg, d) for d in data.days]
        rows = [
            {"date": d, "abbr": DAY_ABBR[d.weekday()], "s": s, "label": d_short(d)}
            for d, s in zip(data.days, sessions, strict=True)
        ]
        km = sum((s.distance_km or 0) for s in sessions if s)
        mins = sum((s.duration_min or 0) for s in sessions if s)
        ctx |= {"view": "week", "rows": rows, "km": km, "mins": mins}
    else:
        first = data.start - dt.timedelta(days=data.start.weekday())
        weeks = []
        day = first
        while day <= data.end:
            days = [day + dt.timedelta(days=i) for i in range(7)]
            sessions = [session_for(cfg, d) for d in days]
            weeks.append(
                {
                    "number": day.isocalendar()[1],
                    "cells": [
                        {"date": d, "s": s, "in_month": d.month == data.start.month}
                        for d, s in zip(days, sessions, strict=True)
                    ],
                    "km": sum((s.distance_km or 0) for s in sessions if s),
                }
            )
            day += dt.timedelta(days=7)
        ctx |= {"view": "month", "weeks": weeks, "abbr": [a[:2] for a in DAY_ABBR]}
    return ctx
