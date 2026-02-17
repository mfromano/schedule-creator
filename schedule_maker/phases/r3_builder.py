"""Phase 3: R3 schedule builder."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem


# AIRP session definitions — update for each year
AIRP_SESSIONS = {
    # session_id: (block_number, description)
    "2": (2, "Aug 3-28 Virtual"),
    "3": (3, "Sep 14 - Oct 9 In-person"),
    "5": (5, "Oct 19 - Nov 13 Virtual"),
    "9": (9, "Jan 25 - Feb 19 Virtual"),
    "10": (10, "Mar 1-26 Virtual"),
}
MAX_PER_AIRP_SESSION = 4


def _has_hospital_conflict(schedule: dict[int, str], block: int, code: str) -> bool:
    """Check if assigning `code` to `block` creates a hospital system conflict."""
    target_system = get_hospital_system(code)
    if target_system == HospitalSystem.OTHER:
        return False

    start_week = (block - 1) * 4 + 1
    for w in range(start_week, start_week + 4):
        existing = schedule.get(w, "")
        if existing:
            existing_system = get_hospital_system(existing)
            if existing_system != HospitalSystem.OTHER and existing_system != target_system:
                return True
    return False


def assign_airp(
    residents: list[Resident],
    grid: ScheduleGrid,
    sessions: dict | None = None,
) -> dict[str, str]:
    """Assign R3s to AIRP sessions based on preferences.

    Returns {resident_name: session_id} assignments.
    """
    if sessions is None:
        sessions = AIRP_SESSIONS

    r3s = [r for r in residents if r.r_year == 3]
    assignments = {}
    session_counts = {sid: 0 for sid in sessions}

    # Sort by preference strength (residents with fewer ranked sessions first)
    def sort_key(r):
        if r.airp_prefs and r.airp_prefs.rankings:
            return len(r.airp_prefs.rankings)
        return 99

    for res in sorted(r3s, key=sort_key):
        if not res.airp_prefs or not res.airp_prefs.rankings:
            continue

        # Try sessions in preference order
        ranked = sorted(res.airp_prefs.rankings.items(), key=lambda x: x[1])
        assigned = False
        for session_id, rank in ranked:
            if session_id in session_counts and session_counts[session_id] < MAX_PER_AIRP_SESSION:
                session_counts[session_id] += 1
                assignments[res.name] = session_id
                # Write AIRP to schedule
                block = sessions[session_id][0]
                for w in grid.block_to_weeks(block):
                    grid.assign(res.name, w, "AIRP")
                    res.schedule[w] = "AIRP"
                assigned = True
                break

        if not assigned:
            # Assign to least-full session
            least = min(session_counts, key=lambda k: session_counts[k])
            session_counts[least] += 1
            assignments[res.name] = least
            block = sessions[least][0]
            for w in grid.block_to_weeks(block):
                grid.assign(res.name, w, "AIRP")
                res.schedule[w] = "AIRP"

    return assignments


def assign_learning_center(
    residents: list[Resident],
    grid: ScheduleGrid,
    core_exam_block: int = 8,  # block before which LC must be completed
) -> None:
    """Assign LC to all R3s in the last full block before CORE exam."""
    r3s = [r for r in residents if r.r_year == 3]
    lc_block = core_exam_block - 1  # Last full block before CORE

    for res in r3s:
        for w in grid.block_to_weeks(lc_block):
            grid.assign(res.name, w, "LC")
            res.schedule[w] = "LC"


def build_r3_schedules(
    residents: list[Resident],
    grid: ScheduleGrid,
    core_exam_block: int = 8,
) -> dict[str, dict]:
    """Build R3 schedules: AIRP + LC + graduation requirements + fill remaining.

    Returns per-resident schedule metadata.
    """
    r3s = [r for r in residents if r.r_year == 3]

    # Step 1: Assign AIRP
    airp_assignments = assign_airp(r3s, grid)

    # Step 2: Assign LC
    assign_learning_center(r3s, grid, core_exam_block)

    # Step 3: Fill blocks from graduation requirements
    metadata = {}
    for res in r3s:
        req_filled = _fill_r3_requirements(res, grid)

        # Step 4: Fill remaining empty blocks with general clinical rotations
        remaining_filled = _fill_r3_remaining(res, grid)

        metadata[res.name] = {
            "airp_session": airp_assignments.get(res.name, ""),
            "filled_blocks": {**req_filled, **remaining_filled},
        }

    return metadata


def _fill_r3_requirements(res: Resident, grid: ScheduleGrid) -> dict[int, str]:
    """Fill remaining empty blocks for an R3 resident with required rotations.

    Iterates rotation-first: for each needed rotation, find the best
    available block.  This avoids dropping rotations when a single block
    has a hospital-system conflict.

    Respects:
    - Hospital system conflicts
    - No Zir in or after the block before LC
    - Zir block preferences
    - NRDR/ESIR/ESNR/T32 pathway requirements
    """
    filled = {}

    # Get available blocks (not yet assigned)
    available_blocks = []
    for block in range(1, 14):
        weeks = list(grid.block_to_weeks(block))
        if not any(res.schedule.get(w) for w in weeks):
            available_blocks.append(block)

    # Determine LC block
    lc_block = None
    for block in range(1, 14):
        weeks = list(grid.block_to_weeks(block))
        if any(res.schedule.get(w) == "LC" for w in weeks):
            lc_block = block
            break

    # Build priority rotation list from recommended_blocks
    needed_rotations: list[str] = []
    for rotation, count in sorted(res.recommended_blocks.items(),
                                   key=lambda x: -x[1]):
        blocks_needed = max(1, round(count))
        for _ in range(blocks_needed):
            needed_rotations.append(rotation)

    # Also add deficient sections not already covered
    for section in res.deficient_sections:
        if section not in needed_rotations:
            needed_rotations.append(section)

    # NRDR: need 6 blocks Mnuc
    if res.is_nrdr:
        mnuc_needed = 6 - needed_rotations.count("Mnuc")
        for _ in range(max(0, mnuc_needed)):
            needed_rotations.insert(0, "Mnuc")

    # Assign rotations to available blocks (rotation-first iteration)
    used_blocks: set[int] = set()
    for code in needed_rotations:
        placed = False
        for block in available_blocks:
            if block in used_blocks:
                continue

            # No Zir in the block immediately before LC or later
            if code == "Zir" and lc_block and block >= lc_block - 1:
                continue

            if _has_hospital_conflict(res.schedule, block, code):
                continue

            # Zir block preferences: defer to a preferred block if available
            if code == "Zir" and res.zir_prefs and res.zir_prefs.preferred_blocks:
                if block not in res.zir_prefs.preferred_blocks:
                    preferred_available = [
                        b for b in res.zir_prefs.preferred_blocks
                        if b in available_blocks and b not in used_blocks
                    ]
                    if preferred_available:
                        continue

            # Place it
            _assign_block(res, grid, block, code)
            filled[block] = code
            used_blocks.add(block)
            placed = True
            break

    return filled


def _fill_r3_remaining(res: Resident, grid: ScheduleGrid) -> dict[int, str]:
    """Fill remaining empty R3 blocks with general clinical rotations.

    After graduation requirements are placed, any empty blocks are filled
    with rotations that help cover staffing needs: Peds (if short), then
    a round-robin of common clinical services.
    """
    filled = {}

    available_blocks = []
    for block in range(1, 14):
        weeks = list(grid.block_to_weeks(block))
        if not any(res.schedule.get(w) for w in weeks):
            available_blocks.append(block)

    if not available_blocks:
        return filled

    # Peds if < 2 blocks (8 weeks) completed
    peds_weeks = res.history.get("Peds", 0)
    if peds_weeks < 8:
        for block in list(available_blocks):
            if not _has_hospital_conflict(res.schedule, block, "Peds"):
                _assign_block(res, grid, block, "Peds")
                available_blocks.remove(block)
                filled[block] = "Peds"
                break

    # Fill remaining with staffing-need rotations (round-robin)
    fill_rotations = ["Mai", "Mch", "Mus", "Mucic", "Mb", "Ser"]
    rot_idx = 0
    for block in list(available_blocks):
        if rot_idx >= len(fill_rotations):
            rot_idx = 0
        code = fill_rotations[rot_idx]
        if not _has_hospital_conflict(res.schedule, block, code):
            _assign_block(res, grid, block, code)
            available_blocks.remove(block)
            filled[block] = code
        rot_idx += 1

    return filled


def _assign_block(res: Resident, grid: ScheduleGrid, block: int, code: str) -> None:
    """Assign a rotation code to all weeks of a block."""
    for w in grid.block_to_weeks(block):
        grid.assign(res.name, w, code)
        res.schedule[w] = code
