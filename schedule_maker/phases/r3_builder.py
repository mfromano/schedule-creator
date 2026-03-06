"""Phase 3: R3 schedule builder."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem
from schedule_maker.models.constraints import StaffingConstraint
from schedule_maker.staffing_utils import (
    rank_rotations_by_need, rank_rotations_by_combined_score,
    block_exceeds_max, build_fill_candidates,
    _ROTATION_YEAR_ELIGIBILITY,
)


MAX_PER_AIRP_SESSION = 4
AIRP_RANK_WEIGHT = 10
AIRP_GROUPMATE_BONUS = 8


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


def _build_airp_sessions(residents: list[Resident]) -> dict[str, tuple[int, str]]:
    """Build AIRP sessions from resident preferences.

    Session ID = block number (read from Preferences col Y / airp_prefs.rankings).
    Returns {session_id: (block_number, description)}.
    """
    sessions: dict[str, tuple[int, str]] = {}
    for res in residents:
        if res.airp_prefs and res.airp_prefs.rankings:
            for session_id in res.airp_prefs.rankings:
                if session_id not in sessions:
                    try:
                        block = int(session_id)
                        sessions[session_id] = (block, f"Block {block}")
                    except ValueError:
                        pass
    return sessions


def assign_airp(
    residents: list[Resident],
    grid: ScheduleGrid,
    sessions: dict | None = None,
) -> dict[str, str]:
    """Assign R3s to AIRP sessions based on preferences.

    If sessions is None, builds session list from resident AIRP preferences
    (session ID = block number).

    Returns {resident_name: session_id} assignments.
    """
    r3s = [r for r in residents if r.r_year == 3]

    if sessions is None:
        sessions = _build_airp_sessions(r3s)

    if not sessions:
        return {}

    assignments = {}
    session_counts = {sid: 0 for sid in sessions}

    # Build name resolution maps for group requests (first name → full name)
    first_name_map: dict[str, str] = {}
    full_name_set: set[str] = set()
    for r in r3s:
        if r.first_name:
            first_name_map[r.first_name.strip().lower()] = r.name
        full_name_set.add(r.name)

    def _resolve_groupmates(raw_requests: list[str]) -> list[str]:
        """Resolve group request names to canonical 'Last, First' format."""
        resolved = []
        for entry in raw_requests:
            for token in entry.split(","):
                token = token.strip()
                if not token:
                    continue
                # Try direct match (already "Last, First")
                if token in full_name_set:
                    resolved.append(token)
                    continue
                # Try first-name lookup
                key = token.lower()
                if key in first_name_map:
                    resolved.append(first_name_map[key])
                    continue
                # Try "First Last" → "Last, First"
                parts = token.split()
                if len(parts) == 2:
                    flipped = f"{parts[1]}, {parts[0]}"
                    if flipped in full_name_set:
                        resolved.append(flipped)
                        continue
                    # Also try case-insensitive first name from parts
                    key2 = parts[0].lower()
                    if key2 in first_name_map:
                        resolved.append(first_name_map[key2])
        return resolved

    # Sort by preference strength (residents with fewer ranked sessions first)
    def sort_key(r):
        if r.airp_prefs and r.airp_prefs.rankings:
            return len(r.airp_prefs.rankings)
        return 99

    for res in sorted(r3s, key=sort_key):
        if not res.airp_prefs or not res.airp_prefs.rankings:
            continue

        # Resolve group requests to canonical names
        resolved_groupmates: list[str] = []
        if res.airp_prefs.group_requests:
            resolved_groupmates = _resolve_groupmates(res.airp_prefs.group_requests)

        # Score each eligible session: preference rank + groupmate bonus
        ranked = res.airp_prefs.rankings

        best_session = None
        best_score = float('-inf')
        for session_id in ranked:
            if session_id not in session_counts or session_counts[session_id] >= MAX_PER_AIRP_SESSION:
                continue
            rank = ranked[session_id]
            score = -rank * AIRP_RANK_WEIGHT
            # Bonus for each groupmate already in this session
            for gm in resolved_groupmates:
                if assignments.get(gm) == session_id:
                    score += AIRP_GROUPMATE_BONUS
            if score > best_score:
                best_score = score
                best_session = session_id

        assigned = False
        if best_session is not None:
            session_counts[best_session] += 1
            assignments[res.name] = best_session
            block = sessions[best_session][0]
            for w in grid.block_to_weeks(block):
                grid.assign(res.name, w, "AIRP")
                res.schedule[w] = "AIRP"
            assigned = True

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
    lc_weeks: list[int] | None = None,
) -> None:
    """Assign LC to all R3s.

    If *lc_weeks* is provided, assign LC to those specific week numbers.
    Otherwise fall back to the full block before *core_exam_block*.
    """
    r3s = [r for r in residents if r.r_year == 3]

    if lc_weeks:
        for res in r3s:
            for w in lc_weeks:
                grid.assign(res.name, w, "LC")
                res.schedule[w] = "LC"
    else:
        lc_block = core_exam_block - 1
        for res in r3s:
            for w in grid.block_to_weeks(lc_block):
                grid.assign(res.name, w, "LC")
                res.schedule[w] = "LC"


def assign_core(
    residents: list[Resident],
    grid: ScheduleGrid,
    core_weeks: list[int],
) -> None:
    """Assign CORE to specific weeks for all R3s."""
    r3s = [r for r in residents if r.r_year == 3]
    for res in r3s:
        for w in core_weeks:
            grid.assign(res.name, w, "CORE")
            res.schedule[w] = "CORE"


def assign_r3_fixed(
    residents: list[Resident],
    grid: ScheduleGrid,
    core_exam_block: int = 8,
    lc_weeks: list[int] | None = None,
    core_weeks: list[int] | None = None,
) -> dict:
    """Assign deterministic R3 commitments: AIRP + LC + CORE.

    Returns {"airp_assignments": {name: session_id}, "r3s": [Resident, ...]}.
    """
    r3s = [r for r in residents if r.r_year == 3]
    airp_assignments = assign_airp(r3s, grid)
    assign_learning_center(r3s, grid, core_exam_block, lc_weeks=lc_weeks)
    if core_weeks:
        assign_core(r3s, grid, core_weeks)
    return {"airp_assignments": airp_assignments, "r3s": r3s}


def fill_r3_clinical(
    residents: list[Resident],
    grid: ScheduleGrid,
    staffing_constraints: list[StaffingConstraint] | None = None,
) -> dict[str, dict]:
    """Fill R3 graduation requirements + remaining empty blocks.

    Should be called after NF is placed so staffing-aware rotation
    choices account for NF absences.

    Returns per-resident schedule metadata.
    """
    r3s = [r for r in residents if r.r_year == 3]
    metadata = {}
    for res in r3s:
        req_filled = _fill_r3_requirements(res, grid, staffing_constraints)
        remaining_filled = _fill_r3_remaining(res, grid, staffing_constraints)
        metadata[res.name] = {
            "filled_blocks": {**req_filled, **remaining_filled},
        }
    return metadata


def build_r3_schedules(
    residents: list[Resident],
    grid: ScheduleGrid,
    core_exam_block: int = 8,
    staffing_constraints: list[StaffingConstraint] | None = None,
    lc_weeks: list[int] | None = None,
    core_weeks: list[int] | None = None,
) -> dict[str, dict]:
    """Build R3 schedules: AIRP + LC + CORE + graduation requirements + fill remaining.

    Convenience wrapper that runs both fixed and clinical fill phases.
    Returns per-resident schedule metadata.
    """
    fixed = assign_r3_fixed(residents, grid, core_exam_block,
                            lc_weeks=lc_weeks, core_weeks=core_weeks)
    airp_assignments = fixed["airp_assignments"]

    clinical_meta = fill_r3_clinical(residents, grid, staffing_constraints)

    # Merge airp info into clinical metadata
    metadata = {}
    r3s = [r for r in residents if r.r_year == 3]
    for res in r3s:
        meta = clinical_meta.get(res.name, {"filled_blocks": {}})
        meta["airp_session"] = airp_assignments.get(res.name, "")
        metadata[res.name] = meta

    return metadata


def _fill_r3_requirements(
    res: Resident,
    grid: ScheduleGrid,
    staffing_constraints: list[StaffingConstraint] | None = None,
) -> dict[int, str]:
    """Fill remaining empty blocks for an R3 resident with required rotations.

    Iterates rotation-first: for each needed rotation, find the best
    available block.  This avoids dropping rotations when a single block
    has a hospital-system conflict.

    Respects:
    - Hospital system conflicts
    - No Zir in or after the block before LC
    - Zir block preferences
    - NRDR/ESIR/ESNR/T32 pathway requirements
    - Staffing need (prefers blocks with the largest deficit for a rotation)
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
        if rotation in _ROTATION_YEAR_ELIGIBILITY and 3 not in _ROTATION_YEAR_ELIGIBILITY[rotation]:
            continue
        blocks_needed = max(1, round(count))
        for _ in range(blocks_needed):
            needed_rotations.append(rotation)

    # Also add deficient sections not already covered
    for section in res.deficient_sections:
        if section not in needed_rotations:
            needed_rotations.append(section)

    # Sort needed rotations by section preference (preferred first, bottom last)
    if res.section_prefs and res.section_prefs.scores:
        _pref_scores = res.section_prefs.scores
        needed_rotations.sort(key=lambda r: -_pref_scores.get(r, 0))

    # Runtime breast deficit — ensure Pcbi is in needed_rotations with correct count
    breast_codes = {"Pcbi", "Sbi"}
    breast_total = sum(res.history.get(c, 0) for c in breast_codes)
    for w, code in res.schedule.items():
        if code in breast_codes:
            breast_total += 1
    breast_deficit_weeks = max(0, 12 - breast_total)
    breast_blocks_needed = -(-breast_deficit_weeks // 4)  # ceil division
    if breast_blocks_needed > 0:
        existing_pcbi = needed_rotations.count("Pcbi")
        for _ in range(breast_blocks_needed - existing_pcbi):
            needed_rotations.insert(0, "Pcbi")  # high priority

    # NRDR: need 6 blocks Mnuc
    if res.is_nrdr:
        mnuc_needed = 6 - needed_rotations.count("Mnuc")
        for _ in range(max(0, mnuc_needed)):
            needed_rotations.insert(0, "Mnuc")

    # Build code→groups map for staffing-aware block scoring
    from schedule_maker.staffing_utils import _build_code_to_groups, get_staffing_need
    code_to_groups = _build_code_to_groups(staffing_constraints, r_year=3)

    # Cap Zir to 1 block per R3
    zir_entries = [i for i, r in enumerate(needed_rotations) if r == "Zir"]
    for idx in zir_entries[1:]:
        needed_rotations[idx] = None  # type: ignore[assignment]
    needed_rotations = [r for r in needed_rotations if r is not None]

    # Assign rotations to available blocks (rotation-first iteration)
    used_blocks: set[int] = set()
    zir_placed = False
    for code in needed_rotations:
        if code == "Zir" and zir_placed:
            continue

        # Collect eligible blocks with their staffing scores
        eligible: list[tuple[int, float]] = []
        for block in available_blocks:
            if block in used_blocks:
                continue

            # No Zir in the block immediately before LC or later
            if code == "Zir" and lc_block and block >= lc_block - 1:
                continue

            if _has_hospital_conflict(res.schedule, block, code):
                continue

            if block_exceeds_max(grid, block, code):
                continue

            # Score by staffing need (higher = more understaffed)
            score = 0.0

            # Zir block preferences: soft bonus instead of hard filter
            zir_bonus = 0.0
            if code == "Zir" and res.zir_prefs and res.zir_prefs.preferred_blocks:
                if block in res.zir_prefs.preferred_blocks:
                    zir_bonus = 2.0

            # Schedule weight bonus from comments
            weight_bonus = 0.0
            if res.schedule_weight == "front-heavy":
                weight_bonus = 1.0 if block <= 6 else (-0.5 if block >= 10 else 0.0)
            elif res.schedule_weight == "back-heavy":
                weight_bonus = 1.0 if block >= 8 else (-0.5 if block <= 4 else 0.0)

            groups = code_to_groups.get(code, [])
            for codes_set, min_req in groups:
                for w in grid.block_to_weeks(block):
                    score += get_staffing_need(grid, w, codes_set, min_req)
            eligible.append((block, score + zir_bonus + weight_bonus))

        if eligible:
            # Pick the block with the highest staffing need
            best_block = max(eligible, key=lambda x: x[1])[0]
            _assign_block(res, grid, best_block, code)
            filled[best_block] = code
            used_blocks.add(best_block)
            if code == "Zir":
                zir_placed = True

    return filled


def _fill_r3_remaining(
    res: Resident,
    grid: ScheduleGrid,
    staffing_constraints: list[StaffingConstraint] | None = None,
) -> dict[int, str]:
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

    # Fill remaining with staffing-need + preference rotations
    fill_rotations = build_fill_candidates(staffing_constraints, r_year=3)
    # Expand with any preferred rotations not already in the list
    if res.section_prefs and res.section_prefs.top:
        for code in res.section_prefs.top:
            if code not in fill_rotations and \
               (code not in _ROTATION_YEAR_ELIGIBILITY or 3 in _ROTATION_YEAR_ELIGIBILITY[code]):
                fill_rotations.append(code)
    # Sort available blocks by schedule weight preference
    if res.schedule_weight == "front-heavy":
        available_blocks.sort()
    elif res.schedule_weight == "back-heavy":
        available_blocks.sort(reverse=True)

    for block in list(available_blocks):
        has_zir = any(v == "Zir" for v in res.schedule.values())
        ranked = rank_rotations_by_combined_score(
            grid, block, fill_rotations, res.section_prefs,
            constraints=staffing_constraints, r_year=3,
        )
        for code, _score in ranked:
            if code == "Zir" and has_zir:
                continue
            if not _has_hospital_conflict(res.schedule, block, code) and \
               not block_exceeds_max(grid, block, code):
                _assign_block(res, grid, block, code)
                available_blocks.remove(block)
                filled[block] = code
                break

    return filled


def _assign_block(res: Resident, grid: ScheduleGrid, block: int, code: str) -> None:
    """Assign a rotation code to all weeks of a block."""
    for w in grid.block_to_weeks(block):
        grid.assign(res.name, w, code)
        res.schedule[w] = code
