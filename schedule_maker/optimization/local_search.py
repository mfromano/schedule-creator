"""Local search refinement using simulated annealing."""

from __future__ import annotations

import math
import random as _random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from schedule_maker.optimization.config import SearchConfig
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem
from schedule_maker.staffing_utils import block_exceeds_max

if TYPE_CHECKING:
    from schedule_maker.models.resident import Resident
    from schedule_maker.models.schedule import ScheduleGrid
    from schedule_maker.models.constraints import StaffingConstraint


@dataclass
class Swap:
    """Represents a schedule swap operation."""
    swap_type: str  # "rotation", "block", or "cross"
    resident1: str
    block1: int
    code1: str
    resident2: str | None = None  # None for within-resident swaps
    block2: int | None = None
    code2: str | None = None


def _get_block_code(res: "Resident", grid: "ScheduleGrid", block: int) -> str | None:
    """Get the rotation code for a resident's block (first week)."""
    weeks = list(grid.block_to_weeks(block))
    if not weeks:
        return None
    return res.schedule.get(weeks[0])


def _has_hospital_conflict(schedule: dict[int, str], block: int, code: str) -> bool:
    """Check if assigning code to block creates a hospital conflict."""
    target = get_hospital_system(code)
    if target == HospitalSystem.OTHER:
        return False
    start = (block - 1) * 4 + 1
    for w in range(start, start + 4):
        existing = schedule.get(w, "")
        if existing and existing != code:
            sys = get_hospital_system(existing)
            if sys != HospitalSystem.OTHER and sys != target:
                return True
    return False


def _is_fixed_block(res: "Resident", block: int, grid: "ScheduleGrid") -> bool:
    """Check if a block contains fixed/immovable assignments."""
    fixed_codes = {"AIRP", "LC", "CORE", "Res", "CEP", "Mnf", "Snf", "Snf2", "Sx"}
    for w in grid.block_to_weeks(block):
        code = res.schedule.get(w)
        if code in fixed_codes:
            return True
    return False


def generate_swap(
    residents: list["Resident"],
    grid: "ScheduleGrid",
    rng: _random.Random,
    swap_types: list[str],
) -> Swap | None:
    """Generate a random swap operation.

    Swap types:
    - rotation: Exchange two blocks within the same resident
    - block: Exchange entire block between two residents (same year)
    - cross: Exchange single rotation between two residents
    """
    r3r4 = [r for r in residents if r.r_year in (3, 4)]
    if not r3r4:
        return None

    swap_type = rng.choice(swap_types)

    if swap_type == "rotation":
        # Within-resident block swap
        res = rng.choice(r3r4)
        available = [b for b in range(1, 14) if not _is_fixed_block(res, b, grid)]
        if len(available) < 2:
            return None
        b1, b2 = rng.sample(available, 2)
        code1 = _get_block_code(res, grid, b1)
        code2 = _get_block_code(res, grid, b2)
        if not code1 or not code2 or code1 == code2:
            return None
        return Swap("rotation", res.name, b1, code1, res.name, b2, code2)

    elif swap_type == "block":
        # Between-resident full block swap (same year)
        year = rng.choice([3, 4])
        year_residents = [r for r in r3r4 if r.r_year == year]
        if len(year_residents) < 2:
            return None
        res1, res2 = rng.sample(year_residents, 2)
        available1 = [b for b in range(1, 14) if not _is_fixed_block(res1, b, grid)]
        available2 = [b for b in range(1, 14) if not _is_fixed_block(res2, b, grid)]
        common = list(set(available1) & set(available2))
        if not common:
            return None
        block = rng.choice(common)
        code1 = _get_block_code(res1, grid, block)
        code2 = _get_block_code(res2, grid, block)
        if not code1 or not code2:
            return None
        return Swap("block", res1.name, block, code1, res2.name, block, code2)

    elif swap_type == "cross":
        # Cross-resident: swap different blocks between two residents
        year = rng.choice([3, 4])
        year_residents = [r for r in r3r4 if r.r_year == year]
        if len(year_residents) < 2:
            return None
        res1, res2 = rng.sample(year_residents, 2)
        available1 = [b for b in range(1, 14) if not _is_fixed_block(res1, b, grid)]
        available2 = [b for b in range(1, 14) if not _is_fixed_block(res2, b, grid)]
        if not available1 or not available2:
            return None
        b1 = rng.choice(available1)
        b2 = rng.choice(available2)
        code1 = _get_block_code(res1, grid, b1)
        code2 = _get_block_code(res2, grid, b2)
        if not code1 or not code2:
            return None
        return Swap("cross", res1.name, b1, code1, res2.name, b2, code2)

    return None


