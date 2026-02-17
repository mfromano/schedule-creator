"""Phase 6: Resolve R1 Msamp blocks with specific rotations."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid


# Msamp replacement: Pcbi (1wk), Mucic or Mir (1wk), Mnuc (2wk)
SAMPLER_ROTATIONS = ["Pcbi", "Mucic", "Mnuc", "Mnuc"]  # 4 weeks total


def resolve_samplers(
    residents: list[Resident],
    grid: ScheduleGrid,
    all_residents: list[Resident] | None = None,
) -> dict[str, dict[int, str]]:
    """Replace Msamp/Msampler blocks with specific rotations.

    Per goals.md:
    - Replace with Pcbi (1wk), Mucic or Mir (1wk, based on pref), Mnuc (2wk)
    - Order determined by NF schedule: sampler fills in for upper-level on NF

    Args:
        residents: R1 residents
        grid: schedule grid
        all_residents: all residents (to check who's on NF each week)

    Returns:
        {resident_name: {week: replacement_code}}
    """
    r1s = [r for r in residents if r.r_year == 1]
    replacements = {}

    for res in r1s:
        res_replacements = {}

        # Find all Msamp/Msampler/SSamplerCh2 weeks
        sampler_weeks = []
        for w, code in sorted(res.schedule.items()):
            if code and ("samp" in code.lower() or "sampler" in code.lower()):
                sampler_weeks.append(w)

        if not sampler_weeks:
            continue

        # Determine preferred Mucic vs Mir based on sampler prefs
        mucic_or_mir = "Mucic"
        if res.sampler_prefs and res.sampler_prefs.rankings:
            mir_rank = res.sampler_prefs.rankings.get("Mir", 99)
            mucic_rank = res.sampler_prefs.rankings.get("Mucic", 99)
            if mir_rank < mucic_rank:
                mucic_or_mir = "Mir"

        # Build replacement sequence for each 4-week Msamp block
        # Group sampler weeks into contiguous blocks
        blocks = []
        current_block = [sampler_weeks[0]]
        for w in sampler_weeks[1:]:
            if w == current_block[-1] + 1:
                current_block.append(w)
            else:
                blocks.append(current_block)
                current_block = [w]
        blocks.append(current_block)

        for block_weeks in blocks:
            rotation_seq = ["Pcbi", mucic_or_mir, "Mnuc", "Mnuc"]
            for i, w in enumerate(block_weeks):
                if i < len(rotation_seq):
                    code = rotation_seq[i]
                else:
                    code = "Mnuc"  # extra weeks get Mnuc
                grid.assign(res.name, w, code)
                res.schedule[w] = code
                res_replacements[w] = code

        replacements[res.name] = res_replacements

    return replacements
