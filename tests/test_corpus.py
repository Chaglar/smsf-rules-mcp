"""Every record in rules.json carries a primary source; searches and lookups work."""

import json
from pathlib import Path

from smsf_rules_mcp.data import categories, citation, corpus, rules_by_id, search

PRIMARY = ("https://www.ato.gov.au/", "https://www.legislation.gov.au/")


def test_every_rule_has_primary_source_and_provenance():
    for r in corpus()["rules"]:
        assert r["primary_source_url"].startswith(PRIMARY), r["id"]
        assert any(s.get("url") == r["primary_source_url"] for s in r["sources"]), r["id"]
        assert r["source_file"] and r["source_commit"] and r["source_commit_date"], r["id"]
        assert r["summary"] and r["title"] and r["category"], r["id"]


def test_rule_ids_unique_and_counts():
    ids = [r["id"] for r in corpus()["rules"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 22
    assert {e["id"] for e in corpus()["excluded"]} == {
        "smsf-borrowing-residential-property",
        "cgt-12-month-boundary",
        "payday-super-seven-business-days",
    }


def test_categories():
    assert categories() == ["caps", "contributions", "deadlines", "division-296", "franking", "glossary", "pension"]


def test_figures_are_integer_cents():
    for r in corpus()["rules"]:
        for f in r["figures"]:
            if "cents" in f:
                assert isinstance(f["cents"], int) and not isinstance(f["cents"], bool), (r["id"], f)


def test_search_token_match():
    hits = search("bring-forward transfer balance cap")
    assert hits and hits[0][1]["id"] in {"bring-forward-bands", "contribution-caps-fy2026-27"}
    assert search("") == []
    assert search("zzzzqqqq") == []


def test_citation_text_cites_source():
    text = citation(rules_by_id()["division-296-tiers"])
    assert "https://www.legislation.gov.au/C2026A00008/latest" in text
    assert "$15,000,000.00" in text
    assert text.endswith("General information about the rules, not a licensed financial service.")


def test_rules_json_is_committed_and_matches_loaded_corpus():
    on_disk = json.loads(Path("src/smsf_rules_mcp/rules.json").read_text(encoding="utf-8"))
    assert on_disk["rules"] == corpus()["rules"]
