"""Phase 4: R4 schedule builder."""

from __future__ import annotations

from schedule_maker.models.resident import Resident, Pathway, SectionPrefs
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem, SECTION_TO_ROTATION_CODES
from schedule_maker.models.constraints import StaffingConstraint
from schedule_maker.staffing_utils import (
    rank_rotations_by_need, rank_rotations_by_combined_score,
    block_exceeds_max, build_fill_candidates,
    _ROTATION_YEAR_ELIGIBILITY,
)


HOSPITAL_CONFLICT_EXEMPT: set[str] = {"Ding, Kevin"}
_ORG_PREF_WEIGHT = 0.3  # lowest weight of any soft constraint


def _org_pref_score(block: int, placed_blocks: list[int], pref: str) -> float:
    """Score a block based on organization preference (contiguous vs interspersed)."""
    if not pref or not placed_blocks:
        return 0.0
    min_dist = min(abs(block - b) for b in placed_blocks)
    if pref == "contiguous":
        return _ORG_PREF_WEIGHT if min_dist <= 1 else -_ORG_PREF_WEIGHT
    elif pref == "interspersed":
        return _ORG_PREF_WEIGHT if min_dist >= 3 else -_ORG_PREF_WEIGHT
    return 0.0


def _r4_zir_eligible(res: Resident) -> bool:
    """Check if an R4 is eligible for Zir (ESIR or IR FSE, never T32)."""
    if res.is_t32:
        return False
    return res.is_esir or (
        res.fse_prefs is not None
        and any(s.lower() == "ir" for s in res.fse_prefs.specialties)
    )


def assign_r4_fixed(
    residents: list[Resident],
    grid: ScheduleGrid,
    t32_clinical_blocks: list[int] | None = None,
    lc_block: int = 12,
) -> dict[str, dict]:
    """Place deterministic R4 commitments: T32 research, Res/CEP, NRDR Mnuc,
    ESIR Mir, ESNR neuro, FSE.

    Should be called before NF solver so fixed commitments are visible
    in the base schedule.

    Returns per-resident metadata with 'available_after_fixed' lists.
    """
    if t32_clinical_blocks is None:
        t32_clinical_blocks = [12, 13]

    r4s = [r for r in residents if r.r_year == 4]
    metadata = {}

    for res in r4s:
        meta = {}
        if res.is_t32:
            _build_t32_schedule(res, grid, meta, t32_clinical_blocks)
        else:
            _place_fixed_commitments(res, grid, meta, lc_block=lc_block)
        metadata[res.name] = meta

    return metadata


def fill_r4_clinical(
    residents: list[Resident],
    grid: ScheduleGrid,
    all_residents: list[Resident] | None = None,
    fixed_meta: dict[str, dict] | None = None,
    staffing_constraints: list[StaffingConstraint] | None = None,
    lc_block: int = 12,
) -> dict[str, dict]:
    """Fill R4 graduation requirements + remaining blocks.

    Should be called after NF is placed so staffing-aware rotation
    choices account for NF absences.

    Args:
        residents: R4 residents
        grid: schedule grid
        all_residents: all residents (for staffing needs assessment)
        fixed_meta: metadata from assign_r4_fixed (carries available_after_fixed)
        staffing_constraints: dynamic staffing constraints from Excel

    Returns per-resident metadata (merged with fixed_meta).
    """
    if fixed_meta is None:
        fixed_meta = {}

    r4s = [r for r in residents if r.r_year == 4]
    metadata = {}

    for res in r4s:
        meta = dict(fixed_meta.get(res.name, {}))

        if not res.is_t32:
            _fill_grad_requirements(res, grid, meta, staffing_constraints, lc_block=lc_block)
            _fill_remaining(res, grid, meta, all_residents, staffing_constraints, lc_block=lc_block)

        metadata[res.name] = meta

    return metadata


def build_r4_schedules(
    residents: list[Resident],
    grid: ScheduleGrid,
    all_residents: list[Resident] | None = None,
    t32_clinical_blocks: list[int] | None = None,
    staffing_constraints: list[StaffingConstraint] | None = None,
    lc_block: int = 12,
) -> dict[str, dict]:
    """Build R4 schedules: fixed commitments → grad reqs → fill remaining.

    Convenience wrapper that runs both fixed and clinical fill phases.

    Args:
        residents: R4 residents
        grid: schedule grid
        all_residents: all residents (for staffing needs assessment)
        t32_clinical_blocks: blocks where T32 residents may be assigned
            clinical coverage (typically May + first two weeks of June,
            when R3s are on LC/CORE). Defaults to blocks 12-13.
        staffing_constraints: dynamic staffing constraints from Excel

    Returns:
        Per-resident schedule metadata.
    """
    fixed_meta = assign_r4_fixed(residents, grid, t32_clinical_blocks, lc_block=lc_block)
    return fill_r4_clinical(residents, grid, all_residents, fixed_meta, staffing_constraints, lc_block=lc_block)


