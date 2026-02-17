"""Phase 5: Night float assignment."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.constraints import NFRules
from schedule_maker.solver.nf_solver import solve_night_float, NFAssignmentResult


def assign_night_float(
    residents: list[Resident],
    grid: ScheduleGrid,
    rules: NFRules | None = None,
    lc_blocks: set[int] | None = None,
    core_block: int | None = None,
    airp_assignments: dict[str, str] | None = None,
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

        # Raw no-call dates would be mapped to weeks here
        if res.no_call and res.no_call.raw_dates:
            # These need date→week mapping; simplified for now
            pass

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

    # Solve the rest
    result = solve_night_float(
        residents=residents,
        base_schedule=base_schedule,
        rules=rules,
        num_weeks=52,
        no_call_weeks=no_call_weeks,
        locked_assignments=locked,
    )

    # Apply NF to grid
    if result.feasible:
        for name, nf_list in result.assignments.items():
            for week, code in nf_list:
                grid.assign_nf(name, week, code)

    return result
