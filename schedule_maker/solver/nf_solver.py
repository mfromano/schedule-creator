"""OR-Tools CP-SAT solver for night float assignment."""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from schedule_maker.models.resident import Resident
from schedule_maker.models.constraints import NFRules, StaffingConstraint
from schedule_maker.validation.staffing import ROTATION_MINIMUMS


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
    staffing_snapshot: dict[int, dict[str, int]] | None = None,
    staffing_penalty_weight: int = 20,
    no_call_penalty_weight: int = 20,
    staffing_constraints: list[StaffingConstraint] | None = None,
    holiday_weeks: dict[str, list[int]] | None = None,
    holiday_penalty_weight: int = 5,
    nocall_buffer_weight: int = 3,
) -> NFAssignmentResult:
    """Solve NF assignment using CP-SAT.

    Args:
        residents: all residents (NF applicable: R2, R3, R4)
        base_schedule: {resident_name: {week: rotation_code}}
        rules: NFRules with shift eligibility, counts, spacing
        num_weeks: total weeks in year
        no_call_weeks: {resident_name: set of week numbers} where NF is discouraged
            (soft constraint — penalized in objective, not forbidden)
        locked_assignments: pre-assigned NF that must be respected
        staffing_snapshot: {week: {rotation_label: current_count}} for staffing awareness
        staffing_penalty_weight: penalty for pulling from at/below-minimum rotations
        no_call_penalty_weight: penalty for assigning NF on a no-call week

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

    # 1. No-call weeks: soft constraint (penalized in objective, not forbidden)
    no_call_penalties = []
    for res in eligible_residents:
        forbidden = no_call_weeks.get(res.name, set())
        for w in forbidden:
            if (res.name, w) in mnf_vars:
                any_nf = mnf_vars[res.name, w] + snf2_vars[res.name, w]
                no_call_penalties.append(any_nf * no_call_penalty_weight)

    # 2. Eligibility: R2 gets Mnf only, R3 gets Mnf+Snf2, R4 gets Snf2 only
    for res in r2s:
        for w in range(1, num_weeks + 1):
            model.add(snf2_vars[res.name, w] == 0)  # R2 can't do Snf2

    if rules.r4_mnf_weeks == 0:
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
        # Per-shift-type limits for R3
        model.add(
            sum(mnf_vars[res.name, w] for w in range(1, num_weeks + 1))
            <= rules.r3_mnf_max
        )
        model.add(
            sum(snf2_vars[res.name, w] for w in range(1, num_weeks + 1))
            <= rules.r3_snf2_max
        )

    for res in r4s:
        model.add(
            sum(snf2_vars[res.name, w] for w in range(1, num_weeks + 1))
            == rules.r4_snf2_weeks
        )
        if rules.r4_mnf_weeks > 0:
            model.add(
                sum(mnf_vars[res.name, w] for w in range(1, num_weeks + 1))
                == rules.r4_mnf_weeks
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

    # 5b. No NF adjacent to existing Sx/Mnf/Snf2 in base schedule
    #     (Snf is excluded — it's packaged with Sx in R2 tracks by design)
    NF_CODES = {"Sx", "Mnf", "Snf2"}
    for res in eligible_residents:
        sched = base_schedule.get(res.name, {})
        for w in range(1, num_weeks + 1):
            if sched.get(w, "") in NF_CODES:
                # Forbid solver-assigned NF in adjacent weeks
                for w2 in range(max(1, w - 1), min(num_weeks, w + 1) + 1):
                    if w2 == w:
                        continue
                    if (res.name, w2) in mnf_vars:
                        model.add(mnf_vars[res.name, w2] == 0)
                        model.add(snf2_vars[res.name, w2] == 0)

    # 5c. No Mnf for residents on Vb (hard constraint)
    for res in eligible_residents:
        sched = base_schedule.get(res.name, {})
        for w in range(1, num_weeks + 1):
            if sched.get(w, "") == "Vb":
                model.add(mnf_vars[res.name, w] == 0)

    # 6. Locked assignments
    for name, locked in locked_assignments.items():
        for week, code in locked:
            if code == "Mnf" and (name, week) in mnf_vars:
                model.add(mnf_vars[name, week] == 1)
            elif code == "Snf2" and (name, week) in snf2_vars:
                model.add(snf2_vars[name, week] == 1)

    # 7. Per-week exclusivity: at most 1 Mnf and 1 Snf2 across all residents
    for w in range(1, num_weeks + 1):
        model.add(sum(mnf_vars[res.name, w] for res in eligible_residents) <= 1)
        model.add(sum(snf2_vars[res.name, w] for res in eligible_residents) <= 1)

    # 8. Coverage: try to have at least 1 Mnf and 1 Snf2 each week
    # (soft constraint via objective)

    # ── Staffing hard constraints + objective ─────────────────
    # Build reverse map: rotation_code → rotation_label for staffing lookup
    _code_to_labels: dict[str, list[str]] = {}
    _label_to_min: dict[str, int] = {}
    _label_to_codes: dict[str, set[str]] = {}
    if staffing_snapshot:
        if staffing_constraints:
            for sc in staffing_constraints:
                for c in sc.rotation_codes:
                    _code_to_labels.setdefault(c, []).append(sc.label)
                _label_to_min[sc.label] = sc.min_count
                _label_to_codes[sc.label] = sc.rotation_codes
        else:
            for label, (codes, _min_req) in ROTATION_MINIMUMS.items():
                for c in codes:
                    _code_to_labels.setdefault(c, []).append(label)
                _label_to_min[label] = _min_req
                _label_to_codes[label] = codes

    # 9. Hard staffing minimum constraint: forbid NF if pulling would
    #    drop base rotation below minimum staffing for that week
    if staffing_snapshot:
        for w in range(1, num_weeks + 1):
            week_staffing = staffing_snapshot.get(w, {})
            # For each staffing group, count how many eligible residents
            # on that rotation could be pulled.  If pulling ANY of them
            # would breach the minimum, forbid all of them.
            for label, min_req in _label_to_min.items():
                if min_req <= 0:
                    continue
                current = week_staffing.get(label, 0)
                if current <= min_req:
                    # Already at or below minimum — forbid pulling anyone
                    # whose base rotation is in this group
                    codes = _label_to_codes.get(label, set())
                    for res in eligible_residents:
                        sched = base_schedule.get(res.name, {})
                        if sched.get(w, "") in codes:
                            model.add(mnf_vars[res.name, w] == 0)
                            model.add(snf2_vars[res.name, w] == 0)

    # 10. Hard staffing maximum constraint: total NF assignments per
    #     week must not exceed the maximum for Mnf/Snf2 (already
    #     enforced by constraint 7 — at most 1 each per week)

    # ── Objective ─────────────────────────────────────────────
    # Prefer pulling from "easy" rotations (Pcmb, Mb, Mucic, Peds, Mnuc)
    # Penalize pulling from "hard" rotations and near-minimum staffing

    pull_bonus = []
    staffing_penalties = []
    for res in eligible_residents:
        sched = base_schedule.get(res.name, {})
        for w in range(1, num_weeks + 1):
            base_rot = sched.get(w, "")
            any_nf = mnf_vars[res.name, w] + snf2_vars[res.name, w]
            if base_rot in rules.preferred_pull_rotations:
                pull_bonus.append(any_nf * 10)  # bonus for pulling from preferred
            elif base_rot:
                pull_bonus.append(any_nf * (-5))  # penalty for pulling from others

            # Soft staffing penalty: discourage pulling from rotations
            # near minimum (at min+1) even though it's technically allowed
            if staffing_snapshot and base_rot and w in staffing_snapshot:
                week_staffing = staffing_snapshot[w]
                for label in _code_to_labels.get(base_rot, []):
                    if label in week_staffing:
                        current = week_staffing[label]
                        min_req = _label_to_min.get(label)
                        if min_req is None and label in ROTATION_MINIMUMS:
                            min_req = ROTATION_MINIMUMS[label][1]
                        if min_req is not None and current <= min_req + 1:
                            staffing_penalties.append(any_nf * staffing_penalty_weight)

    # Holiday soft constraints: penalize NF on holidays the resident doesn't prefer
    holiday_penalties = []
    if holiday_weeks:
        all_holidays = set(holiday_weeks.keys())
        for res in eligible_residents:
            pref = res.no_call.holiday_work_pref if res.no_call else ""
            history = res.no_call.holiday_history if res.no_call else []

            for holiday_name, weeks in holiday_weeks.items():
                # Penalize if resident prefers a different holiday
                penalty_for_pref = 0
                if pref and pref != "No Preference" and holiday_name != pref:
                    penalty_for_pref = holiday_penalty_weight
                # Penalize if resident worked this holiday in a prior year
                penalty_for_history = 0
                if holiday_name in history:
                    penalty_for_history = holiday_penalty_weight
                total_penalty = penalty_for_pref + penalty_for_history
                if total_penalty > 0:
                    for w in weeks:
                        if (res.name, w) in mnf_vars:
                            any_nf = mnf_vars[res.name, w] + snf2_vars[res.name, w]
                            holiday_penalties.append(any_nf * total_penalty)

    # No-call weekend buffer: penalize weeks adjacent to no-call dates
    buffer_penalties = []
    for res in eligible_residents:
        forbidden = no_call_weeks.get(res.name, set())
        for w in forbidden:
            for adj in (w - 1, w + 1):
                if 1 <= adj <= num_weeks and adj not in forbidden:
                    if (res.name, adj) in mnf_vars:
                        any_nf = mnf_vars[res.name, adj] + snf2_vars[res.name, adj]
                        buffer_penalties.append(any_nf * nocall_buffer_weight)

    # NF timing preferences from resident comments
    timing_penalties = []
    nf_timing_weight = 3
    for res in eligible_residents:
        pref = getattr(res, 'nf_timing_pref', '')
        if not pref:
            continue
        for w in range(1, num_weeks + 1):
            if (res.name, w) not in mnf_vars:
                continue
            any_nf = mnf_vars[res.name, w] + snf2_vars[res.name, w]
            if pref == "avoid-july" and w <= 4:
                timing_penalties.append(any_nf * nf_timing_weight)
            elif pref == "early-holidays-ok":
                if w <= 20:
                    timing_penalties.append(any_nf * (-nf_timing_weight))  # bonus
                elif w > 40:
                    timing_penalties.append(any_nf * nf_timing_weight)
            elif pref == "late" and w <= 16:
                timing_penalties.append(any_nf * nf_timing_weight)
            elif pref == "late-fall":
                if w <= 16 or w > 36:
                    timing_penalties.append(any_nf * nf_timing_weight)
            elif pref == "avoid-core-adjacent" and w >= 41:
                timing_penalties.append(any_nf * nf_timing_weight)
            elif pref == "holidays-ok":
                pass  # no timing penalty; holiday penalties already handle the bonus

    model.maximize(
        sum(pull_bonus) - sum(staffing_penalties) - sum(no_call_penalties)
        - sum(holiday_penalties) - sum(buffer_penalties) - sum(timing_penalties)
    )

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

        # Report no-call preference violations
        for res in eligible_residents:
            forbidden = no_call_weeks.get(res.name, set())
            for w in forbidden:
                if (res.name, w) in mnf_vars:
                    if solver.value(mnf_vars[res.name, w]) == 1:
                        result.violations.append(
                            f"{res.name}: Mnf assigned on no-call week {w}"
                        )
                    elif solver.value(snf2_vars[res.name, w]) == 1:
                        result.violations.append(
                            f"{res.name}: Snf2 assigned on no-call week {w}"
                        )

    return result
