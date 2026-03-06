"""Shared staffing-awareness utilities for schedule phases."""

from __future__ import annotations

from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import fse_to_base_code
from schedule_maker.models.constraints import StaffingConstraint
from schedule_maker.validation.staffing import ROTATION_MINIMUMS, ROTATION_MAXIMUMS


def _build_code_to_groups(
    constraints: list[StaffingConstraint] | None = None,
    r_year: int | None = None,
) -> dict[str, list[tuple[set[str], int]]]:
    """Build reverse map: rotation_code → list of (codes_set, min_required).

    Uses dynamic constraints if provided, otherwise falls back to ROTATION_MINIMUMS.
    When r_year is given, only includes constraints that apply to that year
    (empty r_years = applies to all).
    """
    code_to_groups: dict[str, list[tuple[set[str], int]]] = {}
    if constraints:
        for sc in constraints:
            if r_year and sc.r_years and r_year not in sc.r_years:
                continue
            for c in sc.rotation_codes:
                code_to_groups.setdefault(c, []).append((sc.rotation_codes, sc.min_count))
    else:
        for _label, (codes, min_req) in ROTATION_MINIMUMS.items():
            for c in codes:
                code_to_groups.setdefault(c, []).append((codes, min_req))
    return code_to_groups


def get_staffing_deficit(grid: ScheduleGrid, week: int, rotation_codes: set[str], min_required: int) -> int:
    """How far below minimum a rotation group is for a given week.

    Returns a positive number if under-staffed, 0 if at or above minimum.
    """
    count = grid.get_section_staffing(week, rotation_codes)
    return max(0, min_required - count)


def get_staffing_need(grid: ScheduleGrid, week: int, rotation_codes: set[str], min_required: int) -> float:
    """Staffing need score: strongly positive if under minimum, mildly negative if over.

    Returns:
      - Full deficit if under minimum (needs more residents)
      - Dampened surplus penalty if over minimum (to discourage piling on)
    The asymmetry ensures understaffed rotations are strongly preferred
    while overstaffed ones are gently deprioritized.
    """
    count = grid.get_section_staffing(week, rotation_codes)
    deficit = min_required - count
    if deficit > 0:
        return float(deficit)  # full weight for understaffing
    # Dampen surplus: -0.25 per extra resident above minimum
    return deficit * 0.25


def rank_rotations_by_need(
    grid: ScheduleGrid,
    block: int,
    candidates: list[str],
    constraints: list[StaffingConstraint] | None = None,
    r_year: int | None = None,
) -> list[tuple[str, float]]:
    """Rank candidate rotations by staffing need across block weeks.

    Uses signed need (positive=understaffed, negative=overstaffed) so
    overstaffed rotations sort below understaffed ones.
    Returns [(rotation_code, total_need)] sorted descending (most needed first).
    """
    code_to_groups = _build_code_to_groups(constraints, r_year)

    weeks = list(grid.block_to_weeks(block))
    scored: list[tuple[str, float]] = []

    for candidate in candidates:
        total_need = 0.0
        groups = code_to_groups.get(candidate, [])
        for codes_set, min_req in groups:
            for w in weeks:
                total_need += get_staffing_need(grid, w, codes_set, min_req)
        scored.append((candidate, total_need))

    scored.sort(key=lambda x: -x[1])
    return scored


def block_exceeds_max(grid: ScheduleGrid, block: int, code: str, default_max: int = 6) -> bool:
    """Check if assigning ``code`` to ``block`` would exceed its max staffing cap.

    Uses ROTATION_MAXIMUMS for rotations with explicit caps, otherwise
    falls back to ``default_max`` (default 6).  FSE codes are mapped to
    their base rotation for the comparison.
    """
    # Resolve FSE → base code so FSE-Bre counts against Pcbi cap, etc.
    effective = fse_to_base_code(code)

    # Find the matching max group (if any)
    max_allowed = default_max
    matched_codes: set[str] | None = None
    for _label, (codes, cap) in ROTATION_MAXIMUMS.items():
        if effective in codes:
            max_allowed = cap
            matched_codes = codes
            break

    weeks = list(grid.block_to_weeks(block))
    for w in weeks:
        assignments = grid.get_week_assignments(w)
        if matched_codes is not None:
            count = sum(
                1 for c in assignments.values()
                if c in matched_codes or fse_to_base_code(c) in matched_codes
            )
        else:
            # No explicit group — count exact code matches (+ FSE variants)
            count = sum(
                1 for c in assignments.values()
                if c == effective or fse_to_base_code(c) == effective
            )
        if count >= max_allowed:
            return True
    return False


