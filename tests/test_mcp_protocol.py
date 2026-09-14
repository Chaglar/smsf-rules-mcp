"""MCP protocol smoke test through the SDK's in-process client."""

import json

from mcp import Client

from smsf_rules_mcp.server import mcp

EXPECTED_TOOLS = {"list_rules", "get_rule", "search_rules", "caps", "days_until", "contribution_headroom"}
NOTICE = "General information about the rules, not a licensed financial service."


async def test_list_tools_and_descriptions():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools.tools}
    assert names == EXPECTED_TOOLS
    for t in tools.tools:
        assert t.description and t.description.strip().endswith(NOTICE), t.name


async def test_call_caps_tool():
    async with Client(mcp) as client:
        result = await client.call_tool("caps", {"financial_year": "2026-27"})
    assert not result.is_error
    data = result.structured_content or json.loads(result.content[0].text)
    assert data["concessional_cap_cents"] == 3_250_000
    assert data["division_296"]["lower_threshold_cents"] == 300_000_000


async def test_call_headroom_and_days_until():
    async with Client(mcp) as client:
        h = await client.call_tool(
            "contribution_headroom",
            {
                "financial_year": "2026-27",
                "age_at_1_july": 60,
                "total_super_balance_cents": 1_850_000_00,
                "concessional_ytd_cents": 0,
                "non_concessional_ytd_cents": 0,
            },
        )
        d = await client.call_tool("days_until", {"target": "pension-minimum", "now": "2026-06-29T16:00:00Z"})
    assert h.structured_content["non_concessional"]["band"] == "2x"
    assert d.structured_content["days"] == 0


async def test_tool_error_is_reported_not_raised():
    async with Client(mcp) as client:
        result = await client.call_tool("get_rule", {"id": "no-such-rule"})
    assert result.is_error


async def test_resources():
    async with Client(mcp) as client:
        listed = await client.list_resources()
        index = await client.read_resource("rules://index")
        rule = await client.read_resource("rule://bring-forward-bands")
    assert any(str(r.uri) == "rules://index" for r in listed.resources)
    assert "bring-forward-bands" in index.contents[0].text
    assert "https://www.ato.gov.au/" in rule.contents[0].text
