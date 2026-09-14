"""days_until on the Australia/Sydney calendar."""

from datetime import UTC, date, datetime

import pytest

from smsf_rules_mcp.dates import days_until, fy_end, next_tbar_due, sydney_today


def test_16z_is_already_tomorrow_in_sydney():
    # 29 Jun 16:00Z is 30 Jun 02:00 AEST: the pension deadline is today, not tomorrow.
    assert sydney_today("2026-06-29T16:00:00Z") == date(2026, 6, 30)
    assert days_until("pension-minimum", "2026-06-29T16:00:00Z")["days"] == 0
    assert days_until("pension-minimum", "2026-06-29T13:00:00Z")["days"] == 1


def test_daylight_saving_offset_is_respected():
    # 13:30Z in January is 00:30 AEDT (UTC+11) the next day.
    assert sydney_today("2027-01-27T13:30:00Z") == date(2027, 1, 28)
    assert days_until("tbar-quarterly", "2027-01-27T13:30:00Z")["due_date"] == "2027-01-28"
    assert days_until("tbar-quarterly", "2027-01-27T12:30:00Z")["days"] == 1


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        sydney_today(datetime(2026, 6, 30, 12, 0))


def test_aware_datetime_accepted():
    assert sydney_today(datetime(2026, 6, 30, 15, 0, tzinfo=UTC)) == date(2026, 7, 1)


def test_plain_date_taken_as_sydney_date():
    assert days_until("2026-12-25", "2026-12-20")["days"] == 5


def test_tbar_quarters_roll_forward():
    assert next_tbar_due(date(2026, 7, 28)) == date(2026, 7, 28)
    assert next_tbar_due(date(2026, 7, 29)) == date(2026, 10, 28)
    assert next_tbar_due(date(2026, 12, 31)) == date(2027, 1, 28)


def test_fy_end_boundary():
    assert fy_end(date(2026, 6, 30)) == date(2026, 6, 30)
    assert fy_end(date(2026, 7, 1)) == date(2027, 6, 30)


def test_fixed_and_annual_deadlines():
    r = days_until("div296-first-test", "2026-09-14")
    assert r["due_date"] == "2027-06-30" and r["days"] == 289
    assert days_until("sar-self-preparer", "2026-09-14")["due_date"] == "2027-02-28"
    assert days_until("sar-new-fund", "2026-09-14")["due_date"] == "2026-10-31"
    assert days_until("sar-new-fund", "2026-11-01")["due_date"] == "2027-10-31"


def test_overdue_iso_date():
    r = days_until("2026-01-01", "2026-09-14")
    assert r["days"] < 0 and r["overdue"] is True and r["deadline_id"] is None


def test_deadline_carries_source_and_verification():
    r = days_until("tbar-quarterly", "2026-09-14")
    assert r["sources"][0]["url"].startswith("https://www.ato.gov.au/")
    assert r["verified_on"] == "2026-07-10"
    assert r["rule_id"] == "deadline-tbar-quarterly"


def test_unknown_target_rejected():
    with pytest.raises(ValueError, match="neither a deadline id"):
        days_until("bas-quarterly", "2026-09-14")


def test_default_now_is_today():
    r = days_until("2099-01-01")
    assert r["today_sydney"] == datetime.now(UTC).astimezone(sydney_today.__globals__["SYDNEY"]).date().isoformat()