def rank_rotations_by_combined_score(
    grid: ScheduleGrid,
    block: int,
    candidates: list[str],
    section_prefs: "SectionPrefs | None" = None,
    staffing_weight: int = 2,
    pref_weight: int = 3,
    constraints: list[StaffingConstraint] | None = None,
    r_year: int | None = None,
) -> list[tuple[str, float]]:
    """Rank candidates by combined staffing need + preference score.

    Uses signed need (positive=understaffed, negative=overstaffed) so
    overstaffed rotations are actively deprioritized.
    Returns [(rotation_code, combined_score)] sorted descending (best first).
    """
    from schedule_maker.models.resident import SectionPrefs

    code_to_groups = _build_code_to_groups(constraints, r_year)

    weeks = list(grid.block_to_weeks(block))
    scored: list[tuple[str, float]] = []

    for candidate in candidates:
        total_need = 0.0
        groups = code_to_groups.get(candidate, [])
        for codes_set, min_req in groups:
            for w in weeks:
                total_need += get_staffing_need(grid, w, codes_set, min_req)

        pref_score = 0.0
        if section_prefs is not None and section_prefs.scores:
            pref_score = section_prefs.scores.get(candidate, 0)

        combined = staffing_weight * total_need + pref_weight * pref_score
        scored.append((candidate, combined))

    scored.sort(key=lambda x: -x[1])
    return scored


# Rotation → set of R-years allowed to be assigned
_ROTATION_YEAR_ELIGIBILITY: dict[str, set[int]] = {
    "Vir": {2},
    "Sir": {2},
    "Zir": {3, 4},
    "Zai": {2},
    "Mnct": {1},
    "Vnuc": set(),  # retired rotation — never assign
}


def build_fill_candidates(
    constraints: list[StaffingConstraint] | None = None,
    base: list[str] | None = None,
    r_year: int | None = None,
) -> list[str]:
    """Build a comprehensive list of fill-candidate rotation codes.

    Starts from a base list and adds every rotation code that appears in
    a staffing constraint (dynamic or ROTATION_MINIMUMS fallback).
    Excludes night-float and admin codes.
    When r_year is given, excludes rotations restricted to other years.
    """
    from schedule_maker.models.rotation import is_night_float

    excluded = {"Res", "CEP", "AIRP", "LC", "Mx", "Sx", "Snf", "Snf2", "Mnf",
                "Msamp", "Msampler", "SSamplerCh2",
                "Vch", "Vn", "Vnuc"}  # retired rotations
    candidates = list(base or ["Mai", "Mch", "Mus", "Mucic", "Mb", "Ser"])
    if constraints:
        for sc in constraints:
            for code in sc.rotation_codes:
                if code not in candidates and code not in excluded and not is_night_float(code):
                    candidates.append(code)
    else:
        for _label, (codes, _min) in ROTATION_MINIMUMS.items():
            for code in codes:
                if code not in candidates and code not in excluded and not is_night_float(code):
                    candidates.append(code)
    # Filter out rotations not eligible for this R-year
    if r_year is not None:
        candidates = [
            c for c in candidates
            if c not in _ROTATION_YEAR_ELIGIBILITY or r_year in _ROTATION_YEAR_ELIGIBILITY[c]
        ]
    return candidates


def get_most_needed_rotation(
    grid: ScheduleGrid,
    block: int,
    candidates: list[str],
) -> str:
    """Return the candidate rotation with the highest staffing deficit.

    Falls back to the first candidate if all deficits are equal.
    """
    ranked = rank_rotations_by_need(grid, block, candidates)
    return ranked[0][0] if ranked else candidates[0]