def is_valid_swap(
    swap: Swap,
    residents: list["Resident"],
    grid: "ScheduleGrid",
    staffing_constraints: list["StaffingConstraint"] | None = None,
) -> bool:
    """Check if a swap maintains all hard constraints.

    Validates:
    - Hospital conflicts
    - Staffing maximums
    - Year eligibility
    """
    from schedule_maker.staffing_utils import _ROTATION_YEAR_ELIGIBILITY

    name_map = {r.name: r for r in residents}
    res1 = name_map.get(swap.resident1)
    if not res1:
        return False

    # For rotation swap (within-resident), swap codes between blocks
    if swap.swap_type == "rotation":
        # Check if code2 in block1 causes hospital conflict
        test_schedule = dict(res1.schedule)
        # Remove code1 from block1
        for w in grid.block_to_weeks(swap.block1):
            if test_schedule.get(w) == swap.code1:
                del test_schedule[w]
        if _has_hospital_conflict(test_schedule, swap.block1, swap.code2):
            return False
        # Check if code1 in block2 causes hospital conflict
        test_schedule = dict(res1.schedule)
        for w in grid.block_to_weeks(swap.block2):
            if test_schedule.get(w) == swap.code2:
                del test_schedule[w]
        if _has_hospital_conflict(test_schedule, swap.block2, swap.code1):
            return False
        return True

    # For block/cross swaps, need both residents
    res2 = name_map.get(swap.resident2)
    if not res2:
        return False

    # Year eligibility
    if swap.code1 in _ROTATION_YEAR_ELIGIBILITY:
        if res2.r_year not in _ROTATION_YEAR_ELIGIBILITY[swap.code1]:
            return False
    if swap.code2 in _ROTATION_YEAR_ELIGIBILITY:
        if res1.r_year not in _ROTATION_YEAR_ELIGIBILITY[swap.code2]:
            return False

    # Check hospital conflicts after swap
    test1 = dict(res1.schedule)
    for w in grid.block_to_weeks(swap.block1):
        if test1.get(w) == swap.code1:
            del test1[w]
    if _has_hospital_conflict(test1, swap.block1, swap.code2):
        return False

    test2 = dict(res2.schedule)
    b2 = swap.block2 if swap.block2 else swap.block1
    for w in grid.block_to_weeks(b2):
        if test2.get(w) == swap.code2:
            del test2[w]
    if _has_hospital_conflict(test2, b2, swap.code1):
        return False

    # Check staffing maximums
    # For block/cross swaps, the grid totals don't change for a straight swap
    # but we should verify the codes are acceptable
    if block_exceeds_max(grid, swap.block1, swap.code2):
        return False
    b2_check = swap.block2 if swap.block2 else swap.block1
    if block_exceeds_max(grid, b2_check, swap.code1):
        return False

    return True


def apply_swap(
    swap: Swap,
    residents: list["Resident"],
    grid: "ScheduleGrid",
) -> None:
    """Apply a swap operation to the schedule.

    Modifies both resident schedules and grid assignments.
    """
    name_map = {r.name: r for r in residents}
    res1 = name_map[swap.resident1]

    if swap.swap_type == "rotation":
        # Within-resident: swap codes between block1 and block2
        for w in grid.block_to_weeks(swap.block1):
            if res1.schedule.get(w) == swap.code1:
                res1.schedule[w] = swap.code2
                grid.assignments[(res1.name, w)] = swap.code2
        for w in grid.block_to_weeks(swap.block2):
            if res1.schedule.get(w) == swap.code2:
                res1.schedule[w] = swap.code1
                grid.assignments[(res1.name, w)] = swap.code1
    else:
        # Between-resident swap
        res2 = name_map[swap.resident2]
        b2 = swap.block2 if swap.block2 else swap.block1

        for w in grid.block_to_weeks(swap.block1):
            if res1.schedule.get(w) == swap.code1:
                res1.schedule[w] = swap.code2
                grid.assignments[(res1.name, w)] = swap.code2
        for w in grid.block_to_weeks(b2):
            if res2.schedule.get(w) == swap.code2:
                res2.schedule[w] = swap.code1
                grid.assignments[(res2.name, w)] = swap.code1


