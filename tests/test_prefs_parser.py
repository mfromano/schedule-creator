"""Unit tests for PrefsParser static helper methods added in 2026-03."""
from __future__ import annotations

from datetime import datetime

import pytest

from schedule_maker.io.prefs_parser import PrefsParser, _SAMPLER_COLS
from schedule_maker.models.resident import Resident, SamplerPrefs


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_r1(name: str = "Doe, Jane", sampler_prefs: SamplerPrefs | None = None) -> Resident:
    parts = name.split(", ", 1)
    last = parts[0].strip()
    first = parts[1].strip() if len(parts) > 1 else ""
    return Resident(name=name, first_name=first, last_name=last, r_year=1,
                    sampler_prefs=sampler_prefs)


def make_resident(name: str, r_year: int) -> Resident:
    parts = name.split(", ", 1)
    last = parts[0].strip()
    first = parts[1].strip() if len(parts) > 1 else ""
    return Resident(name=name, first_name=first, last_name=last, r_year=r_year)


SAMPLER_CODES = set(_SAMPLER_COLS.values())  # {"Nir", "Mir", "Msk", "Mnuc", "Mucic"}


# ── _fill_missing_r1_prefs ────────────────────────────────────────────────────

class TestFillMissingR1Prefs:
    def test_r1_without_prefs_gets_sampler_prefs(self):
        res = make_r1()
        assert res.sampler_prefs is None
        PrefsParser._fill_missing_r1_prefs([res])
        assert res.sampler_prefs is not None

    def test_assigned_rankings_cover_all_five_codes(self):
        res = make_r1()
        PrefsParser._fill_missing_r1_prefs([res])
        assert set(res.sampler_prefs.rankings.keys()) == SAMPLER_CODES

    def test_assigned_rankings_are_1_through_5(self):
        res = make_r1()
        PrefsParser._fill_missing_r1_prefs([res])
        assert set(res.sampler_prefs.rankings.values()) == {1, 2, 3, 4, 5}

    def test_existing_sampler_prefs_are_not_overwritten(self):
        original = SamplerPrefs(rankings={"Nir": 1, "Mir": 2, "Msk": 3, "Mnuc": 4, "Mucic": 5})
        res = make_r1(sampler_prefs=original)
        PrefsParser._fill_missing_r1_prefs([res])
        assert res.sampler_prefs is original

    def test_non_r1_residents_are_untouched(self):
        r2 = make_resident("Smith, John", r_year=2)
        r3 = make_resident("Jones, Alice", r_year=3)
        PrefsParser._fill_missing_r1_prefs([r2, r3])
        assert r2.sampler_prefs is None
        assert r3.sampler_prefs is None

    def test_mixed_class_only_fills_r1(self):
        r1_missing = make_r1("Adams, Beth")
        r1_has = make_r1("Brown, Tom",
                         sampler_prefs=SamplerPrefs(rankings={"Nir": 1, "Mir": 2, "Msk": 3, "Mnuc": 4, "Mucic": 5}))
        r2 = make_resident("Clark, Eve", r_year=2)

        PrefsParser._fill_missing_r1_prefs([r1_missing, r1_has, r2])

        assert r1_missing.sampler_prefs is not None
        assert set(r1_missing.sampler_prefs.rankings.keys()) == SAMPLER_CODES
        assert r1_has.sampler_prefs.rankings == {"Nir": 1, "Mir": 2, "Msk": 3, "Mnuc": 4, "Mucic": 5}
        assert r2.sampler_prefs is None

    def test_multiple_missing_r1s_each_get_independent_rankings(self):
        residents = [make_r1(f"Resident{i:02d}, Test") for i in range(5)]
        PrefsParser._fill_missing_r1_prefs(residents)
        for res in residents:
            assert set(res.sampler_prefs.rankings.keys()) == SAMPLER_CODES
            assert set(res.sampler_prefs.rankings.values()) == {1, 2, 3, 4, 5}

    def test_empty_list_does_not_crash(self):
        PrefsParser._fill_missing_r1_prefs([])  # should not raise


# ── _dedup_rows ───────────────────────────────────────────────────────────────

class TestDedupRows:
    def _row(self, full_name: str, ts=None, **extra) -> dict:
        return {"Full Name": full_name, "Timestamp": ts, **extra}

    def test_single_row_passes_through(self):
        rows = [self._row("Jane Doe", ts=datetime(2026, 3, 1))]
        result = PrefsParser._dedup_rows(rows)
        assert len(result) == 1
        assert result[0]["Full Name"] == "Jane Doe"

    def test_duplicate_keeps_latest_timestamp(self):
        early = self._row("Jane Doe", ts=datetime(2026, 2, 1), data="old")
        late = self._row("Jane Doe", ts=datetime(2026, 3, 15), data="new")
        result = PrefsParser._dedup_rows([early, late])
        assert len(result) == 1
        assert result[0]["data"] == "new"

    def test_duplicate_latest_first_in_list(self):
        """Order in input doesn't matter — timestamp wins."""
        late = self._row("Jane Doe", ts=datetime(2026, 3, 15), data="new")
        early = self._row("Jane Doe", ts=datetime(2026, 2, 1), data="old")
        result = PrefsParser._dedup_rows([late, early])
        assert len(result) == 1
        assert result[0]["data"] == "new"

    def test_different_residents_both_kept(self):
        rows = [
            self._row("Jane Doe", ts=datetime(2026, 3, 1)),
            self._row("John Smith", ts=datetime(2026, 3, 2)),
        ]
        result = PrefsParser._dedup_rows(rows)
        assert len(result) == 2

    def test_name_via_first_last_columns(self):
        early = {"First Name": "Jane", "Last Name": "Doe", "Timestamp": datetime(2026, 2, 1), "data": "old"}
        late  = {"First Name": "Jane", "Last Name": "Doe", "Timestamp": datetime(2026, 3, 1), "data": "new"}
        result = PrefsParser._dedup_rows([early, late])
        assert len(result) == 1
        assert result[0]["data"] == "new"

    def test_name_via_name_column(self):
        early = {"Name": "Doe, Jane", "Timestamp": datetime(2026, 2, 1), "data": "old"}
        late  = {"Name": "Doe, Jane", "Timestamp": datetime(2026, 3, 1), "data": "new"}
        result = PrefsParser._dedup_rows([early, late])
        assert len(result) == 1
        assert result[0]["data"] == "new"

    def test_no_timestamp_last_row_wins(self):
        """When timestamps are absent, row order determines the winner (last wins)."""
        first  = {"Full Name": "Jane Doe", "Timestamp": None, "data": "first"}
        second = {"Full Name": "Jane Doe", "Timestamp": None, "data": "second"}
        result = PrefsParser._dedup_rows([first, second])
        assert len(result) == 1
        assert result[0]["data"] == "second"

    def test_rows_without_name_are_skipped(self):
        rows = [
            {"Full Name": "", "First Name": "", "Last Name": "", "Timestamp": None},
            self._row("Jane Doe"),
        ]
        result = PrefsParser._dedup_rows(rows)
        assert len(result) == 1
        assert result[0]["Full Name"] == "Jane Doe"

    def test_empty_input_returns_empty(self):
        assert PrefsParser._dedup_rows([]) == []

    def test_case_insensitive_dedup(self):
        """Same name in different cases should collapse to one entry."""
        early = self._row("jane doe", ts=datetime(2026, 2, 1), data="lower")
        late  = self._row("Jane Doe", ts=datetime(2026, 3, 1), data="title")
        result = PrefsParser._dedup_rows([early, late])
        assert len(result) == 1
        assert result[0]["data"] == "title"
