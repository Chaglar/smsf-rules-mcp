"""MCP server exposing the SMSF Core rules corpus as read-only tools and resources.

Everything is deterministic and local: no model calls and no network at call time.
General information about the rules, not a licensed financial service.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from . import __version__
from .caps import caps_summary, contribution_headroom
from .data import categories, citation, corpus, rules_by_id, search
from .dates import days_until

NOTICE = "General information about the rules, not a licensed financial service."

mcp = MCPServer(
    name="smsf-rules-mcp",
    version=__version__,
    instructions=(
        "Read-only tools over the Australian SMSF rules corpus published at "
        "smsfcore.com/rules: contribution caps, total super balance thresholds, "
        "Division 296 thresholds, pension minimums and lodgment deadlines, each with "
        "an ato.gov.au or legislation.gov.au citation. Money is integer cents. " + NOTICE
    ),
)


def _brief(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rule["id"],
        "title": rule["title"],
        "category": rule["category"],
        "primary_source_url": rule["primary_source_url"],
        "verified_on": rule.get("verified_on"),
    }


@mcp.tool()
def list_rules(category: str | None = None) -> dict[str, Any]:
    """List the rules in the corpus, optionally filtered by category.

    Categories: caps, contributions, deadlines, division-296, franking, glossary, pension.
    General information about the rules, not a licensed financial service.
    """
    rules = corpus()["rules"]
    if category:
        if category not in categories():
            raise ToolError(f"unknown category {category!r}; known: {', '.join(categories())}")
        rules = [r for r in rules if r["category"] == category]
    return {"count": len(rules), "categories": categories(), "rules": [_brief(r) for r in rules]}


@mcp.tool()
def get_rule(id: str) -> dict[str, Any]:
    """Return one rule in full: summary, figures in cents, mechanics, sources and provenance.

    General information about the rules, not a licensed financial service.
    """
    rule = rules_by_id().get(id)
    if rule is None:
        raise ToolError(f"no rule with id {id!r}; use list_rules or search_rules")
    return {**rule, "citation_text": citation(rule), "notice": NOTICE}


@mcp.tool()
def search_rules(query: str) -> dict[str, Any]:
    """Find rules whose text contains the query's words (simple token match, ranked by hits).

    General information about the rules, not a licensed financial service.
    """
    hits = search(query)
    return {
        "query": query,
        "count": len(hits),
        "results": [{"score": s, **_brief(r), "summary": r["summary"]} for s, r in hits],
    }


@mcp.tool()
def caps(financial_year: str) -> dict[str, Any]:
    """Caps and thresholds for one financial year, e.g. "2026-27": concessional and
    non-concessional caps, bring-forward bands, general transfer balance cap, total super
    balance gates and Division 296 thresholds, each with its source.

    General information about the rules, not a licensed financial service.
    """
    try:
        return caps_summary(financial_year)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(name="days_until")
def days_until_tool(target: str, now: str | None = None) -> dict[str, Any]:
    """Days from today on the Australia/Sydney calendar to a deadline id (tbar-quarterly,
    pension-minimum, div296-first-test, sar-self-preparer, sar-new-fund) or a YYYY-MM-DD
    date. `now` may be an ISO 8601 datetime with offset (converted to Sydney) or a date.

    General information about the rules, not a licensed financial service.
    """
    try:
        return days_until(target, now)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(name="contribution_headroom")
def contribution_headroom_tool(
    financial_year: str,
    age_at_1_july: int,
    total_super_balance_cents: int,
    concessional_ytd_cents: int,
    non_concessional_ytd_cents: int,
    unused_concessional_cents: int = 0,
) -> dict[str, Any]:
    """Remaining room under the concessional and non-concessional caps from the figures
    given, with each rule applied listed and cited. Integer cents in and out; no division,
    so nothing is rounded. Total super balance is the prior 30 June figure.

    General information about the rules, not a licensed financial service.
    """
    try:
        return contribution_headroom(
            financial_year,
            age_at_1_july,
            total_super_balance_cents,
            concessional_ytd_cents,
            non_concessional_ytd_cents,
            unused_concessional_cents,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.resource("rules://index", mime_type="text/plain")
def rules_index() -> str:
    """Index of every rule id with its title, category and primary source."""
    lines = [f"SMSF rules corpus ({corpus()['corpus_url']}), {len(corpus()['rules'])} rules", ""]
    for r in corpus()["rules"]:
        lines.append(f"{r['id']}  [{r['category']}]  {r['title']}  <{r['primary_source_url']}>")
    lines += ["", NOTICE]
    return "\n".join(lines)


@mcp.resource("rule://{id}", mime_type="text/plain")
def rule_text(id: str) -> str:
    """One rule as plain text with figures, mechanics and citation."""
    rule = rules_by_id().get(id)
    if rule is None:
        raise ResourceError(f"no rule with id {id!r}")
    return citation(rule)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
