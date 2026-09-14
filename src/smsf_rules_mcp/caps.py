"""Contribution cap arithmetic in integer cents.

Every step is an add, subtract, multiply by a small integer, or a comparison.
No division happens anywhere in this module, so no rounding rule is needed.
"""

from __future__ import annotations

from typing import Any

from .data import caps_for_fy, corpus, rules_by_id

BRING_FORWARD_AGE_LIMIT = 75  # under 75 on 1 July of the financial year


def caps_summary(financial_year: str | int) -> dict[str, Any]:
    c = caps_for_fy(financial_year)
    fy = c["financial_year"]
    ncc = c["non_concessional_cap_cents"]
    tbc = c["general_transfer_balance_cap_cents"]
    div = corpus()["division_296"]
    div_applies = fy >= "2026-27"
    return {
        "financial_year": fy,
        "starts": c["starts"],
        "ends": c["ends"],
        "concessional_cap_cents": c["concessional_cap_cents"],
        "non_concessional_cap_cents": ncc,
        "bring_forward": {
            "three_year_total_cents": 3 * ncc,
            "three_year_available_while_tsb_below_cents": c["bring_forward_3x_below_cents"],
            "two_year_total_cents": 2 * ncc,
            "two_year_available_while_tsb_below_cents": c["bring_forward_2x_below_cents"],
            "annual_cap_only_while_tsb_below_cents": tbc,
            "nil_at_or_above_cents": tbc,
            "age_condition": f"under {BRING_FORWARD_AGE_LIMIT} on 1 July {fy[:4]}",
        },
        "general_transfer_balance_cap_cents": tbc,
        "total_super_balance_thresholds": {
            "carry_forward_concessional_gate_cents": c["carry_forward_tsb_gate_cents"],
            "carry_forward_gate_test": "prior 30 June TSB strictly below the gate",
            "non_concessional_nil_at_or_above_cents": tbc,
            "measurement_date": f"30 June {fy[:4]} (the 30 June before the year starts)",
        },
        "division_296": (
            {
                "lower_threshold_cents": div["lower_threshold_cents"],
                "upper_threshold_cents": div["upper_threshold_cents"],
                "tier1_rate": div["tier1_rate"],
                "tier2_rate": div["tier2_rate"],
                "base": div["base"],
                "first_test_date": div["first_test_date"],
                "sources": div["sources"],
                "verified_on": div["verified_on"],
            }
            if div_applies
            else {
                "applies": False,
                "note": f"Division 296 commenced {div['commenced']}; no thresholds for FY {fy}.",
            }
        ),
        "sources": c["sources"],
        "verified_on": c["verified_on"],
        "verified_by": c["verified_by"],
        "rule_ids": [f"contribution-caps-fy{fy}", "bring-forward-bands", "carry-forward-concessional-gate"]
        + (["division-296-thresholds"] if div_applies else []),
        "notice": "General information about the rules, not a licensed financial service.",
    }


