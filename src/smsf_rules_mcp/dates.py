"""Deadline arithmetic on the Australia/Sydney calendar."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .data import corpus

SYDNEY = ZoneInfo("Australia/Sydney")


def sydney_today(now: datetime | date | str | None = None) -> date:
    """The calendar date in Sydney for `now` (UTC clock if omitted).

    Accepts a timezone-aware datetime, an ISO 8601 string with an offset or Z,
    or a plain YYYY-MM-DD which is taken as a Sydney calendar date as given.
    """
    if now is None:
        now = datetime.now(UTC)
    if isinstance(now, str):
        s = now.strip()
        if len(s) == 10:
            return date.fromisoformat(s)
        now = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if isinstance(now, datetime):
        if now.tzinfo is None:
            raise ValueError("a datetime needs a timezone offset (or use a YYYY-MM-DD date)")
        return now.astimezone(SYDNEY).date()
    return now


def fy_end(today: date) -> date:
    return date(today.year + 1 if today.month >= 7 else today.year, 6, 30)


def next_annual(today: date, month: int, day: int) -> date:
    candidate = date(today.year, month, day)
    return candidate if candidate >= today else date(today.year + 1, month, day)


def next_tbar_due(today: date) -> date:
    """Next quarterly TBAR due date on or after `today` (28 Jan/Apr/Jul/Oct)."""
    for y in (today.year, today.year + 1):
        for m in (1, 4, 7, 10):
            d = date(y, m, 28)
            if d >= today:
                return d
    raise AssertionError("unreachable")


def resolve_deadline(deadline: dict[str, Any], today: date) -> date:
    rule: str = deadline["rule"]
    if rule == "quarterly_28_days":
        return next_tbar_due(today)
    if rule == "fy_end":
        return fy_end(today)
    if rule.startswith("fixed:"):
        return date.fromisoformat(rule[6:])
    if rule.startswith("annual:"):
        month, day = (int(x) for x in rule[7:].split("-"))
        return next_annual(today, month, day)
    raise ValueError(f"unknown deadline rule {rule!r}")


def deadlines() -> list[dict[str, Any]]:
    return corpus()["deadlines"]


def days_until(target: str, now: datetime | date | str | None = None) -> dict[str, Any]:
    """Days from today (Sydney) to a deadline id or an ISO date. Same day is 0."""
    today = sydney_today(now)
    by_id = {d["id"]: d for d in deadlines()}
    if target in by_id:
        d = by_id[target]
        due = resolve_deadline(d, today)
        meta: dict[str, Any] = {
            "deadline_id": d["id"],
            "label": d["label"],
            "detail": d["detail"],
            "sources": d["sources"],
            "verified_on": d["verified_on"],
            "rule_id": f"deadline-{d['id']}",
        }
    else:
        try:
            due = date.fromisoformat(target)
        except ValueError as exc:
            known = ", ".join(sorted(by_id))
            raise ValueError(f"target {target!r} is neither a deadline id ({known}) nor a YYYY-MM-DD date") from exc
        meta = {"deadline_id": None}
    delta = (due - today).days
    return {
        "target": target,
        "due_date": due.isoformat(),
        "today_sydney": today.isoformat(),
        "days": delta,
        "overdue": delta < 0,
        "calendar": "Australia/Sydney",
        **meta,
        "notice": "General information about the rules, not a licensed financial service.",
    }
