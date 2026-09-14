"""Golden caps per FY and headroom arithmetic edge cases."""

import pytest

from smsf_rules_mcp.caps import caps_summary, contribution_headroom
from smsf_rules_mcp.data import normalise_fy

GOLDEN = {
    # FY: (concessional, non-concessional, general TBC, 3x-below, 2x-below)
    "2024-25": (30_000_00, 120_000_00, 1_900_000_00, 1_660_000_00, 1_780_000_00),
    "2025-26": (30_000_00, 120_000_00, 2_000_000_00, 1_760_000_00, 1_880_000_00),
    "2026-27": (32_500_00, 130_000_00, 2_100_000_00, 1_840_000_00, 1_970_000_00),
}


@pytest.mark.parametrize(("fy", "expected"), GOLDEN.items())
def test_caps_golden(fy, expected):
    cc, ncc, tbc, three, two = expected
    c = caps_summary(fy)
    assert c["concessional_cap_cents"] == cc
    assert c["non_concessional_cap_cents"] == ncc
    assert c["general_transfer_balance_cap_cents"] == tbc
    assert c["bring_forward"]["three_year_available_while_tsb_below_cents"] == three
    assert c["bring_forward"]["two_year_available_while_tsb_below_cents"] == two
    assert c["bring_forward"]["three_year_total_cents"] == 3 * ncc
    assert c["total_super_balance_thresholds"]["carry_forward_concessional_gate_cents"] == 500_000_00
    assert c["sources"][0]["url"].startswith("https://www.ato.gov.au/")
    assert c["verified_on"] == "2026-07-07"


def test_caps_band_identities_hold_for_every_fy():
    for fy in GOLDEN:
        c = caps_summary(fy)
        ncc, tbc = c["non_concessional_cap_cents"], c["general_transfer_balance_cap_cents"]
        assert c["bring_forward"]["three_year_available_while_tsb_below_cents"] == tbc - 2 * ncc
        assert c["bring_forward"]["two_year_available_while_tsb_below_cents"] == tbc - ncc


def test_division_296_only_from_commencement_year():
    d = caps_summary("2026-27")["division_296"]
    assert d["lower_threshold_cents"] == 3_000_000_00
    assert d["upper_threshold_cents"] == 10_000_000_00
    assert (d["tier1_rate"], d["tier2_rate"]) == (0.15, 0.25)
    assert d["first_test_date"] == "2027-06-30"
    assert caps_summary("2025-26")["division_296"] == {
        "applies": False,
        "note": "Division 296 commenced 2026-07-01; no thresholds for FY 2025-26.",
    }


@pytest.mark.parametrize("value", ["2026-27", "FY2026-27", "2026", 2026, "2026/27", "fy 2026-2027"])
def test_normalise_fy_forms(value):
    assert normalise_fy(value) == "2026-27"


@pytest.mark.parametrize("value", ["2026-28", "26-27", "abc", "2023-24"])
def test_unknown_or_malformed_fy_rejected(value):
    with pytest.raises(ValueError):
        caps_summary(value)


def headroom(**kw):
    base = {
        "financial_year": "2026-27",
        "age_at_1_july": 55,
        "total_super_balance_cents": 400_000_00,
        "concessional_ytd_cents": 0,
        "non_concessional_ytd_cents": 0,
    }
    return contribution_headroom(**{**base, **kw})


def test_headroom_plain_room():
    h = headroom(concessional_ytd_cents=12_500_00, non_concessional_ytd_cents=30_000_00)
    assert h["concessional"]["remaining_cents"] == 20_000_00
    assert h["concessional"]["excess_cents"] == 0
    assert h["non_concessional"]["band"] == "3x"
    assert h["non_concessional"]["remaining_cents"] == 360_000_00
    assert h["non_concessional"]["bring_forward_triggered"] is False
    assert {c["rule_id"] for c in h["citations"]} >= {"bring-forward-bands", "carry-forward-concessional-gate"}
    assert all(c["url"].startswith("https://www.ato.gov.au/") for c in h["citations"])


def test_headroom_over_concessional_cap():
    h = headroom(concessional_ytd_cents=40_000_00)
    assert h["concessional"]["remaining_cents"] == 0
    assert h["concessional"]["excess_cents"] == 7_500_00


def test_headroom_bring_forward_trigger():
    h = headroom(non_concessional_ytd_cents=150_000_00)
    assert h["non_concessional"]["bring_forward_triggered"] is True
    assert h["non_concessional"]["remaining_cents"] == 240_000_00
    assert any("triggered" in line for line in h["rules_applied"])


def test_headroom_over_three_year_total():
    h = headroom(non_concessional_ytd_cents=400_000_00)
    assert h["non_concessional"]["excess_cents"] == 10_000_00
    assert h["non_concessional"]["remaining_cents"] == 0


def test_carry_forward_gate_is_strict():
    below = headroom(total_super_balance_cents=499_999_99, unused_concessional_cents=30_000_00)
    at = headroom(total_super_balance_cents=500_000_00, unused_concessional_cents=30_000_00)
    assert below["concessional"]["carry_forward_gate_passed"] is True
    assert below["concessional"]["effective_cap_cents"] == 62_500_00
    assert at["concessional"]["carry_forward_gate_passed"] is False
    assert at["concessional"]["effective_cap_cents"] == 32_500_00
    assert at["concessional"]["carry_forward_applied_cents"] == 0


@pytest.mark.parametrize(
    ("tsb", "band", "maximum"),
    [
        (1_839_999_99, "3x", 390_000_00),
        (1_840_000_00, "2x", 260_000_00),
        (1_969_999_99, "2x", 260_000_00),
        (1_970_000_00, "1x", 130_000_00),
        (2_099_999_99, "1x", 130_000_00),
        (2_100_000_00, "nil", 0),
        (5_000_000_00, "nil", 0),
    ],
)
def test_tsb_band_boundaries(tsb, band, maximum):
    h = headroom(total_super_balance_cents=tsb)
    assert h["non_concessional"]["band"] == band
    assert h["non_concessional"]["maximum_this_period_cents"] == maximum


def test_tsb_nil_band_any_contribution_is_excess():
    h = headroom(total_super_balance_cents=2_100_000_00, non_concessional_ytd_cents=1_00)
    assert h["non_concessional"]["excess_cents"] == 1_00
    assert h["non_concessional"]["bring_forward_triggered"] is False


def test_age_75_drops_bring_forward_to_annual_cap():
    under = headroom(age_at_1_july=74)
    over = headroom(age_at_1_july=75)
    assert under["non_concessional"]["band"] == "3x"
    assert over["non_concessional"]["band"] == "1x"
    assert over["non_concessional"]["age_condition_met"] is False
    assert over["non_concessional"]["maximum_this_period_cents"] == 130_000_00


def test_age_75_with_nil_band_stays_nil():
    h = headroom(age_at_1_july=80, total_super_balance_cents=2_100_000_00)
    assert h["non_concessional"]["band"] == "nil"


@pytest.mark.parametrize("field", ["total_super_balance_cents", "concessional_ytd_cents", "non_concessional_ytd_cents"])
def test_negative_or_fractional_cents_rejected(field):
    with pytest.raises(ValueError):
        headroom(**{field: -1})
    with pytest.raises(ValueError):
        headroom(**{field: 1.5})


def test_headroom_prior_fy_uses_that_years_caps():
    h = headroom(financial_year="2024-25", total_super_balance_cents=1_700_000_00)
    assert h["concessional"]["annual_cap_cents"] == 30_000_00
    assert h["non_concessional"]["band"] == "2x"
    assert h["non_concessional"]["maximum_this_period_cents"] == 240_000_00
