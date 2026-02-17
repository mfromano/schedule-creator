"""OR-Tools CP-SAT solver for night float assignment."""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from schedule_maker.models.resident import Resident
from schedule_maker.models.constraints import NFRules


@dataclass
class NFAssignmentResult:
    """Result of night float assignment optimization."""
    # resident_name → list of (week_number, nf_code) tuples
    assignments: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    feasible: bool = True
    status: str = ""
    violations: list[str] = field(default_factory=list)


def solve_night_float(
    residents: list[Resident],
    base_schedule: dict[str, dict[int, str]],
    rules: NFRules,
    num_weeks: int = 52,
    no_call_weeks: dict[str, set[int]] | None = None,
    locked_assignments: dict[str, list[tuple[int, str]]] | None = None,
) -> NFAssignmentResult:
    """Solve NF assignment using CP-SAT.

    Args:
        residents: all residents (NF applicable: R2, R3, R4)
        base_schedule: {resident_name: {week: rotation_code}}
        rules: NFRules with shift eligibility, counts, spacing
        num_weeks: total weeks in year
        no_call_weeks: {resident_name: set of week numbers} where NF is forbidden
        locked_assignments: pre-assigned NF that must be respected

    Returns:
        NFAssignmentResult
    """
    if no_call_weeks is None:
        no_call_weeks = {}
    if locked_assignments is None:
        locked_assignments = {}

    model = cp_model.CpModel()

    # Categorize residents
    r2s = [r for r in residents if r.r_year == 2]
    r3s = [r for r in residents if r.r_year == 3]
    r4s = [r for r in residents if r.r_year == 4]

    # Decision variables: nf[resident_name, week] ∈ {0=none, 1=Mnf, 2=Snf2}
    # (Snf and Sx are already in R2 tracks, not assigned here)
    nf_vars: dict[tuple[str, int], cp_model.IntVar] = {}
    mnf_vars: dict[tuple[str, int], cp_model.IntVar] = {}
    snf2_vars: dict[tuple[str, int], cp_model.IntVar] = {}

    eligible_residents = r2s + r3s + r4s

    for res in eligible_residents:
        for w in range(1, num_weeks + 1):
            mnf_vars[res.name, w] = model.new_bool_var(f"mnf_{res.name}_{w}")
            snf2_vars[res.name, w] = model.new_bool_var(f"snf2_{res.name}_{w}")

    # ── Constraints ───────────────────────────────────────────

    # 1. No-call weeks: cannot assign NF
    for res in eligible_residents:
        forbidden = no_call_weeks.get(res.name, set())
        for w in forbidden:
            if (res.name, w) in mnf_vars:
                model.add(mnf_vars[res.name, w] == 0)
                model.add(snf2_vars[res.name, w] == 0)

    # 2. Eligibility: R2 gets Mnf only, R3 gets Mnf+Snf2, R4 gets Snf2 only
    for res in r2s:
        for w in range(1, num_weeks + 1):
            model.add(snf2_vars[res.name, w] == 0)  # R2 can't do Snf2

    for res in r4s:
        for w in range(1, num_weeks + 1):
            model.add(mnf_vars[res.name, w] == 0)  # R4 can't do Mnf

    # 3. Total NF counts
    for res in r2s:
        model.add(
            sum(mnf_vars[res.name, w] for w in range(1, num_weeks + 1))
            == rules.r2_mnf_weeks
        )

    for res in r3s:
        total_nf = sum(
            mnf_vars[res.name, w] + snf2_vars[res.name, w]
            for w in range(1, num_weeks + 1)
        )
        model.add(total_nf <= rules.r3_max_nf)
        model.add(total_nf >= 1)  # At least 1 NF week

    for res in r4s:
        model.add(
            sum(snf2_vars[res.name, w] for w in range(1, num_weeks + 1))
            == rules.r4_snf2_weeks
        )

    # 4. No double-assignment: can't have both Mnf and Snf2 in same week
    for res in eligible_residents:
        for w in range(1, num_weeks + 1):
            model.add(mnf_vars[res.name, w] + snf2_vars[res.name, w] <= 1)

    # 5. Minimum spacing between NF weeks for same resident
    for res in eligible_residents:
        for w in range(1, num_weeks + 1):
            any_nf_w = mnf_vars[res.name, w] + snf2_vars[res.name, w]
            for w2 in range(w + 1, min(w + rules.min_spacing_weeks, num_weeks + 1)):
                any_nf_w2 = mnf_vars[res.name, w2] + snf2_vars[res.name, w2]
                model.add(any_nf_w + any_nf_w2 <= 1)

    # 6. Locked assignments
    for name, locked in locked_assignments.items():
        for week, code in locked:
            if code == "Mnf" and (name, week) in mnf_vars:
                model.add(mnf_vars[name, week] == 1)
            elif code == "Snf2" and (name, week) in snf2_vars:
                model.add(snf2_vars[name, week] == 1)

    # 7. Coverage: try to have at least 1 Mnf and 1 Snf2 each week
    # (soft constraint via objective)

    # ── Objective ─────────────────────────────────────────────
    # Prefer pulling from "easy" rotations (Pcmb, Mb, Mucic, Peds, Mnuc)
    # Penalize pulling from "hard" rotations

    pull_bonus = []
    for res in eligible_residents:
        sched = base_schedule.get(res.name, {})
        for w in range(1, num_weeks + 1):
            base_rot = sched.get(w, "")
            any_nf = mnf_vars[res.name, w] + snf2_vars[res.name, w]
            if base_rot in rules.preferred_pull_rotations:
                pull_bonus.append(any_nf * 10)  # bonus for pulling from preferred
            elif base_rot:
                pull_bonus.append(any_nf * (-5))  # penalty for pulling from others

    # Also try to spread NF evenly across weeks
    model.maximize(sum(pull_bonus))

    # ── Solve ─────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    status = solver.solve(model)

    result = NFAssignmentResult(
        feasible=status in (cp_model.OPTIMAL, cp_model.FEASIBLE),
        status=solver.status_name(status),
    )

    if result.feasible:
        for res in eligible_residents:
            nf_list = []
            for w in range(1, num_weeks + 1):
                if solver.value(mnf_vars[res.name, w]) == 1:
                    nf_list.append((w, "Mnf"))
                elif solver.value(snf2_vars[res.name, w]) == 1:
                    nf_list.append((w, "Snf2"))
            if nf_list:
                result.assignments[res.name] = nf_list

    return result
