"""Phase 6: Resolve R1 Msamp blocks with specific rotations."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.constraints import StaffingConstraint
from schedule_maker.staffing_utils import rank_rotations_by_need

SAMPLER_POOL = ["Pcbi", "Mnuc", "Mucic", "Mb"]


def resolve_samplers(
    residents: list[Resident],
    grid: ScheduleGrid,
    all_residents: list[Resident] | None = None,
    staffing_constraints: list[StaffingConstraint] | None = None,
) -> dict[str, dict[int, str]]:
    """Replace Msamp/Msampler blocks with two 2-week sub-rotations.

    Each 4-week Msamp block is split into weeks 1-2 (rotation A) and
    weeks 3-4 (rotation B), drawn from SAMPLER_POOL.  Selection priority:
      1. Staffing need (most-needed rotation scores highest)
      2. Resident sampler preference (lower rank = more preferred)
      3. Year-level dedup (penalize rotations already used in prior blocks)

    Returns:
        {resident_name: {week: replacement_code}}
    """
    r1s = [r for r in residents if r.r_year == 1]
    replacements = {}

    for res in r1s:
        res_replacements: dict[int, str] = {}

        # Find all Msamp/Msampler weeks
        sampler_weeks = sorted(
            w for w, code in res.schedule.items()
            if code and ("samp" in code.lower() or "sampler" in code.lower())
        )

        if not sampler_weeks:
            continue

        # Group into 4-week blocks, splitting at schedule block boundaries
        blocks: list[list[int]] = []
        current_block = [sampler_weeks[0]]
        for w in sampler_weeks[1:]:
            same_sched_block = grid.week_to_block(w) == grid.week_to_block(current_block[0])
            if w == current_block[-1] + 1 and same_sched_block:
                current_block.append(w)
            else:
                blocks.append(current_block)
                current_block = [w]
        blocks.append(current_block)

        used_rotations: set[str] = set()

        for block_weeks in blocks:
            sched_block = grid.week_to_block(block_weeks[0])

            # Score each pool rotation
            staffing_ranked = rank_rotations_by_need(
                grid, sched_block, SAMPLER_POOL,
                constraints=staffing_constraints, r_year=1,
            )
            staffing_scores = {code: score for code, score in staffing_ranked}

            # Build combined score: staffing need + preference - dedup penalty
            scored: list[tuple[str, float]] = []
            for rot in SAMPLER_POOL:
                score = 2.0 * staffing_scores.get(rot, 0.0)

                # Preference bonus (lower rank = better, so invert)
                if res.sampler_prefs and res.sampler_prefs.rankings:
                    rank = res.sampler_prefs.rankings.get(rot, 99)
                    score += max(0, 5 - rank)

                # Dedup penalty (large enough to override staffing/pref scores)
                if rot in used_rotations:
                    score -= 100.0

                scored.append((rot, score))

            scored.sort(key=lambda x: -x[1])

            # Pick top 2 distinct rotations
            chosen: list[str] = []
            for rot, _ in scored:
                if len(chosen) >= 2:
                    break
                if rot not in chosen:
                    chosen.append(rot)

            # Assign in 2-week chunks
            for i, w in enumerate(block_weeks):
                rot = chosen[i // 2] if i // 2 < len(chosen) else chosen[-1]
                grid.assign(res.name, w, rot)
                res.schedule[w] = rot
                res_replacements[w] = rot

            used_rotations.update(chosen)

        replacements[res.name] = res_replacements

    return replacements
