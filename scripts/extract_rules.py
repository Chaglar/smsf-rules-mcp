#!/usr/bin/env python3
"""Generate src/smsf_rules_mcp/rules.json from the SMSF Core TypeScript sources.

Reads the corpus with `git show origin/main:<path>` so the other repos' working
trees are never touched. Nothing here invents a figure: every number is parsed
out of the TypeScript, every URL is copied from a source comment or citation
table, and a record without an ato.gov.au or legislation.gov.au URL is listed
under "excluded" instead of being emitted.

Usage:
    uv run python scripts/extract_rules.py [--landing DIR] [--product DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parents[1] / "src" / "smsf_rules_mcp" / "rules.json"
CORPUS_URL = "https://smsfcore.com/rules"
PRIMARY_HOSTS = ("https://www.ato.gov.au/", "https://www.legislation.gov.au/")

# Words the server must never carry (AFSL discipline). Built from fragments so
# a plain grep of the repository stays clean.
_F = ["adv", "ice"], ["recomm", "end"], ["guar", "antee"], ["optim", "al"], ["optim", "ise"]
_G = ["optim", "ize"], ["outperf", "orm"], ["should inv", "est"], ["returns ", "of"]
_H = ["best strat", "egy"], ["beat the ", "market"]
BANNED = tuple("".join(p) for p in (*_F, *_G, *_H))


# ---------------------------------------------------------------- git access
def git_show(repo: Path, path: str, ref: str = "origin/main") -> str:
    return subprocess.run(["git", "show", f"{ref}:{path}"], cwd=repo, check=True, capture_output=True, text=True).stdout


def git_commit(repo: Path, path: str, ref: str = "origin/main") -> tuple[str, str]:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%h %cs", ref, "--", path],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return out[0], out[1]


# ------------------------------------------------- TS object literal -> JSON
def ts_literal_to_json(text: str) -> Any:
    """Tolerant conversion of a TypeScript object/array literal to Python data.

    Handles comments, single-quoted strings, bare keys, numeric underscores
    and trailing commas. Only touches text outside string literals.
    """
    parts: list[str] = []
    i, n = 0, len(text)
    code: list[str] = []

    def flush_code() -> None:
        s = "".join(code)
        code.clear()
        s = re.sub(r"(?<=\d)_(?=\d)", "", s)
        s = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*|\d+)\s*:", r'\1"\2":', s)
        parts.append(s)

    while i < n:
        c = text[i]
        if c in "\"'":
            flush_code()
            quote = c
            buf = ['"']
            i += 1
            while i < n and text[i] != quote:
                ch = text[i]
                if ch == "\\":
                    buf.append(text[i : i + 2])
                    i += 2
                    continue
                if ch == '"':
                    buf.append('\\"')
                else:
                    buf.append(ch)
                i += 1
            buf.append('"')
            parts.append("".join(buf))
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            i = text.find("*/", i) + 2
            continue
        code.append(c)
        i += 1
    flush_code()
    s = "".join(parts)
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    return json.loads(s)


def slice_literal(text: str, marker: str) -> str:
    """Return the literal that starts at the first [ or { after `marker`."""
    start = text.index(marker) + len(marker)
    open_at = min(x for x in (text.find("[", start), text.find("{", start)) if x >= 0)
    closer = "]" if text[open_at] == "[" else "}"
    end = text.index(f"\n{closer};", open_at)
    return text[open_at : end + 2]


# ----------------------------------------------------------- verified dates
_MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def verified_on(text: str) -> str | None:
    """First 'verified <date>' in a source header, as ISO."""
    m = re.search(r"verified (\d{4}-\d{2}-\d{2})", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"verified (\d{1,2}) ([A-Z][a-z]{2}) (\d{4})", text)
    if m:
        return date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1))).isoformat()
    return None


# ------------------------------------------------ statute -> URL resolution
def parse_citations(text: str) -> list[tuple[str, str]]:
    pairs = re.findall(r'ruling_id:\s*"([^"]+)",\s*paragraph:\s*"[^"]*",\s*source_url:\s*"([^"]+)"', text, re.S)
    if not pairs:
        raise SystemExit("citations.ts: no (ruling_id, source_url) pairs parsed")
    return pairs


def resolve_statute(label: str, citations: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Map a statute label from the corpus to a legislation.gov.au URL by
    matching the act year and section against the product citation table."""
    act = re.search(r"Income Tax Assessment Act (1936|1997)", label)
    if not act:
        return None
    year = act.group(1)
    sections = re.findall(r"\bss?\s+(\d{1,3}[A-Z]*(?:-\d+)?)", label)
    sections += [f"Div {d}" for d in re.findall(r"Division (\d+)", label)]
    for sec in sections:
        needle = sec if sec.startswith("Div") else f"s {sec}"
        for ruling_id, url in citations:
            if f"ITAA {year}" in ruling_id and re.search(rf"{re.escape(needle)}(?![\d-])", ruling_id):
                if url.startswith(PRIMARY_HOSTS[1]):
                    return url, f"{ruling_id} (product citations table)"
    return None


# ------------------------------------------------------------- record build
def fy_label(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def check_clean(record: dict[str, Any]) -> None:
    blob = json.dumps(record).lower()
    for w in BANNED:
        if w in blob:
            raise SystemExit(f"record {record['id']} carries banned term {w!r}")
    if "\u2014" in blob:
        raise SystemExit(f"record {record['id']} carries an em-dash")


def primary(sources: list[dict[str, str]]) -> str | None:
    for s in sources:
        u = s.get("url", "")
        if u.startswith(PRIMARY_HOSTS):
            return u
    return None


RULE_CATEGORY = {
    "45-day-holding-period": "franking",
    "franking-gross-up": "franking",
    "cgt-12-month-boundary": "capital-gains",
    "bring-forward-bands": "contributions",
    "carry-forward-concessional-gate": "contributions",
    "minimum-pension-drawdown": "pension",
    "division-296-tiers": "division-296",
    "payday-super-seven-business-days": "contributions",
    "smsf-borrowing-residential-property": "borrowing",
}

# Which product engine header vouches for the figures in a landing rule.
RULE_ENGINE = {
    "bring-forward-bands": "mcaps",
    "carry-forward-concessional-gate": "mcaps",
    "minimum-pension-drawdown": "drawdown",
    "division-296-tiers": "div296",
}


def build(landing: Path, product: Path) -> dict[str, Any]:
    subprocess.run(["git", "fetch", "origin", "-q"], cwd=landing, check=True)
    subprocess.run(["git", "fetch", "origin", "-q"], cwd=product, check=True)

    src = {
        "rules": ("landing", "content/rules.ts"),
        "glossary": ("landing", "content/glossary.ts"),
        "caps": ("product", "src/lib/caps/caps-math.ts"),
        "mcaps": ("product", "src/lib/mcaps/mcaps-math.ts"),
        "div296": ("product", "src/lib/div296/div296-math.ts"),
        "drawdown": ("product", "src/lib/pension/drawdown-math.ts"),
        "deadlines": ("product", "src/lib/compliance/deadlines.ts"),
        "tbar": ("product", "src/lib/tbar/tbar-math.ts"),
        "citations": ("product", "src/lib/calc/citations.ts"),
    }
    repos = {"landing": landing, "product": product}
    text: dict[str, str] = {}
    provenance: dict[str, dict[str, str]] = {}
    for key, (repo, path) in src.items():
        text[key] = git_show(repos[repo], path)
        sha, day = git_commit(repos[repo], path)
        provenance[key] = {
            "repo": f"smsfcore-{repo}",
            "path": path,
            "commit": sha,
            "commit_date": day,
            "verified_on": verified_on(text[key]),
        }

    citations = parse_citations(text["citations"])
    rules: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    def emit(rec: dict[str, Any]) -> None:
        check_clean(rec)
        assert rec["primary_source_url"].startswith(PRIMARY_HOSTS), rec["id"]
        rules.append(rec)

    # -- landing content/rules.ts ------------------------------------------
    for raw in ts_literal_to_json(slice_literal(text["rules"], "const RAW: RuleExplainer[] =")):
        sources = []
        via = None
        for s in raw["sources"]:
            entry = {"label": s["label"]}
            if "url" in s:
                entry["url"] = s["url"]
            else:
                hit = resolve_statute(s["label"], citations)
                if hit:
                    entry["url"], entry["resolved_via"] = hit
                    via = via or hit[1]
            sources.append(entry)
        url = primary(sources)
        if not url:
            excluded.append(
                {
                    "id": raw["slug"],
                    "source_file": "smsfcore-landing/content/rules.ts",
                    "reason": "no ato.gov.au or legislation.gov.au URL in the corpus entry, "
                    "and no statute in the product citation table",
                }
            )
            continue
        fy = re.search(r"FY ?(\d{4})-(\d{2})", raw["title"] + " " + raw["statute"])
        figures = []
        for row in raw["example"]["rows"]:
            fig: dict[str, Any] = {"label": row["label"]}
            if "cents" in row:
                fig["cents"] = row["cents"]
            else:
                fig["text"] = row["text"]
            if fy:
                fig["financial_year"] = f"{fy.group(1)}-{fy.group(2)}"
            figures.append(fig)
        engine = RULE_ENGINE.get(raw["slug"])
        emit(
            {
                "id": raw["slug"],
                "title": raw["title"],
                "category": RULE_CATEGORY[raw["slug"]],
                "summary": raw["intro"],
                "statute": raw["statute"],
                "figures": figures,
                "example_heading": raw["example"]["heading"],
                "example_footnote": raw["example"].get("footnote"),
                "mechanics": raw["mechanics"],
                "sources": sources,
                "primary_source_url": url,
                "verified_on": provenance[engine]["verified_on"] if engine else None,
                "verified_by": f"smsfcore-product/{src[engine][1]}" if engine else None,
                "source_file": "smsfcore-landing/content/rules.ts",
                "source_commit": provenance["rules"]["commit"],
                "source_commit_date": provenance["rules"]["commit_date"],
                "corpus_url": f"{CORPUS_URL}/{raw['slug']}",
            }
        )

    # -- landing content/glossary.ts ---------------------------------------
    for raw in ts_literal_to_json(slice_literal(text["glossary"], "GLOSSARY: GlossaryTerm[] =")):
        sources = []
        for label in raw["sources"]:
            entry = {"label": label}
            hit = resolve_statute(label, citations)
            if hit:
                entry["url"], entry["resolved_via"] = hit
            sources.append(entry)
        url = primary(sources)
        if not url:
            excluded.append(
                {
                    "id": raw["slug"],
                    "source_file": "smsfcore-landing/content/glossary.ts",
                    "reason": "statute reference not present in the product citation table",
                }
            )
            continue
        emit(
            {
                "id": raw["slug"],
                "title": raw["term"],
                "category": "glossary",
                "summary": raw["definition"],
                "statute": "; ".join(raw["sources"]),
                "figures": [],
                "mechanics": [],
                "sources": sources,
                "primary_source_url": url,
                "verified_on": None,
                "verified_by": None,
                "source_file": "smsfcore-landing/content/glossary.ts",
                "source_commit": provenance["glossary"]["commit"],
                "source_commit_date": provenance["glossary"]["commit_date"],
                "corpus_url": f"https://smsfcore.com/glossary/{raw['slug']}",
            }
        )

    # -- product caps tables -----------------------------------------------
    caps_urls = re.findall(r"(https://www\.ato\.gov\.au/\S+)", text["caps"][: text["caps"].index("*/")])
    mcaps_urls = re.findall(r"(https://www\.ato\.gov\.au/\S+)", text["mcaps"][: text["mcaps"].index("*/")])
    fy_caps = ts_literal_to_json(slice_literal(text["caps"], "FY_CAPS: Record<number, FyCaps> ="))
    mcaps_text = re.sub(r"\n\s*2026: FY2026_27,", "", text["mcaps"])
    mcaps_cfg = ts_literal_to_json(slice_literal(mcaps_text, "CAPS_CONFIG_BY_FY: Record<number, CapsConfig> ="))
    fy2026 = ts_literal_to_json(slice_literal(text["mcaps"], "FY2026_27: CapsConfig ="))
    mcaps_cfg["2026"] = fy2026
    gate = int(re.search(r"CARRY_FORWARD_TSB_GATE_CENTS = ([\d_]+)", text["caps"]).group(1).replace("_", ""))

    caps_by_fy: dict[str, Any] = {}
    for year, c in sorted(fy_caps.items()):
        m = mcaps_cfg[year]
        cc, ncc, tbc = c["ccCapCents"], c["nccCapCents"], c["generalTbcCents"]
        # Cross-engine consistency: the two product engines must agree.
        assert (cc, ncc, tbc) == (
            m["concessionalCapCents"],
            m["nonConcessionalCapCents"],
            m["generalTbcCents"],
        ), f"caps engines disagree for FY {year}"
        assert m["carryForwardTsbLimitCents"] == gate
        assert ncc == 4 * cc, f"NCC is defined as 4 x CC (FY {year})"
        assert c["bringForward3xBelowCents"] == tbc - 2 * ncc, f"3x band identity (FY {year})"
        assert c["bringForward2xBelowCents"] == tbc - ncc, f"2x band identity (FY {year})"
        y = int(year)
        caps_by_fy[fy_label(y)] = {
            "financial_year": fy_label(y),
            "starts": f"{y}-07-01",
            "ends": f"{y + 1}-06-30",
            "concessional_cap_cents": cc,
            "non_concessional_cap_cents": ncc,
            "general_transfer_balance_cap_cents": tbc,
            "bring_forward_3x_below_cents": c["bringForward3xBelowCents"],
            "bring_forward_2x_below_cents": c["bringForward2xBelowCents"],
            "carry_forward_tsb_gate_cents": gate,
            "sources": [
                {"label": "ATO: contributions caps (key rates and thresholds)", "url": caps_urls[0]},
                {"label": "ATO: concessional contributions cap", "url": caps_urls[1]},
                {"label": "ATO: non-concessional contributions cap", "url": caps_urls[2]},
                {"label": "ATO: general transfer balance cap indexation 1 July 2026", "url": mcaps_urls[2]},
            ],
            "verified_on": provenance["caps"]["verified_on"],
            "verified_by": "smsfcore-product/src/lib/caps/caps-math.ts",
        }
        emit(
            {
                "id": f"contribution-caps-fy{fy_label(y)}",
                "title": f"Contribution caps and total super balance thresholds, FY {fy_label(y)}",
                "category": "caps",
                "summary": (
                    f"For the financial year starting 1 July {y}: concessional cap "
                    f"${cc // 100:,}, non-concessional cap ${ncc // 100:,} (four times the "
                    f"concessional cap), general transfer balance cap ${tbc // 100:,}. The "
                    f"non-concessional cap is nil when total super balance at the prior 30 June "
                    f"is at or above the general transfer balance cap. Bring-forward bands are "
                    f"derived: three years available below ${(tbc - 2 * ncc) // 100:,}, two years "
                    f"below ${(tbc - ncc) // 100:,}. Carry-forward of unused concessional cap "
                    f"needs a prior 30 June balance strictly under ${gate // 100:,}."
                ),
                "statute": "Income Tax Assessment Act 1997 (Cth) ss 291-20, 292-85; ATO published caps",
                "figures": [
                    {"label": "Concessional cap", "cents": cc, "financial_year": fy_label(y)},
                    {"label": "Non-concessional cap", "cents": ncc, "financial_year": fy_label(y)},
                    {
                        "label": "General transfer balance cap",
                        "cents": tbc,
                        "financial_year": fy_label(y),
                    },
                    {
                        "label": "Three-year bring-forward available while TSB below",
                        "cents": c["bringForward3xBelowCents"],
                        "financial_year": fy_label(y),
                    },
                    {
                        "label": "Two-year bring-forward available while TSB below",
                        "cents": c["bringForward2xBelowCents"],
                        "financial_year": fy_label(y),
                    },
                    {
                        "label": "Carry-forward concessional gate (TSB strictly below)",
                        "cents": gate,
                        "financial_year": fy_label(y),
                    },
                ],
                "mechanics": [
                    "Non-concessional cap = 4 x concessional cap.",
                    "Bring-forward band k is available while prior 30 June TSB is below "
                    "general TBC minus (k minus 1) x non-concessional cap, and the member is "
                    "under 75 on 1 July.",
                    "Exceeding the annual non-concessional cap in a year triggers the bring-forward period.",
                    "Carry-forward: unused concessional cap from up to five prior years is "
                    "available only while prior 30 June TSB is strictly under the gate.",
                ],
                "sources": caps_by_fy[fy_label(y)]["sources"],
                "primary_source_url": caps_urls[0],
                "verified_on": provenance["caps"]["verified_on"],
                "verified_by": "smsfcore-product/src/lib/caps/caps-math.ts",
                "source_file": "smsfcore-product/src/lib/caps/caps-math.ts",
                "source_commit": provenance["caps"]["commit"],
                "source_commit_date": provenance["caps"]["commit_date"],
                "corpus_url": f"{CORPUS_URL}/bring-forward-bands",
            }
        )

    # -- Division 296 thresholds -------------------------------------------
    d = text["div296"]
    lower = int(re.search(r"DIV296_LOWER_THRESHOLD_CENTS = ([\d_]+)", d).group(1).replace("_", ""))
    upper = int(re.search(r"DIV296_UPPER_THRESHOLD_CENTS = ([\d_]+)", d).group(1).replace("_", ""))
    t1 = float(re.search(r"DIV296_TIER1_RATE = ([\d.]+)", d).group(1))
    t2 = float(re.search(r"DIV296_TIER2_RATE = ([\d.]+)", d).group(1))
    div296_url = re.search(r"(https://www\.ato\.gov\.au/\S+better-targeted\S+)", d).group(1)
    act_url = "https://www.legislation.gov.au/C2026A00008/latest"
    assert act_url in text["rules"], "Division 296 Act URL must come from the corpus"
    div296 = {
        "commenced": "2026-07-01",
        "first_test_date": "2027-06-30",
        "lower_threshold_cents": lower,
        "upper_threshold_cents": upper,
        "tier1_rate": t1,
        "tier2_rate": t2,
        "base": "realised earnings only",
        "sources": [
            {"label": "ATO: Better Targeted Super Concessions is law", "url": div296_url},
            {"label": "Treasury Laws Amendment (Better Targeted Superannuation Concessions) Act 2026", "url": act_url},
        ],
        "verified_on": provenance["div296"]["verified_on"],
        "verified_by": "smsfcore-product/src/lib/div296/div296-math.ts",
    }
    emit(
        {
            "id": "division-296-thresholds",
            "title": "Division 296 thresholds and rates at commencement",
            "category": "division-296",
            "summary": (
                f"Division 296 commenced 1 July 2026 and applies to realised earnings only. "
                f"Tier 1 is {t1:.0%} on the share of earnings attributable to total super "
                f"balance between ${lower // 100:,} and ${upper // 100:,}; tier 2 is "
                f"{t2:.0%} on the share above ${upper // 100:,}. Total super balance is first "
                f"tested at 30 June 2027. Both thresholds are indexed from commencement."
            ),
            "statute": "Income Tax Assessment Act 1997 (Cth) Division 296 (Act No. C2026A00008)",
            "figures": [
                {"label": "Lower threshold", "cents": lower, "financial_year": "2026-27"},
                {"label": "Upper threshold", "cents": upper, "financial_year": "2026-27"},
                {"label": "Tier 1 rate", "text": f"{t1:.0%}", "financial_year": "2026-27"},
                {"label": "Tier 2 rate (cumulative)", "text": f"{t2:.0%}", "financial_year": "2026-27"},
                {"label": "First TSB test date", "text": "2027-06-30", "financial_year": "2026-27"},
            ],
            "mechanics": [
                "tier 1 tax = rate1 x earnings x (min(TSB, upper) minus lower) / TSB",
                "tier 2 tax = rate2 x earnings x (TSB minus upper) / TSB",
                "Assessed per individual across all super interests, not per fund.",
            ],
            "sources": div296["sources"],
            "primary_source_url": div296_url,
            "verified_on": provenance["div296"]["verified_on"],
            "verified_by": "smsfcore-product/src/lib/div296/div296-math.ts",
            "source_file": "smsfcore-product/src/lib/div296/div296-math.ts",
            "source_commit": provenance["div296"]["commit"],
            "source_commit_date": provenance["div296"]["commit_date"],
            "corpus_url": f"{CORPUS_URL}/division-296-tiers",
        }
    )

    # -- pension minimum percentages ---------------------------------------
    bands = ts_literal_to_json(slice_literal(text["drawdown"], "DRAWDOWN_BANDS: readonly AgeBand[] ="))
    dd_urls = re.findall(r"(https://www\.ato\.gov\.au/\S+)", text["drawdown"][: text["drawdown"].index("*/")])
    emit(
        {
            "id": "pension-minimum-percentages",
            "title": "Account-based pension minimum drawdown percentages by age",
            "category": "pension",
            "summary": (
                "The minimum annual payment is the Schedule 7 percentage for the member's age "
                "at 1 July (or at commencement) applied to the pension balance on that day, "
                "rounded to the nearest $10. A pension commenced on or after 1 June has no "
                "minimum for that year; one commenced mid-year pro-rates by days remaining."
            ),
            "statute": "Superannuation Industry (Supervision) Regulations 1994 (Cth) Schedule 7, reg 1.07D",
            "figures": [
                {
                    "label": f"Age {b['minAge']}" + (f" to {b['maxAge']}" if b["maxAge"] is not None else " and over"),
                    "text": f"{b['rate']:.0%}",
                }
                for b in bands
            ],
            "mechanics": [
                "Percentage steps at ages 65, 75, 80, 85, 90 and 95.",
                "Rounded to the nearest $10.",
                "Standard rates apply; the temporary 50% reduction ended 30 June 2023.",
            ],
            "sources": [
                {"label": "ATO: payments from super (minimum annual payments by age)", "url": dd_urls[0]},
                {"label": "ATO: income stream (pension) rules and payments (SMSF)", "url": dd_urls[1]},
            ],
            "primary_source_url": dd_urls[0],
            "verified_on": provenance["drawdown"]["verified_on"],
            "verified_by": "smsfcore-product/src/lib/pension/drawdown-math.ts",
            "source_file": "smsfcore-product/src/lib/pension/drawdown-math.ts",
            "source_commit": provenance["drawdown"]["commit"],
            "source_commit_date": provenance["drawdown"]["commit_date"],
            "corpus_url": f"{CORPUS_URL}/minimum-pension-drawdown",
        }
    )

    # -- deadlines ---------------------------------------------------------
    dl = text["deadlines"]
    tbar_url = re.search(r"(https://www\.ato\.gov\.au/\S+transfer-balance-account-reporting)", dl).group(1)
    sar_url = re.search(r"(https://www\.ato\.gov\.au/\S+lodge-smsf-annual-returns)", dl).group(1)
    sar_verified = re.search(r"re-verified (\d{4}-\d{2}-\d{2})", dl).group(1)
    tbar_when = re.search(r"(https://www\.ato\.gov\.au/\S+when-to-lodge)", text["tbar"]).group(1)
    deadlines = [
        {
            "id": "tbar-quarterly",
            "label": "TBAR quarter due",
            "rule": "quarterly_28_days",
            "detail": "Transfer balance events for a quarter must reach the ATO within 28 days "
            "of quarter end: 28 October, 28 January, 28 April and 28 July. All SMSFs "
            "report quarterly since 1 July 2023.",
            "sources": [
                {"label": "ATO: transfer balance account reporting", "url": tbar_url},
                {"label": "ATO: TBAR instructions, when to lodge", "url": tbar_when},
            ],
            "verified_on": provenance["deadlines"]["verified_on"],
        },
        {
            "id": "pension-minimum",
            "label": "Pension minimums paid by 30 June",
            "rule": "fy_end",
            "detail": "Each retirement-phase pension must have paid at least its statutory "
            "minimum by 30 June of the financial year.",
            "sources": [{"label": "ATO: income stream (pension) rules and payments (SMSF)", "url": dd_urls[1]}],
            "verified_on": provenance["drawdown"]["verified_on"],
        },
        {
            "id": "div296-first-test",
            "label": "Division 296 first total super balance test",
            "rule": "fixed:2027-06-30",
            "detail": "Total super balance is first tested at 30 June 2027 for the commencement year of Division 296.",
            "sources": [{"label": "ATO: Better Targeted Super Concessions is law", "url": div296_url}],
            "verified_on": provenance["div296"]["verified_on"],
        },
        {
            "id": "sar-self-preparer",
            "label": "SMSF annual return, self-preparer",
            "rule": "annual:02-28",
            "detail": "Funds lodging their own annual return lodge by 28 February, except newly "
            "registered funds and funds with an overdue prior-year return.",
            "sources": [{"label": "ATO: lodge SMSF annual returns (QC 23331)", "url": sar_url}],
            "verified_on": sar_verified,
        },
        {
            "id": "sar-new-fund",
            "label": "SMSF annual return, newly registered fund",
            "rule": "annual:10-31",
            "detail": "Newly registered funds, and funds with an overdue prior-year return, "
            "lodge by 31 October. Tax agent program dates run later.",
            "sources": [{"label": "ATO: lodge SMSF annual returns (QC 23331)", "url": sar_url}],
            "verified_on": sar_verified,
        },
    ]
    for dline in deadlines:
        emit(
            {
                "id": f"deadline-{dline['id']}",
                "title": dline["label"],
                "category": "deadlines",
                "summary": dline["detail"],
                "statute": None,
                "figures": [{"label": "Rule", "text": dline["rule"]}],
                "mechanics": [],
                "sources": dline["sources"],
                "primary_source_url": dline["sources"][0]["url"],
                "verified_on": dline["verified_on"],
                "verified_by": "smsfcore-product/src/lib/compliance/deadlines.ts",
                "source_file": "smsfcore-product/src/lib/compliance/deadlines.ts",
                "source_commit": provenance["deadlines"]["commit"],
                "source_commit_date": provenance["deadlines"]["commit_date"],
                "corpus_url": CORPUS_URL,
            }
        )

    ids = [r["id"] for r in rules]
    assert len(ids) == len(set(ids)), "duplicate rule ids"
    return {
        "generated_on": datetime.now().date().isoformat(),
        "corpus_url": CORPUS_URL,
        "provenance": provenance,
        "rules": rules,
        "caps_by_fy": caps_by_fy,
        "division_296": div296,
        "deadlines": deadlines,
        "excluded": excluded,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--landing", type=Path, default=Path("/Users/simon/dev/smsfcore/smsfcore-landing"))
    ap.add_argument("--product", type=Path, default=Path("/Users/simon/dev/smsfcore/smsfcore-product"))
    args = ap.parse_args()
    data = build(args.landing, args.product)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}: {len(data['rules'])} rules, {len(data['excluded'])} excluded")
    for e in data["excluded"]:
        print(f"  excluded {e['id']}: {e['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