def revert_swap(
    swap: Swap,
    residents: list["Resident"],
    grid: "ScheduleGrid",
) -> None:
    """Revert a swap operation (inverse of apply_swap)."""
    # Create inverse swap and apply
    if swap.swap_type == "rotation":
        inverse = Swap(swap.swap_type, swap.resident1, swap.block1, swap.code2,
                       swap.resident2, swap.block2, swap.code1)
    else:
        inverse = Swap(swap.swap_type, swap.resident1, swap.block1, swap.code2,
                       swap.resident2, swap.block2, swap.code1)
    apply_swap(inverse, residents, grid)


def local_search_refine(
    residents: list["Resident"],
    grid: "ScheduleGrid",
    config: SearchConfig,
    rng: _random.Random,
    nf_result: object | None = None,
    r3_meta: dict[str, dict] | None = None,
    r4_meta: dict[str, dict] | None = None,
    staffing_constraints: list["StaffingConstraint"] | None = None,
    use_multi_objective: bool = False,
) -> tuple[float, dict]:
    """Refine a schedule using simulated annealing with swap-based neighborhood.

    Args:
        residents: All residents
        grid: Schedule grid (modified in place)
        config: Search configuration
        rng: Random number generator
        nf_result: Night float assignment result
        r3_meta: R3 build metadata
        r4_meta: R4 build metadata
        staffing_constraints: Dynamic staffing constraints
        use_multi_objective: Use multi-objective scoring (default: False uses
            simple R3/R4 satisfaction for consistency with trial loop).

    Returns:
        (final_score, stats_dict) where stats_dict contains search statistics.
    """
    from schedule_maker.validation.report import (
        compute_r3r4_satisfaction,
        compute_multi_objective_score,
    )

    # Compute initial score
    if use_multi_objective:
        score_result = compute_multi_objective_score(
            residents, grid, nf_result, r3_meta, r4_meta,
            staffing_constraints=staffing_constraints,
        )
        current_score = score_result["composite"]
    else:
        current_score = compute_r3r4_satisfaction(
            residents, grid, nf_result, r3_meta, r4_meta,
        )
    initial_score = current_score
    best_score = current_score
    best_state = {r.name: dict(r.schedule) for r in residents}
    best_grid_state = dict(grid.assignments)

    temperature = config.initial_temp
    iterations_without_improvement = 0
    accepted = 0
    rejected = 0

    for i in range(config.iterations):
        # Generate a swap
        swap = generate_swap(residents, grid, rng, config.swap_types)
        if swap is None:
            continue

        # Validate the swap
        if not is_valid_swap(swap, residents, grid, staffing_constraints):
            rejected += 1
            continue

        # Apply swap and compute new score
        apply_swap(swap, residents, grid)
        if use_multi_objective:
            new_score_result = compute_multi_objective_score(
                residents, grid, nf_result, r3_meta, r4_meta,
                staffing_constraints=staffing_constraints,
            )
            new_score = new_score_result["composite"]
        else:
            new_score = compute_r3r4_satisfaction(
                residents, grid, nf_result, r3_meta, r4_meta,
            )
        delta = new_score - current_score

        # Accept/reject based on Metropolis criterion
        if delta > 0 or (temperature > 0 and rng.random() < math.exp(delta / temperature)):
            current_score = new_score
            accepted += 1
            if new_score > best_score:
                best_score = new_score
                best_state = {r.name: dict(r.schedule) for r in residents}
                best_grid_state = dict(grid.assignments)
                iterations_without_improvement = 0
            else:
                iterations_without_improvement += 1
        else:
            # Reject: revert the swap
            revert_swap(swap, residents, grid)
            rejected += 1
            iterations_without_improvement += 1

        # Cool down
        temperature *= config.cooling_rate
        temperature = max(temperature, config.min_temp)

        # Early stopping on plateau
        if iterations_without_improvement >= config.plateau_limit:
            break

    # Restore best state
    for r in residents:
        r.schedule.clear()
        r.schedule.update(best_state.get(r.name, {}))
    grid.assignments.clear()
    grid.assignments.update(best_grid_state)

    stats = {
        "iterations": i + 1,
        "accepted": accepted,
        "rejected": rejected,
        "initial_score": initial_score,
        "final_score": best_score,
        "improvement": best_score - initial_score,
    }

    return best_score, stats
