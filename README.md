# smsf-rules-mcp

An MCP server that answers questions about Australian SMSF contribution caps, total super balance thresholds, Division 296 thresholds, pension minimums and lodgment deadlines, with an ato.gov.au or legislation.gov.au citation on every answer.

It is read-only and deterministic: no model calls, no network at call time. The data is a single `rules.json` generated from the TypeScript corpus behind [smsfcore.com/rules](https://smsfcore.com/rules), and every record carries a primary source URL, the file and commit it came from, and the date the figures were last verified against the ATO page.

General information about the rules, not a licensed financial service.

## Install

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is fetched automatically).

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "smsf-rules": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Chaglar/smsf-rules-mcp", "smsf-rules-mcp"]
    }
  }
}
```

### Claude Code

```sh
claude mcp add smsf-rules -- uvx --from git+https://github.com/Chaglar/smsf-rules-mcp smsf-rules-mcp
```

### From a checkout

```sh
git clone https://github.com/Chaglar/smsf-rules-mcp
cd smsf-rules-mcp
uv sync
uv run smsf-rules-mcp        # stdio transport
uv run pytest                # 61 tests
```

## Tools

Money is integer cents everywhere. The cap arithmetic is adds, subtracts, small integer multiples and comparisons, so nothing is ever rounded.

| Tool | What it returns | Example call |
| --- | --- | --- |
| `list_rules(category?)` | Every rule id with title, category, primary source and verified date. Categories: caps, contributions, deadlines, division-296, franking, glossary, pension. | `list_rules(category="contributions")` |
| `get_rule(id)` | One rule in full: summary, figures in cents with financial year, mechanics, sources, provenance, plus a plain-text citation block. | `get_rule(id="bring-forward-bands")` |
| `search_rules(query)` | Simple token match over id, title, summary, mechanics and source labels, ranked by distinct hits. | `search_rules(query="carry forward 500,000 gate")` |
| `caps(financial_year)` | Concessional and non-concessional caps, bring-forward bands and totals, general transfer balance cap, TSB gates and Division 296 thresholds for that year, each with sources. | `caps(financial_year="2026-27")` |
| `days_until(target, now?)` | Days from today on the Australia/Sydney calendar to a deadline id (`tbar-quarterly`, `pension-minimum`, `div296-first-test`, `sar-self-preparer`, `sar-new-fund`) or a `YYYY-MM-DD` date. `now` accepts an ISO datetime with offset, converted to Sydney. | `days_until(target="pension-minimum", now="2026-06-29T16:00:00Z")` gives `days: 0` because it is already 30 June in Sydney |
| `contribution_headroom(...)` | Remaining room and excess under each cap from the figures supplied, the band reached, whether a bring-forward period was triggered, and the list of rules applied with citations. | `contribution_headroom(financial_year="2026-27", age_at_1_july=60, total_super_balance_cents=48000000, concessional_ytd_cents=1000000, non_concessional_ytd_cents=15000000, unused_concessional_cents=2000000)` |

`contribution_headroom` applies, in order: the carry-forward gate (prior 30 June TSB strictly under $500,000 adds `unused_concessional_cents` to the concessional cap), the bring-forward band from TSB (three years below general TBC minus two annual caps, two years below TBC minus one, annual cap only below TBC, nil at or above), the age condition (under 75 on 1 July for any bring-forward), and the trigger test (non-concessional contributions above the annual cap start the period). Contributions from earlier years of an already running period are not modelled; pass the period total as `non_concessional_ytd_cents`.

## Resources

- `rules://index` lists every rule id, category, title and primary source.
- `rule://{id}` returns one rule as plain text with figures, mechanics and citation, for example `rule://division-296-tiers`.

## Data provenance

`scripts/extract_rules.py` reads the sources with `git show origin/main:<path>` and writes `src/smsf_rules_mcp/rules.json`. It parses the TypeScript literals, copies URLs from source comments and the product citation table, asserts the cross-engine identities (non-concessional cap = 4 x concessional; bring-forward band ceilings = general TBC minus k x non-concessional cap; the two product cap engines agree on every year) and refuses to emit any record that lacks an ato.gov.au or legislation.gov.au URL or carries banned vocabulary.

| Source file | What it supplies | Figures verified against the ATO page |
| --- | --- | --- |
| smsfcore-landing `content/rules.ts` | Rule explainers: title, summary, worked example, mechanics, sources | via the product engines below (commit 42007ea, 2026-08-24) |
| smsfcore-landing `content/glossary.ts` | Franking glossary terms with statute references | commit 11effe7, 2026-08-08 |
| smsfcore-product `src/lib/caps/caps-math.ts` | Contribution caps, bring-forward bands and general TBC for FY 2024-25, 2025-26, 2026-27; carry-forward gate | 2026-07-07 |
| smsfcore-product `src/lib/mcaps/mcaps-math.ts` | Cross-check of the same caps; general TBC indexation source | 2026-07-11 |
| smsfcore-product `src/lib/div296/div296-math.ts` | Division 296 thresholds and rates | 2026-07-06 |
| smsfcore-product `src/lib/pension/drawdown-math.ts` | Minimum drawdown percentages by age | 2026-07-07 |
| smsfcore-product `src/lib/compliance/deadlines.ts` | TBAR quarterly, pension minimum, Division 296 first test and SAR lodgment dates | 2026-07-10; SAR dates re-verified 2026-08-29 |
| smsfcore-product `src/lib/tbar/tbar-math.ts` | TBAR "when to lodge" source | 2026-07-16 |
| smsfcore-product `src/lib/calc/citations.ts` | Statute reference to legislation.gov.au URL table, used to resolve glossary and holding-period statutes | commit 1dd5319, 2026-09-10 |

Glossary records and the 45-day holding period rule carry legislation.gov.au URLs resolved by section number from the product citation table; each such source is marked `resolved_via` in `rules.json`. Records without a product engine behind them show `verified_on: null` and rely on the corpus commit date.

### Rules included (22)

45-day-holding-period, franking-gross-up, bring-forward-bands, carry-forward-concessional-gate, minimum-pension-drawdown, division-296-tiers, 45-day-holding-period-rule, franking-credit, lifo-disposal-tracing, ecpi, trans-tasman-imputation, qualified-person, contribution-caps-fy2024-25, contribution-caps-fy2025-26, contribution-caps-fy2026-27, division-296-thresholds, pension-minimum-percentages, deadline-tbar-quarterly, deadline-pension-minimum, deadline-div296-first-test, deadline-sar-self-preparer, deadline-sar-new-fund.

### Rules excluded (3)

These exist in the corpus but their sources are statute labels without a URL, and the product citation table has no entry for the section, so the extractor leaves them out rather than attach a URL nobody verified:

- `smsf-borrowing-residential-property` (SIS Act s 67A as amended by Act No. 49 of 2026)
- `cgt-12-month-boundary` (ITAA 1997 ss 115-25, 115-100)
- `payday-super-seven-business-days` (Payday Superannuation Act timing rules)

They return when a verified ato.gov.au or legislation.gov.au URL is added to the corpus and the extractor is re-run.

## Regenerating the data

```sh
uv run python scripts/extract_rules.py --landing ../smsfcore-landing --product ../smsfcore-product
uv run pytest
```

## Development

`uv sync`, then `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest`. CI runs the same three on every push and pull request. `tests/test_language.py` sweeps the whole repository for the vocabulary the server must never use and for em-dashes.

## License

MIT. Built by Fatih Gurcaglar; the rules corpus is the one behind smsfcore.com/rules.