def _build_t32_schedule(
    res: Resident,
    grid: ScheduleGrid,
    meta: dict,
    clinical_blocks: list[int],
) -> None:
    """Build schedule for a T32 resident.

    T32 residents are on research for the entire year except during
    the LC/CORE coverage period (May + first two weeks of June),
    when they may be assigned clinical rotations to help cover staffing.
    """
    # Fill all non-clinical blocks with research
    research_blocks = []
    for block in range(1, 14):
        if block not in clinical_blocks:
            _assign_block(res, grid, block, "Res")
            research_blocks.append(block)
    meta["research_blocks"] = len(research_blocks)

    # Fill clinical blocks from graduation requirements first, then staffing
    clinical_filled = {}
    available = list(clinical_blocks)

    # Runtime breast deficit — prioritize breast in clinical blocks
    breast_codes = {"Pcbi", "Sbi"}
    breast_total = sum(res.history.get(c, 0) for c in breast_codes)
    for w, code in res.schedule.items():
        if code in breast_codes:
            breast_total += 1
    breast_deficit_weeks = max(0, 12 - breast_total)
    breast_blocks_needed = -(-breast_deficit_weeks // 4)

    placed_breast = 0
    for block in list(available):
        if placed_breast >= breast_blocks_needed:
            break
        for try_code in ("Pcbi", "Sbi"):
            if not _has_hospital_conflict(res.schedule, block, try_code) and \
               not block_exceeds_max(grid, block, try_code):
                _assign_block(res, grid, block, try_code)
                available.remove(block)
                clinical_filled[block] = try_code
                placed_breast += 1
                break

    # Check graduation deficiencies — place those first
    for rotation, count in sorted(res.recommended_blocks.items(),
                                   key=lambda x: -x[1]):
        if rotation in _ROTATION_YEAR_ELIGIBILITY and 4 not in _ROTATION_YEAR_ELIGIBILITY[rotation]:
            continue
        if rotation == "Zir":
            continue
        blocks_needed = max(1, round(count))
        placed = 0
        for block in list(available):
            if placed >= blocks_needed:
                break
            if not _has_hospital_conflict(res.schedule, block, rotation) and \
               not block_exceeds_max(grid, block, rotation):
                _assign_block(res, grid, block, rotation)
                available.remove(block)
                clinical_filled[block] = rotation
                placed += 1

    # Fill any remaining clinical blocks with staffing-need rotations
    fill_rotations = build_fill_candidates(r_year=4)
    for block in list(available):
        ranked = rank_rotations_by_need(grid, block, fill_rotations, r_year=4)
        for code, _deficit in ranked:
            if code == "Zir":
                continue
            if not _has_hospital_conflict(res.schedule, block, code) and \
               not block_exceeds_max(grid, block, code):
                _assign_block(res, grid, block, code)
                available.remove(block)
                clinical_filled[block] = code
                break

    meta["t32_clinical_filled"] = clinical_filled
    meta["available_after_fixed"] = []
    meta["available_after_grad"] = []
    meta["grad_req_filled"] = {}
    meta["remaining_filled"] = {}


def _fse_to_rotation_code(fse_name: str) -> str:
    """Map an FSE specialty name to its actual rotation code.

    E.g. "Breast" → "Pcbi", "AI" → "Mai", "Cardiac" → "Mch".
    Falls back to first code from SECTION_TO_ROTATION_CODES or FSE-Xxx prefix.
    """
    # Try exact match first
    for section, codes in SECTION_TO_ROTATION_CODES.items():
        if section.lower() == fse_name.lower():
            return codes[0]
    # Try substring match
    for section, codes in SECTION_TO_ROTATION_CODES.items():
        if section.lower() in fse_name.lower() or fse_name.lower() in section.lower():
            return codes[0]
    # Fallback
    return f"FSE-{fse_name[:3]}"


def _place_fixed_commitments(res: Resident, grid: ScheduleGrid, meta: dict, lc_block: int = 12) -> None:
    """Place research/CEP, FSE, NRDR Mnuc, ESIR Mir, ESNR neuro blocks."""

    available_blocks = list(range(1, 14))

    # Block requests from comments (e.g. CEP in specific block)
    block_req_placed = 0
    if res.block_requests:
        for block, code in res.block_requests.items():
            if block in available_blocks and code in ("Res", "CEP"):
                _assign_block(res, grid, block, code)
                available_blocks.remove(block)
                block_req_placed += 1

    # Research/CEP (place in middle of year, avoid LC/RSNA periods)
    research_total = res.research_months + res.cep_months
    if research_total > 0:
        # Avoid blocks 7 (LC), 5-6 (RSNA area), prefer blocks 3-4, 8-10
        preferred = [3, 4, 8, 9, 10, 11, 2, 12]
        placed = block_req_placed
        for block in preferred:
            if placed >= research_total:
                break
            if block in available_blocks:
                code = "Res" if placed < res.research_months else "CEP"
                _assign_block(res, grid, block, code)
                available_blocks.remove(block)
                placed += 1
        meta["research_blocks"] = placed

    # NRDR: 6 blocks Mnuc
    if res.is_nrdr:
        mnuc_needed = 6
        placed = 0
        nrdr_placed: list[int] = []
        for _ in range(len(available_blocks)):
            if placed >= mnuc_needed:
                break
            candidates = sorted(
                available_blocks,
                key=lambda b: -_org_pref_score(b, nrdr_placed, res.pathway_org_pref),
            )
            for block in candidates:
                if not block_exceeds_max(grid, block, "Mnuc"):
                    _assign_block(res, grid, block, "Mnuc")
                    available_blocks.remove(block)
                    nrdr_placed.append(block)
                    placed += 1
                    break
            else:
                break
        meta["nrdr_mnuc_blocks"] = placed

    # ESIR: remaining Mir blocks (8 in R4 per goals.md)
    if res.is_esir:
        mir_needed = 8
        placed = 0
        esir_placed: list[int] = []
        for _ in range(len(available_blocks)):
            if placed >= mir_needed:
                break
            candidates = sorted(
                available_blocks,
                key=lambda b: -_org_pref_score(b, esir_placed, res.pathway_org_pref),
            )
            for block in candidates:
                if not block_exceeds_max(grid, block, "Mir"):
                    _assign_block(res, grid, block, "Mir")
                    available_blocks.remove(block)
                    esir_placed.append(block)
                    placed += 1
                    break
            else:
                break
        meta["esir_mir_blocks"] = placed

    # ESNR: 6 blocks neuro (max 1 on Smr)
    if res.is_esnr:
        neuro_needed = 6
        placed_mucic = 0
        placed_smr = 0
        for block in list(available_blocks):
            if placed_mucic + placed_smr >= neuro_needed:
                break
            if placed_smr < 1:
                code = "Smr"
            else:
                code = "Mucic"
            if not block_exceeds_max(grid, block, code):
                _assign_block(res, grid, block, code)
                if code == "Smr":
                    placed_smr += 1
                else:
                    placed_mucic += 1
                available_blocks.remove(block)
        meta["esnr_neuro_blocks"] = placed_mucic + placed_smr

    # FSE blocks — use actual rotation codes, not FSE-Xxx prefixes
    # Loop over ALL FSE specialties (not just the first)
    if res.fse_prefs and res.fse_prefs.specialties:
        exempt = res.name in HOSPITAL_CONFLICT_EXEMPT
        fse_codes_placed: list[str] = []
        total_fse_placed = 0
        for fse_name in res.fse_prefs.specialties:
            # Breast FSE requires 6 months
            if "breast" in fse_name.lower():
                fse_blocks = 6
            else:
                fse_blocks = 2  # typical FSE

            fse_code = _fse_to_rotation_code(fse_name)
            fse_org = getattr(res.fse_prefs, 'organization', '') if res.fse_prefs else ''

            placed = 0
            fse_placed_blocks: list[int] = []
            # Sort by org preference each iteration so newly placed blocks influence order
            for _ in range(len(available_blocks)):
                if placed >= fse_blocks:
                    break
                candidates = sorted(
                    available_blocks,
                    key=lambda b: -_org_pref_score(b, fse_placed_blocks, fse_org),
                )
                for block in candidates:
                    conflict = not exempt and _has_hospital_conflict(res.schedule, block, fse_code)
                    if not conflict and not block_exceeds_max(grid, block, fse_code):
                        _assign_block(res, grid, block, fse_code)
                        available_blocks.remove(block)
                        fse_placed_blocks.append(block)
                        placed += 1
                        break
                else:
                    break
            total_fse_placed += placed
            if placed > 0:
                fse_codes_placed.append(fse_code)
        meta["fse_blocks"] = total_fse_placed
        meta["fse_code"] = fse_codes_placed[0] if fse_codes_placed else ""

    meta["available_after_fixed"] = list(available_blocks)


def _fill_grad_requirements(
    res: Resident,
    grid: ScheduleGrid,
    meta: dict,
    staffing_constraints: list[StaffingConstraint] | None = None,
    lc_block: int = 12,
) -> None:
    """Fill graduation requirement deficiencies."""
    available = meta.get("available_after_fixed", [])
    if not available:
        return

    filled = {}

    # Runtime breast deficit check — place enough Pcbi to close the gap
    breast_codes = {"Pcbi", "Sbi"}
    breast_total = sum(res.history.get(c, 0) for c in breast_codes)
    for w, code in res.schedule.items():
        if code in breast_codes:
            breast_total += 1
    breast_deficit_weeks = max(0, 12 - breast_total)
    breast_blocks_needed = -(-breast_deficit_weeks // 4)  # ceil division

    placed_breast = 0
    for block in list(available):
        if placed_breast >= breast_blocks_needed:
            break
        for try_code in ("Pcbi", "Sbi"):
            if not _has_hospital_conflict(res.schedule, block, try_code) and \
               not block_exceeds_max(grid, block, try_code):
                _assign_block(res, grid, block, try_code)
                available.remove(block)
                filled[block] = try_code
                placed_breast += 1
                break

    # NucMed-deficient → Mnuc (or partial credit rotations)
    if any("Mnuc" in s or "nuc" in s.lower() or "Vnuc" in s for s in res.deficient_sections):
        for block in list(available):
            if not _has_hospital_conflict(res.schedule, block, "Mnuc") and \
               not block_exceeds_max(grid, block, "Mnuc"):
                _assign_block(res, grid, block, "Mnuc")
                available.remove(block)
                filled[block] = "Mnuc"
                break

    # Build code→groups map for staffing-aware block scoring
    from schedule_maker.staffing_utils import _build_code_to_groups, get_staffing_need
    code_to_groups = _build_code_to_groups(staffing_constraints, r_year=4)

    # Fill from recommended_blocks
    for rotation, count in sorted(res.recommended_blocks.items(), key=lambda x: -x[1]):
        if rotation in _ROTATION_YEAR_ELIGIBILITY and 4 not in _ROTATION_YEAR_ELIGIBILITY[rotation]:
            continue
        if rotation == "Zir" and not _r4_zir_eligible(res):
            continue
        blocks_needed = max(1, round(count))
        placed = 0
        # Score eligible blocks by staffing need, pick best first
        eligible: list[tuple[int, float]] = []
        for block in list(available):
            if rotation == "Zir" and block < lc_block - 1:
                continue
            if not _has_hospital_conflict(res.schedule, block, rotation) and \
               not block_exceeds_max(grid, block, rotation):
                score = 0.0
                groups = code_to_groups.get(rotation, [])
                for codes_set, min_req in groups:
                    for w in grid.block_to_weeks(block):
                        score += get_staffing_need(grid, w, codes_set, min_req)
                # Schedule weight bonus from comments
                if res.schedule_weight == "front-heavy":
                    score += 1.0 if block <= 6 else (-0.5 if block >= 10 else 0.0)
                elif res.schedule_weight == "back-heavy":
                    score += 1.0 if block >= 8 else (-0.5 if block <= 4 else 0.0)
                eligible.append((block, score))
        # Sort by staffing need descending (most understaffed first)
        eligible.sort(key=lambda x: -x[1])
        for block, _score in eligible:
            if placed >= blocks_needed:
                break
            _assign_block(res, grid, block, rotation)
            available.remove(block)
            filled[block] = rotation
            placed += 1

    meta["grad_req_filled"] = filled
    meta["available_after_grad"] = list(available)


def _fill_remaining(
    res: Resident,
    grid: ScheduleGrid,
    meta: dict,
    all_residents: list[Resident] | None,
    staffing_constraints: list[StaffingConstraint] | None = None,
    lc_block: int = 12,
) -> None:
    """Fill remaining empty blocks with Mx, Peds, MSK, etc."""
    available = meta.get("available_after_grad", [])
    if not available:
        return

    filled = {}

    # Sort available blocks by schedule weight preference
    if res.schedule_weight == "front-heavy":
        available.sort()
    elif res.schedule_weight == "back-heavy":
        available.sort(reverse=True)

    # Mx for all R4s except T32 or dual-pathway
    # Use recommended_blocks["Mx"] if available, otherwise default to 1
    mx_count = int(res.recommended_blocks.get("Mx", 1))
    if not res.is_t32 and not res.dual_pathway and mx_count > 0:
        placed = 0
        for block in list(available):
            if placed >= mx_count:
                break
            if not block_exceeds_max(grid, block, "Mx"):
                _assign_block(res, grid, block, "Mx")
                available.remove(block)
                filled[block] = "Mx"
                placed += 1

    # Fill remaining with staffing-need + preference rotations
    fill_rotations = build_fill_candidates(staffing_constraints, r_year=4)
    # Expand with any preferred rotations not already in the list
    if res.section_prefs and res.section_prefs.top:
        for code in res.section_prefs.top:
            if code not in fill_rotations and \
               (code not in _ROTATION_YEAR_ELIGIBILITY or 4 in _ROTATION_YEAR_ELIGIBILITY[code]):
                fill_rotations.append(code)

    # Boost FSE rotation codes with higher weight than general section prefs
    fse_pref_weight = 3  # default
    effective_prefs = res.section_prefs
    if res.fse_prefs and res.fse_prefs.specialties:
        fse_pref_weight = 5
        fse_codes = [_fse_to_rotation_code(s) for s in res.fse_prefs.specialties]
        # Build boosted prefs: copy existing scores and add FSE codes at max score
        base_scores = dict(effective_prefs.scores) if effective_prefs and effective_prefs.scores else {}
        base_top = list(effective_prefs.top) if effective_prefs else []
        for fc in fse_codes:
            base_scores[fc] = max(base_scores.get(fc, 0), 3)  # max positive score
            if fc not in base_top:
                base_top.append(fc)
            if fc not in fill_rotations and \
               (fc not in _ROTATION_YEAR_ELIGIBILITY or 4 in _ROTATION_YEAR_ELIGIBILITY[fc]):
                fill_rotations.append(fc)
        effective_prefs = SectionPrefs(
            top=base_top,
            bottom=list(effective_prefs.bottom) if effective_prefs else [],
            scores=base_scores,
        )

    exempt = res.name in HOSPITAL_CONFLICT_EXEMPT
    fse_code_set = set(fse_codes) if res.fse_prefs and res.fse_prefs.specialties else set()

    for block in list(available):
        ranked = rank_rotations_by_combined_score(
            grid, block, fill_rotations, effective_prefs,
            constraints=staffing_constraints, r_year=4,
            pref_weight=fse_pref_weight,
        )
        for code, _score in ranked:
            if code == "Zir" and (not _r4_zir_eligible(res) or block < lc_block - 1):
                continue
            skip_conflict = exempt and code in fse_code_set
            if (skip_conflict or not _has_hospital_conflict(res.schedule, block, code)) and \
               not block_exceeds_max(grid, block, code):
                _assign_block(res, grid, block, code)
                available.remove(block)
                filled[block] = code
                break

    # Warn if all blocks consumed by graduation requirements (no room for staffing flexibility)
    if not meta.get("available_after_grad"):
        meta["staffing_warning"] = (
            f"{res.name}: all blocks consumed by fixed/grad requirements — "
            f"no staffing-flexible blocks available"
        )

    meta["remaining_filled"] = filled


def _assign_block(res: Resident, grid: ScheduleGrid, block: int, code: str) -> None:
    """Assign a rotation code to all weeks of a block."""
    for w in grid.block_to_weeks(block):
        grid.assign(res.name, w, code)
        res.schedule[w] = code


def _has_hospital_conflict(schedule: dict[int, str], block: int, code: str) -> bool:
    """Check hospital system conflict within a block."""
    target = get_hospital_system(code)
    if target == HospitalSystem.OTHER:
        return False
    start = (block - 1) * 4 + 1
    for w in range(start, start + 4):
        existing = schedule.get(w, "")
        if existing:
            sys = get_hospital_system(existing)
            if sys != HospitalSystem.OTHER and sys != target:
                return True
    return False
