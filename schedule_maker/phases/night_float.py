"""Phase 5: Night float assignment."""

from __future__ import annotations

from datetime import date, timedelta

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import Block, ScheduleGrid
from schedule_maker.models.constraints import NFRules, StaffingConstraint
from schedule_maker.solver.nf_solver import solve_night_float, NFAssignmentResult
from schedule_maker.validation.staffing import ROTATION_MINIMUMS


def _nocall_dates_to_weeks(
    raw_dates: list[str], blocks: list[Block],
) -> set[int]:
    """Convert M/D date strings to week numbers using block date ranges.

    Month >= 7 → academic year start year; month < 7 → start year + 1.
    """
    if not blocks:
        return set()

    year_start = blocks[0].start_date.year
    forbidden: set[int] = set()

    for raw in raw_dates:
        raw = raw.strip()
        if "/" not in raw:
            continue
        parts = raw.split("/")
        try:
            month = int(parts[0])
            day = int(parts[1])
        except (ValueError, IndexError):
            continue
        yr = year_start if month >= 7 else year_start + 1
        try:
            d = date(yr, month, day)
        except ValueError:
            continue

        # Find containing block and compute week number
        for block in blocks:
            if block.start_date <= d <= block.end_date:
                # Week within block: each block starts at week (block.number-1)*4+1
                days_in = (d - block.start_date).days
                week_offset = days_in // 7
                week_num = (block.number - 1) * 4 + 1 + week_offset
                forbidden.add(week_num)
                break

    return forbidden


def _compute_holiday_weeks(blocks: list[Block]) -> dict[str, list[int]]:
    """Map major holidays to their containing week numbers.

    Returns {"Thanksgiving": [...], "Christmas": [...], "New Years": [...]}.
    """
    if not blocks:
        return {}

    year_start = blocks[0].start_date.year

    # Thanksgiving: 4th Thursday of November in the start year
    nov1 = date(year_start, 11, 1)
    # Find first Thursday
    days_to_thu = (3 - nov1.weekday()) % 7
    first_thu = nov1 + timedelta(days=days_to_thu)
    thanksgiving = first_thu + timedelta(weeks=3)

    christmas = date(year_start, 12, 25)
    new_years = date(year_start + 1, 1, 1)

    result: dict[str, list[int]] = {}
    for name, holiday_date in [
        ("Thanksgiving", thanksgiving),
        ("Christmas", christmas),
        ("New Years", new_years),
    ]:
        for block in blocks:
            if block.start_date <= holiday_date <= block.end_date:
                days_in = (holiday_date - block.start_date).days
                week_offset = days_in // 7
                week_num = (block.number - 1) * 4 + 1 + week_offset
                result[name] = [week_num]
                break
    return result


def assign_night_float(
    residents: list[Resident],
    grid: ScheduleGrid,
    rules: NFRules | None = None,
    lc_blocks: set[int] | None = None,
    core_block: int | None = None,
    airp_assignments: dict[str, str] | None = None,
    staffing_constraints: list[StaffingConstraint] | None = None,
) -> NFAssignmentResult:
    """Assign night float using the solver, with pre-locked high-constraint assignments.

    Per goals.md, work backwards from high-constraint conditions:
    1. LC+CORE blocks: R2 Mnf, R4 Snf2
    2. Post-CORE: R2-3 Mnf, R3 Snf2
    3. Block 1: R3 Mnf
    4. AIRP blocks: avoid affected R3s
    5. Remaining: solver fills
    """
    if rules is None:
        rules = NFRules()
    if lc_blocks is None:
        lc_blocks = set()
    if airp_assignments is None:
        airp_assignments = {}

    # Build base schedule dict
    base_schedule = {}
    for res in residents:
        base_schedule[res.name] = dict(res.schedule)

    # Build no-call weeks
    no_call_weeks: dict[str, set[int]] = {}
    for res in residents:
        forbidden = set()

        # AIRP blocks are no-NF for R3s
        if res.r_year == 3 and res.name in airp_assignments:
            session_id = airp_assignments[res.name]
            # Map session to blocks (simplified — use actual block lookup)
            # For now mark AIRP weeks as forbidden
            for w in range(1, 53):
                if res.schedule.get(w) == "AIRP":
                    forbidden.add(w)

        # LC blocks are no-NF
        for w in range(1, 53):
            if res.schedule.get(w) == "LC":
                forbidden.add(w)

        # Convert raw no-call dates to week numbers
        if res.no_call and res.no_call.raw_dates:
            forbidden |= _nocall_dates_to_weeks(res.no_call.raw_dates, grid.blocks)

        if forbidden:
            no_call_weeks[res.name] = forbidden

    # Pre-lock high-constraint assignments
    locked: dict[str, list[tuple[int, str]]] = {}

    # Block 1 (weeks 1-4): Mnf to R3s only
    r3s = [r for r in residents if r.r_year == 3]
    if r3s:
        # Pick an R3 for Block 1 Mnf
        for res in r3s:
            if 1 not in no_call_weeks.get(res.name, set()):
                locked.setdefault(res.name, []).append((1, "Mnf"))
                break

    # Compute staffing snapshot for solver penalty
    staffing_snapshot: dict[int, dict[str, int]] = {}
    if staffing_constraints:
        for w in range(1, 53):
            week_staffing: dict[str, int] = {}
            for sc in staffing_constraints:
                count = grid.get_section_staffing(w, sc.rotation_codes)
                week_staffing[sc.label] = count
            staffing_snapshot[w] = week_staffing
    else:
        for w in range(1, 53):
            week_staffing: dict[str, int] = {}
            for label, (codes, _min_req) in ROTATION_MINIMUMS.items():
                count = grid.get_section_staffing(w, codes)
                week_staffing[label] = count
            staffing_snapshot[w] = week_staffing

    # Compute holiday weeks for soft penalty
    holiday_weeks = _compute_holiday_weeks(grid.blocks)

    # Solve the rest
    result = solve_night_float(
        residents=residents,
        base_schedule=base_schedule,
        rules=rules,
        num_weeks=52,
        no_call_weeks=no_call_weeks,
        locked_assignments=locked,
        staffing_snapshot=staffing_snapshot,
        staffing_constraints=staffing_constraints,
        holiday_weeks=holiday_weeks,
    )

    # Apply NF to grid
    if result.feasible:
        for name, nf_list in result.assignments.items():
            for week, code in nf_list:
                grid.assign_nf(name, week, code)

    return result
