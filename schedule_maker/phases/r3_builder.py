"""Phase 3: R3 schedule builder."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem


# AIRP session definitions (from 2025 prefs — update for each year)
AIRP_SESSIONS = {
    # session_id: (block_number, description)
    "2": (2, "Aug Virtual"),
    "3+4": (3, "Sep In-Person"),
    "4+5": (4, "Oct Virtual"),
    "9": (9, "Feb Virtual"),
    "10": (10, "Mar Virtual"),
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
    """Build R3 schedules: AIRP + LC + graduation requirements.

    Returns per-resident schedule metadata.
    """
    r3s = [r for r in residents if r.r_year == 3]

    # Step 1: Assign AIRP
    airp_assignments = assign_airp(r3s, grid)

    # Step 2: Assign LC
    assign_learning_center(r3s, grid, core_exam_block)

    # Step 3: Fill remaining blocks with required rotations
    metadata = {}
    for res in r3s:
        filled = _fill_r3_requirements(res, grid)
        metadata[res.name] = {
            "airp_session": airp_assignments.get(res.name, ""),
            "filled_blocks": filled,
        }

    return metadata


def _fill_r3_requirements(res: Resident, grid: ScheduleGrid) -> dict[int, str]:
    """Fill remaining empty blocks for an R3 resident with required rotations.

    Respects:
    - Hospital system conflicts
    - No Zir before LC
    - NRDR breast requirements
    - T32/ESIR/ESNR NM/breast requirements
    """
    filled = {}

    # Get available blocks (not yet assigned)
    available_blocks = []
    for block in range(1, 14):
        weeks = list(grid.block_to_weeks(block))
        if not any(res.schedule.get(w) for w in weeks):
            available_blocks.append(block)

    # Determine LC block (find it)
    lc_block = None
    for block in range(1, 14):
        weeks = list(grid.block_to_weeks(block))
        if any(res.schedule.get(w) == "LC" for w in weeks):
            lc_block = block
            break

    # Build priority rotation list from recommended_blocks
    needed_rotations = []
    for rotation, count in sorted(res.recommended_blocks.items(),
                                   key=lambda x: -x[1]):
        blocks_needed = max(1, round(count))
        for _ in range(blocks_needed):
            needed_rotations.append(rotation)

    # Also add deficient sections as rotations
    for section in res.deficient_sections:
        if section not in [r for r in needed_rotations]:
            needed_rotations.append(section)

    # NRDR: need 6 blocks Mnuc
    if res.is_nrdr:
        mnuc_needed = 6 - needed_rotations.count("Mnuc")
        for _ in range(max(0, mnuc_needed)):
            needed_rotations.insert(0, "Mnuc")

    # Assign rotations to available blocks
    rotation_idx = 0
    for block in available_blocks:
        if rotation_idx >= len(needed_rotations):
            break

        code = needed_rotations[rotation_idx]

        # Skip Zir before LC
        if code == "Zir" and lc_block and block >= lc_block - 1:
            # Try to find a different block for Zir or swap
            rotation_idx += 1
            continue

        # Check hospital conflict
        if _has_hospital_conflict(res.schedule, block, code):
            rotation_idx += 1
            continue

        # Check Zir block preferences
        if code == "Zir" and res.zir_prefs and res.zir_prefs.preferred_blocks:
            if block not in res.zir_prefs.preferred_blocks:
                # Try to defer Zir to a preferred block
                # Only skip if a preferred block is still available
                preferred_available = [b for b in res.zir_prefs.preferred_blocks
                                       if b in available_blocks and b != block]
                if preferred_available:
                    continue

        # Assign
        for w in grid.block_to_weeks(block):
            grid.assign(res.name, w, code)
            res.schedule[w] = code
        filled[block] = code
        rotation_idx += 1

    return filled
