"""Phase 4: R4 schedule builder."""

from __future__ import annotations

from schedule_maker.models.resident import Resident, Pathway
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem


def build_r4_schedules(
    residents: list[Resident],
    grid: ScheduleGrid,
    all_residents: list[Resident] | None = None,
) -> dict[str, dict]:
    """Build R4 schedules: fixed commitments → grad reqs → fill remaining.

    Args:
        residents: R4 residents
        grid: schedule grid
        all_residents: all residents (for staffing needs assessment)

    Returns:
        Per-resident schedule metadata.
    """
    r4s = [r for r in residents if r.r_year == 4]
    metadata = {}

    for res in r4s:
        meta = {}

        # Step 1: Place fixed commitments
        _place_fixed_commitments(res, grid, meta)

        # Step 2: Fill graduation requirements
        _fill_grad_requirements(res, grid, meta)

        # Step 3: Fill remaining capacity (Mx, Peds, MSK, etc.)
        _fill_remaining(res, grid, meta, all_residents)

        metadata[res.name] = meta

    return metadata


def _place_fixed_commitments(res: Resident, grid: ScheduleGrid, meta: dict) -> None:
    """Place research/CEP, FSE, NRDR Mnuc, ESIR Mir, ESNR neuro blocks."""

    available_blocks = list(range(1, 14))

    # Research/CEP (place in middle of year, avoid LC/RSNA periods)
    research_total = res.research_months + res.cep_months
    if research_total > 0:
        # Avoid blocks 7 (LC), 5-6 (RSNA area), prefer blocks 3-4, 8-10
        preferred = [3, 4, 8, 9, 10, 11, 2, 12]
        placed = 0
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
        for block in list(available_blocks):
            if placed >= mnuc_needed:
                break
            _assign_block(res, grid, block, "Mnuc")
            available_blocks.remove(block)
            placed += 1
        meta["nrdr_mnuc_blocks"] = placed

    # ESIR: remaining Mir blocks (8 in R4 per goals.md)
    if res.is_esir:
        mir_needed = 8
        placed = 0
        for block in list(available_blocks):
            if placed >= mir_needed:
                break
            _assign_block(res, grid, block, "Mir")
            available_blocks.remove(block)
            placed += 1
        meta["esir_mir_blocks"] = placed

    # ESNR: 6 blocks neuro (max 1 on Smr)
    if res.is_esnr:
        neuro_needed = 6
        placed_zai = 0
        placed_smr = 0
        for block in list(available_blocks):
            if placed_zai + placed_smr >= neuro_needed:
                break
            if placed_smr < 1:
                _assign_block(res, grid, block, "Smr")
                placed_smr += 1
            else:
                _assign_block(res, grid, block, "Zai")
                placed_zai += 1
            available_blocks.remove(block)
        meta["esnr_neuro_blocks"] = placed_zai + placed_smr

    # FSE blocks
    if res.fse_prefs and res.fse_prefs.specialties:
        fse_name = res.fse_prefs.specialties[0] if res.fse_prefs.specialties else ""
        # Breast FSE requires 6 months
        if "breast" in fse_name.lower():
            fse_blocks = 6
        else:
            fse_blocks = 2  # typical FSE

        placed = 0
        # First half or second half of year depending on cohort
        # (goals.md: half get first half, half get second half)
        for block in list(available_blocks):
            if placed >= fse_blocks:
                break
            _assign_block(res, grid, block, f"FSE-{fse_name[:3]}")
            available_blocks.remove(block)
            placed += 1
        meta["fse_blocks"] = placed

    meta["available_after_fixed"] = list(available_blocks)


def _fill_grad_requirements(res: Resident, grid: ScheduleGrid, meta: dict) -> None:
    """Fill graduation requirement deficiencies."""
    available = meta.get("available_after_fixed", [])
    if not available:
        return

    filled = {}

    # Breast-deficient → Pcbi
    if any("Pcbi" in s or "bi" in s.lower() for s in res.deficient_sections):
        for block in list(available):
            if not _has_hospital_conflict(res.schedule, block, "Pcbi"):
                _assign_block(res, grid, block, "Pcbi")
                available.remove(block)
                filled[block] = "Pcbi"
                break

    # NucMed-deficient → Mnuc (or partial credit rotations)
    if any("Mnuc" in s or "nuc" in s.lower() or "Vnuc" in s for s in res.deficient_sections):
        for block in list(available):
            if not _has_hospital_conflict(res.schedule, block, "Mnuc"):
                _assign_block(res, grid, block, "Mnuc")
                available.remove(block)
                filled[block] = "Mnuc"
                break

    # Fill from recommended_blocks
    for rotation, count in sorted(res.recommended_blocks.items(), key=lambda x: -x[1]):
        blocks_needed = max(1, round(count))
        placed = 0
        for block in list(available):
            if placed >= blocks_needed:
                break
            if not _has_hospital_conflict(res.schedule, block, rotation):
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
) -> None:
    """Fill remaining empty blocks with Mx, Peds, MSK, etc."""
    available = meta.get("available_after_grad", [])
    if not available:
        return

    filled = {}

    # Mx for all R4s except T32 or dual-pathway
    if not res.is_t32 and not res.dual_pathway:
        for block in list(available):
            _assign_block(res, grid, block, "Mx")
            available.remove(block)
            filled[block] = "Mx"
            break  # 1 Mx block typically

    # Peds if only 1 block completed
    peds_weeks = res.history.get("Peds", 0)
    if peds_weeks < 8:  # less than 2 blocks
        for block in list(available):
            if not _has_hospital_conflict(res.schedule, block, "Peds"):
                _assign_block(res, grid, block, "Peds")
                available.remove(block)
                filled[block] = "Peds"
                break

    # Fill remaining with staffing-need rotations
    fill_rotations = ["Mai", "Mch", "Mus", "Mucic", "Mb", "Ser"]
    rot_idx = 0
    for block in list(available):
        if rot_idx >= len(fill_rotations):
            rot_idx = 0
        code = fill_rotations[rot_idx]
        if not _has_hospital_conflict(res.schedule, block, code):
            _assign_block(res, grid, block, code)
            available.remove(block)
            filled[block] = code
        rot_idx += 1

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
