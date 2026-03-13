"""Phase 3: R3 schedule builder."""

from __future__ import annotations

import random as _random

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import get_hospital_system, get_same_section_codes, HospitalSystem
from schedule_maker.models.constraints import StaffingConstraint
from schedule_maker.staffing_utils import (
    rank_rotations_by_need, rank_rotations_by_combined_score,
    block_exceeds_max, build_fill_candidates,
    compute_run_penalty, block_has_nf,
    _ROTATION_YEAR_ELIGIBILITY,
)

_RUN_PENALTY_WEIGHT = 8.0
_FILL_NOISE_SIGMA = 0.5
_IR_CODES = {"Zir", "Vir", "Sir"}


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


def _build_airp_sessions(residents: list[Resident]) -> dict[str, list[int]]:
    """Build AIRP sessions from resident preferences.

    Returns {session_id: [week_numbers]}, built from the session_weeks
    data populated during preference parsing.
    """
    sessions: dict[str, list[int]] = {}
    for res in residents:
        if res.airp_prefs and res.airp_prefs.session_weeks:
            for session_id, weeks in res.airp_prefs.session_weeks.items():
                if session_id not in sessions:
                    sessions[session_id] = weeks
    return sessions


def assign_airp(
    residents: list[Resident],
    grid: ScheduleGrid,
    sessions: dict[str, list[int]] | None = None,
) -> dict[str, str]:
    """Assign R3s to AIRP sessions based on preferences.

    If sessions is None, builds session list from resident AIRP preferences.
    Sessions map session_id → list of week numbers.

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

        # Resolve group requests to canonical names and store back
        resolved_groupmates: list[str] = []
        if res.airp_prefs.group_requests:
            resolved_groupmates = _resolve_groupmates(res.airp_prefs.group_requests)
            res.airp_prefs.group_requests = resolved_groupmates

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
            for w in sessions[best_session]:
                grid.assign(res.name, w, "AIRP")
                res.schedule[w] = "AIRP"
            assigned = True

        if not assigned:
            # Assign to least-full session
            least = min(session_counts, key=lambda k: session_counts[k])
            session_counts[least] += 1
            assignments[res.name] = least
            for w in sessions[least]:
                grid.assign(res.name, w, "AIRP")
                res.schedule[w] = "AIRP"

    # Second pass: assign R3s who had no AIRP rankings to least-full session
    for res in r3s:
        if res.name in assignments:
            continue
        least = min(session_counts, key=lambda k: session_counts[k])
        session_counts[least] += 1
        assignments[res.name] = least
        for w in sessions[least]:
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
    rng: _random.Random | None = None,
    shuffle_residents: bool = False,
    shuffle_blocks: bool = False,
    top_k_sample: int = 1,
) -> dict[str, dict]:
    """Fill R3 graduation requirements + remaining empty blocks.

    Should be called after NF is placed so staffing-aware rotation
    choices account for NF absences.

    Args:
        rng: Optional random number generator for stochastic scoring.
             When provided, small Gaussian noise is added to scores at
             decision points, enabling multi-trial optimization.
        shuffle_residents: Randomize resident processing order within
             pathway groups (NRDR always first for Mnuc cap constraints).
        shuffle_blocks: Randomize block processing order within
             schedule weight groups.
        top_k_sample: Sample from top K rotations instead of picking
             the single best. Set to 1 for deterministic behavior.

    Returns per-resident schedule metadata.
    """
    r3s = [r for r in residents if r.r_year == 3]
    # Process NRDR R3s first — they need 6 blocks Mnuc against a cap of 5/week
    nrdr_r3s = [r for r in r3s if r.is_nrdr]
    non_nrdr_r3s = [r for r in r3s if not r.is_nrdr]

    if shuffle_residents and rng:
        rng.shuffle(nrdr_r3s)
        rng.shuffle(non_nrdr_r3s)
    else:
        nrdr_r3s.sort(key=lambda r: r.name)
        non_nrdr_r3s.sort(key=lambda r: r.name)

    r3s = nrdr_r3s + non_nrdr_r3s

    metadata = {}
    for res in r3s:
        req_filled = _fill_r3_requirements(
            res, grid, staffing_constraints, rng=rng,
            shuffle_blocks=shuffle_blocks, top_k_sample=top_k_sample,
        )
        remaining_filled = _fill_r3_remaining(
            res, grid, staffing_constraints, rng=rng,
            shuffle_blocks=shuffle_blocks, top_k_sample=top_k_sample,
        )
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
    rng: _random.Random | None = None,
    shuffle_blocks: bool = False,
    top_k_sample: int = 1,
) -> dict[int, str]:
    """Fill remaining empty blocks for an R3 resident with required rotations.

    Uses block-first iteration so rotations from recommended_blocks are
    interleaved naturally rather than placing all N blocks of rotation X
    before any blocks of rotation Y.

    Respects:
    - Hospital system conflicts
    - No Zir in or after the block before LC
    - Zir block preferences
    - NRDR/ESIR/ESNR/T32 pathway requirements
    - Staffing need (prefers blocks with the largest deficit for a rotation)

    Args:
        shuffle_blocks: Randomize block order within schedule weight groups.
        top_k_sample: Sample from top K rotations instead of best.
    """
    from schedule_maker.staffing_utils import weighted_sample_top_k
    filled = {}

    # Get available blocks (not yet assigned)
    available_blocks = []
    for block in range(1, 14):
        weeks = list(grid.block_to_weeks(block))
        if not all(res.schedule.get(w) for w in weeks):
            available_blocks.append(block)

    # Determine LC block
    lc_block = None
    for block in range(1, 14):
        weeks = list(grid.block_to_weeks(block))
        if any(res.schedule.get(w) == "LC" for w in weeks):
            lc_block = block
            break

    # Build remaining_counts from recommended_blocks
    remaining_counts: dict[str, int] = {}
    for rotation, count in res.recommended_blocks.items():
        if rotation in _ROTATION_YEAR_ELIGIBILITY and 3 not in _ROTATION_YEAR_ELIGIBILITY[rotation]:
            continue
        remaining_counts[rotation] = max(1, round(count))

    # Cap Zir to 1 block per R3
    if "Zir" in remaining_counts:
        remaining_counts["Zir"] = min(remaining_counts["Zir"], 1)

    # Breast deficit — Pcbi gets large priority bonus
    breast_codes = {"Pcbi", "Sbi"}
    breast_total = sum(res.history.get(c, 0) for c in breast_codes)
    for w, code in res.schedule.items():
        if code in breast_codes:
            breast_total += 1
    breast_deficit_weeks = max(0, 12 - breast_total)
    breast_blocks_needed = -(-breast_deficit_weeks // 4)  # ceil division
    if breast_blocks_needed > 0:
        remaining_counts["Pcbi"] = max(remaining_counts.get("Pcbi", 0), breast_blocks_needed)

    # NRDR: need 6 blocks Mnuc (large priority bonus applied in scoring)
    if res.is_nrdr:
        remaining_counts["Mnuc"] = max(remaining_counts.get("Mnuc", 0), 6)

    # Add deficient sections (low priority — 1 block each if not already in pool)
    from schedule_maker.models.rotation import ROTATION_SECTION
    for section in res.deficient_sections:
        code = section
        if code not in ROTATION_SECTION:
            continue
        if code in _ROTATION_YEAR_ELIGIBILITY and 3 not in _ROTATION_YEAR_ELIGIBILITY[code]:
            alternatives = get_same_section_codes(code)
            eligible = [c for c in alternatives
                        if c not in _ROTATION_YEAR_ELIGIBILITY or 3 in _ROTATION_YEAR_ELIGIBILITY[c]]
            code = eligible[0] if eligible else None
        if code and code not in remaining_counts:
            remaining_counts[code] = 1

    # Build code→groups map for staffing-aware block scoring
    from schedule_maker.staffing_utils import _build_code_to_groups, get_staffing_need
    code_to_groups = _build_code_to_groups(staffing_constraints, r_year=3)

    # Sort available blocks by schedule weight preference
    # When shuffle_blocks is enabled, shuffle within schedule weight groups
    if shuffle_blocks and rng:
        early = [b for b in available_blocks if b <= 6]
        mid = [b for b in available_blocks if 6 < b < 10]
        late = [b for b in available_blocks if b >= 10]
        rng.shuffle(early)
        rng.shuffle(mid)
        rng.shuffle(late)
        if res.schedule_weight == "back-heavy":
            sorted_blocks = late + mid + early
        elif res.schedule_weight == "front-heavy":
            sorted_blocks = early + mid + late
        else:
            sorted_blocks = early + mid + late
    elif res.schedule_weight == "back-heavy":
        sorted_blocks = sorted(available_blocks, reverse=True)
    else:
        sorted_blocks = sorted(available_blocks)

    zir_placed = False

    # Block-first iteration: for each block pick best rotation from remaining pool
    for block in sorted_blocks:
        if not any(v > 0 for v in remaining_counts.values()):
            break

        scored_rotations: list[tuple[str, float]] = []

        for rotation, remaining in remaining_counts.items():
            if remaining <= 0:
                continue

            # Zir constraints
            if rotation == "Zir":
                if zir_placed:
                    continue
                if not _block_fully_available(res, grid, block):
                    continue
                if lc_block and block >= lc_block - 1:
                    continue

            if _has_hospital_conflict(res.schedule, block, rotation):
                continue

            # NRDR Mnuc: graduation requirement takes precedence over max cap
            if block_exceeds_max(grid, block, rotation) and not (res.is_nrdr and rotation == "Mnuc"):
                continue

            # No IR on blocks with existing NF assignments
            if rotation in _IR_CODES and block_has_nf(res.schedule, block, grid, resident_name=res.name):
                continue

            score = 0.0

            # Preference bonus
            pref_score = res.section_prefs.scores.get(rotation, 0) if res.section_prefs else 0
            score += 1.0 * pref_score

            # Zir block preferences: soft bonus
            if rotation == "Zir" and res.zir_prefs and res.zir_prefs.preferred_blocks:
                if block in res.zir_prefs.preferred_blocks:
                    score += 2.0

            # NRDR Mnuc and breast deficit: large priority bonuses
            if res.is_nrdr and rotation == "Mnuc":
                score += 20.0
            if rotation in ("Pcbi", "Sbi") and breast_blocks_needed > 0:
                score += 20.0

            # Schedule weight bonus from comments
            if res.schedule_weight == "front-heavy":
                score += 1.0 if block <= 6 else (-0.5 if block >= 10 else 0.0)
            elif res.schedule_weight == "back-heavy":
                score += 1.0 if block >= 8 else (-0.5 if block <= 4 else 0.0)

            # Staffing need
            groups = code_to_groups.get(rotation, [])
            for codes_set, min_req in groups:
                for w in grid.block_to_weeks(block):
                    score += get_staffing_need(grid, w, codes_set, min_req)

            # Run penalty: discourage consecutive same-rotation blocks
            # NRDR R3s doing 6 blocks Mnuc — consecutive is expected/desired
            run_pen = 0.0 if (res.is_nrdr and rotation == "Mnuc") else compute_run_penalty(res.schedule, block, rotation, grid)
            score -= _RUN_PENALTY_WEIGHT * run_pen

            scored_rotations.append((rotation, score))

        if not scored_rotations:
            continue

        # Select rotation: top-K sampling when rng provided, else pick best
        if rng is not None and top_k_sample > 1 and len(scored_rotations) > 1:
            best_code, _ = weighted_sample_top_k(scored_rotations, top_k_sample, rng)
        else:
            # Add noise if rng provided (legacy behavior for top_k_sample=1)
            if rng is not None:
                scored_rotations = [(c, s + rng.gauss(0, _FILL_NOISE_SIGMA)) for c, s in scored_rotations]
            scored_rotations.sort(key=lambda x: -x[1])
            best_code = scored_rotations[0][0]

        _assign_block(res, grid, block, best_code)
        filled[block] = best_code
        remaining_counts[best_code] -= 1
        if best_code == "Zir":
            zir_placed = True

    return filled


def _fill_r3_remaining(
    res: Resident,
    grid: ScheduleGrid,
    staffing_constraints: list[StaffingConstraint] | None = None,
    rng: _random.Random | None = None,
    shuffle_blocks: bool = False,
    top_k_sample: int = 1,
) -> dict[int, str]:
    """Fill remaining empty R3 blocks with general clinical rotations.

    After graduation requirements are placed, any empty blocks are filled
    with rotations that help cover staffing needs: Peds (if short), then
    a round-robin of common clinical services.

    Args:
        shuffle_blocks: Randomize block order within schedule weight groups.
        top_k_sample: Sample from top K rotations instead of best.
    """
    from schedule_maker.staffing_utils import weighted_sample_top_k
    filled = {}

    available_blocks = []
    for block in range(1, 14):
        weeks = list(grid.block_to_weeks(block))
        if not all(res.schedule.get(w) for w in weeks):
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
    # When shuffle_blocks is enabled, shuffle within schedule weight groups
    if shuffle_blocks and rng:
        early = [b for b in available_blocks if b <= 6]
        mid = [b for b in available_blocks if 6 < b < 10]
        late = [b for b in available_blocks if b >= 10]
        rng.shuffle(early)
        rng.shuffle(mid)
        rng.shuffle(late)
        if res.schedule_weight == "back-heavy":
            available_blocks = late + mid + early
        elif res.schedule_weight == "front-heavy":
            available_blocks = early + mid + late
        else:
            available_blocks = early + mid + late
    elif res.schedule_weight == "front-heavy":
        available_blocks.sort()
    elif res.schedule_weight == "back-heavy":
        available_blocks.sort(reverse=True)

    # Determine LC block for Zir eligibility check
    _lc_block = None
    for _b in range(1, 14):
        if any(res.schedule.get(w) == "LC" for w in grid.block_to_weeks(_b)):
            _lc_block = _b
            break

    for block in list(available_blocks):
        has_zir = any(v == "Zir" for v in res.schedule.values())
        ranked = rank_rotations_by_combined_score(
            grid, block, fill_rotations, res.section_prefs,
            constraints=staffing_constraints, r_year=3,
        )
        # Apply randomization: either top-K sampling or Gaussian noise
        if rng is not None:
            if top_k_sample > 1 and len(ranked) > 1:
                # Use weighted sampling; don't add noise since sampling provides exploration
                pass  # ranked stays as-is, sampling happens below
            else:
                ranked = sorted(
                    [(c, s + rng.gauss(0, _FILL_NOISE_SIGMA)) for c, s in ranked],
                    key=lambda x: -x[1],
                )

        # Force Zir to top when it has 0 staffing and resident is eligible
        if not has_zir and (_lc_block is None or block < _lc_block - 1) \
                and _block_fully_available(res, grid, block) \
                and not _has_hospital_conflict(res.schedule, block, "Zir") \
                and not block_exceeds_max(grid, block, "Zir") \
                and not block_has_nf(res.schedule, block, grid, resident_name=res.name):
            zir_unstaffed = all(
                grid.get_section_staffing(w, {"Zir"}) < 1
                for w in grid.block_to_weeks(block)
            )
            if zir_unstaffed:
                ranked = [(c, s) for c, s in ranked if c != "Zir"]
                ranked.insert(0, ("Zir", float("inf")))

        # Force Mnuc to top for NRDR R3s who still need more Mnuc blocks
        nrdr_mnuc_deficit = False
        if res.is_nrdr:
            mnuc_placed = sum(1 for v in res.schedule.values() if v == "Mnuc")
            nrdr_mnuc_deficit = mnuc_placed < 24
            if nrdr_mnuc_deficit and not _has_hospital_conflict(res.schedule, block, "Mnuc"):
                ranked = [(c, s) for c, s in ranked if c != "Mnuc"]
                ranked.insert(0, ("Mnuc", float("inf")))

        # Helper to check if a rotation is valid for this block
        def _is_valid_rotation(c: str) -> bool:
            if c == "Zir" and has_zir:
                return False
            if c == "Zir" and not _block_fully_available(res, grid, block):
                return False
            if c == "Zir" and _lc_block is not None and block >= _lc_block - 1:
                return False
            if c in _IR_CODES and block_has_nf(res.schedule, block, grid, resident_name=res.name):
                return False
            nrdr_override = nrdr_mnuc_deficit and c == "Mnuc"
            if _has_hospital_conflict(res.schedule, block, c):
                return False
            if not nrdr_override and block_exceeds_max(grid, block, c):
                return False
            return True

        # Filter to valid rotations
        valid_ranked = [(c, s) for c, s in ranked if _is_valid_rotation(c)]
        if not valid_ranked:
            continue

        # Use top-K sampling when enabled, otherwise pick best with run penalty logic
        if rng is not None and top_k_sample > 1 and len(valid_ranked) > 1:
            code, _ = weighted_sample_top_k(valid_ranked, top_k_sample, rng)
        else:
            code, _score = valid_ranked[0]
            # Penalize consecutive same-rotation runs; prefer lowest-penalty alternative
            # NRDR R3s doing 6 blocks Mnuc — consecutive is expected/desired
            run_pen = 0.0 if (res.is_nrdr and code == "Mnuc") else compute_run_penalty(res.schedule, block, code, grid)
            if run_pen > 0:
                candidates_by_penalty = sorted(
                    [
                        (c, (0.0 if (res.is_nrdr and c == "Mnuc") else compute_run_penalty(res.schedule, block, c, grid)))
                        for c, _ in valid_ranked
                        if c != code
                    ],
                    key=lambda x: x[1],
                )
                if candidates_by_penalty:
                    alt_code, alt_pen = candidates_by_penalty[0]
                    if alt_pen < run_pen:
                        code = alt_code

        _assign_block(res, grid, block, code)
        available_blocks.remove(block)
        filled[block] = code

    return filled


def _block_fully_available(res: Resident, grid: ScheduleGrid, block: int) -> bool:
    """Return True if all 4 weeks of the block are unassigned for the resident."""
    return all(not res.schedule.get(w) for w in grid.block_to_weeks(block))


def _assign_block(res: Resident, grid: ScheduleGrid, block: int, code: str) -> None:
    """Assign a rotation code to all weeks of a block, skipping already-assigned weeks."""
    for w in grid.block_to_weeks(block):
        if not res.schedule.get(w):
            grid.assign(res.name, w, code)
            res.schedule[w] = code
