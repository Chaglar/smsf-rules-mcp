"""Load the generated rules corpus (rules.json) once and expose lookups."""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources
from typing import Any

_TOKEN = re.compile(r"[a-z0-9]+")


@cache
def corpus() -> dict[str, Any]:
    with resources.files("smsf_rules_mcp").joinpath("rules.json").open(encoding="utf-8") as fh:
        return json.load(fh)


@cache
def rules_by_id() -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in corpus()["rules"]}


def categories() -> list[str]:
    return sorted({r["category"] for r in corpus()["rules"]})


def tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def rule_search_text(rule: dict[str, Any]) -> str:
    parts = [rule["id"], rule["title"], rule["category"], rule["summary"], rule.get("statute") or ""]
    parts += rule.get("mechanics", [])
    parts += [f["label"] for f in rule.get("figures", [])]
    parts += [s["label"] for s in rule.get("sources", [])]
    return " ".join(parts)


def search(query: str, limit: int = 10) -> list[tuple[int, dict[str, Any]]]:
    """Rank rules by the number of distinct query tokens they contain."""
    q = tokens(query)
    if not q:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for rule in corpus()["rules"]:
        hits = len(q & tokens(rule_search_text(rule)))
        if hits:
            scored.append((hits, rule))
    scored.sort(key=lambda t: (-t[0], t[1]["id"]))
    return scored[:limit]


def normalise_fy(value: str | int) -> str:
    """Accept 2026, "2026", "2026-27", "FY2026-27", "2026/27" and return "2026-27"."""
    s = str(value).strip().upper().replace("FY", "").replace(" ", "")
    m = re.fullmatch(r"(\d{4})(?:[-/](\d{2}|\d{4}))?", s)
    if not m:
        raise ValueError(f"unrecognised financial year {value!r}; use a form like 2026-27")
    start = int(m.group(1))
    if m.group(2):
        end = int(m.group(2))
        end = end if end > 99 else 2000 + end
        if end != start + 1:
            raise ValueError(f"financial year {value!r} does not span consecutive years")
    return f"{start}-{str(start + 1)[-2:]}"


def caps_for_fy(value: str | int) -> dict[str, Any]:
    key = normalise_fy(value)
    caps = corpus()["caps_by_fy"].get(key)
    if caps is None:
        known = ", ".join(sorted(corpus()["caps_by_fy"]))
        raise ValueError(f"no published caps for FY {key}; published: {known}")
    return caps


def citation(rule: dict[str, Any]) -> str:
    lines = [f"{rule['title']} [{rule['id']}]", ""]
    lines.append(rule["summary"])
    if rule.get("statute"):
        lines += ["", f"Statute: {rule['statute']}"]
    if rule.get("figures"):
        lines += ["", rule.get("example_heading") or "Figures:"]
        for f in rule["figures"]:
            val = f"${f['cents'] / 100:,.2f}" if "cents" in f else f["text"]
            fy = f" (FY {f['financial_year']})" if f.get("financial_year") else ""
            lines.append(f"  {f['label']}: {val}{fy}")
        if rule.get("example_footnote"):
            lines.append(f"  {rule['example_footnote']}")
    if rule.get("mechanics"):
        lines += ["", "Mechanics:"]
        lines += [f"  - {m}" for m in rule["mechanics"]]
    lines += ["", "Sources:"]
    for s in rule["sources"]:
        lines.append(f"  - {s['label']}" + (f" <{s['url']}>" if s.get("url") else ""))
    lines += ["", f"Primary source: {rule['primary_source_url']}"]
    if rule.get("verified_on"):
        lines.append(f"Figures verified {rule['verified_on']} in {rule['verified_by']}")
    lines.append(
        f"Corpus: {rule['source_file']} @ {rule['source_commit']} ({rule['source_commit_date']}), {rule['corpus_url']}"
    )
    lines += ["", "General information about the rules, not a licensed financial service."]
    return "\n".join(lines)