def _non_negative(name: str, value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer number of cents")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


def contribution_headroom(
    financial_year: str | int,
    age_at_1_july: int,
    total_super_balance_cents: int,
    concessional_ytd_cents: int,
    non_concessional_ytd_cents: int,
    unused_concessional_cents: int = 0,
) -> dict[str, Any]:
    """Remaining room under each cap from the figures supplied. All cents."""
    c = caps_for_fy(financial_year)
    fy = c["financial_year"]
    tsb = _non_negative("total_super_balance_cents", total_super_balance_cents)
    cc_ytd = _non_negative("concessional_ytd_cents", concessional_ytd_cents)
    ncc_ytd = _non_negative("non_concessional_ytd_cents", non_concessional_ytd_cents)
    unused = _non_negative("unused_concessional_cents", unused_concessional_cents)
    if not isinstance(age_at_1_july, int) or age_at_1_july < 0 or age_at_1_july > 130:
        raise ValueError("age_at_1_july must be a whole number of years")

    cc_cap = c["concessional_cap_cents"]
    ncc_cap = c["non_concessional_cap_cents"]
    tbc = c["general_transfer_balance_cap_cents"]
    gate = c["carry_forward_tsb_gate_cents"]
    applied: list[str] = []

    # Concessional: cap plus carry-forward if the TSB gate is passed (strict <).
    gate_passed = tsb < gate
    applied.append(
        f"Carry-forward gate: TSB {tsb:,} cents is "
        f"{'below' if gate_passed else 'not below'} {gate:,} cents, so unused prior-year "
        f"concessional cap is {'added' if gate_passed else 'not added'} [carry-forward-concessional-gate]."
    )
    cc_effective = cc_cap + (unused if gate_passed else 0)
    cc_remaining = max(0, cc_effective - cc_ytd)
    cc_excess = max(0, cc_ytd - cc_effective)

    # Non-concessional: band from TSB, then the age condition, then the trigger.
    if tsb >= tbc:
        band, multiplier = "nil", 0
        applied.append(
            f"TSB at or above the general transfer balance cap ({tbc:,} cents): "
            "non-concessional cap for the year is nil [bring-forward-bands]."
        )
    elif tsb < c["bring_forward_3x_below_cents"]:
        band, multiplier = "3x", 3
        applied.append(
            f"TSB below {c['bring_forward_3x_below_cents']:,} cents: three-year bring-forward "
            "band [bring-forward-bands]."
        )
    elif tsb < c["bring_forward_2x_below_cents"]:
        band, multiplier = "2x", 2
        applied.append(
            f"TSB below {c['bring_forward_2x_below_cents']:,} cents: two-year bring-forward band [bring-forward-bands]."
        )
    else:
        band, multiplier = "1x", 1
        applied.append(
            f"TSB at or above {c['bring_forward_2x_below_cents']:,} cents and below the general "
            "transfer balance cap: annual cap only [bring-forward-bands]."
        )
    age_ok = age_at_1_july < BRING_FORWARD_AGE_LIMIT
    if not age_ok and multiplier > 1:
        applied.append(
            f"Age {age_at_1_july} at 1 July is not under {BRING_FORWARD_AGE_LIMIT}: bring-forward "
            "not available, annual cap only [bring-forward-bands]."
        )
        band, multiplier = "1x", 1
    ncc_max = multiplier * ncc_cap
    ncc_remaining = max(0, ncc_max - ncc_ytd)
    ncc_excess = max(0, ncc_ytd - ncc_max)
    triggered = ncc_ytd > ncc_cap and ncc_max > ncc_cap
    if triggered:
        applied.append(
            f"Non-concessional contributions {ncc_ytd:,} cents exceed the annual cap "
            f"{ncc_cap:,} cents: the bring-forward period is triggered this year [bring-forward-bands]."
        )

    rules = rules_by_id()
    cited = ["carry-forward-concessional-gate", "bring-forward-bands", f"contribution-caps-fy{fy}"]
    return {
        "financial_year": fy,
        "inputs": {
            "age_at_1_july": age_at_1_july,
            "total_super_balance_cents": tsb,
            "concessional_ytd_cents": cc_ytd,
            "non_concessional_ytd_cents": ncc_ytd,
            "unused_concessional_cents": unused,
        },
        "concessional": {
            "annual_cap_cents": cc_cap,
            "carry_forward_gate_passed": gate_passed,
            "carry_forward_applied_cents": unused if gate_passed else 0,
            "effective_cap_cents": cc_effective,
            "remaining_cents": cc_remaining,
            "excess_cents": cc_excess,
        },
        "non_concessional": {
            "annual_cap_cents": ncc_cap,
            "band": band,
            "age_condition_met": age_ok,
            "maximum_this_period_cents": ncc_max,
            "remaining_cents": ncc_remaining,
            "excess_cents": ncc_excess,
            "bring_forward_triggered": triggered,
        },
        "rules_applied": applied,
        "assumptions": [
            "total_super_balance_cents is the balance at the 30 June before the financial year.",
            "non_concessional_ytd_cents covers the whole bring-forward period if one is already "
            "running; earlier-year history is not modelled.",
            "unused_concessional_cents is the caller's own five-year total; the tool does not compute it.",
            "Arithmetic is integer cents with no division, so nothing is rounded.",
        ],
        "citations": [
            {"rule_id": rid, "title": rules[rid]["title"], "url": rules[rid]["primary_source_url"]} for rid in cited
        ],
        "notice": "General information about the rules, not a licensed financial service.",
    }
