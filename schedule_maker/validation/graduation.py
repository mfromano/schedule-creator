"""Graduation requirement verification."""

from __future__ import annotations

from dataclasses import dataclass, field

from schedule_maker.models.resident import Resident, Pathway
from schedule_maker.models.constraints import GraduationRequirements, STANDARD_GRAD_REQS
from schedule_maker.models.rotation import NM_PARTIAL_CREDIT_ROTATIONS, NM_PARTIAL_RATIO


@dataclass
class GradDeficit:
    resident_name: str
    requirement: str
    total_weeks: float
    required_weeks: float
    deficit: float


def check_graduation(
    residents: list[Resident],
    check_r4_only: bool = False,
) -> list[GradDeficit]:
    """Check graduation requirements for all (or R4 only) residents.

    Combines historical rotation weeks + current year schedule.

    Args:
        residents: residents to check
        check_r4_only: if True, only check graduating R4s

    Returns:
        List of graduation deficits
    """
    deficits = []

    for res in residents:
        if check_r4_only and res.r_year != 4:
            continue

        # Count current year rotation weeks from schedule
        current_weeks: dict[str, float] = {}
        for week, code in res.schedule.items():
            if code:
                current_weeks[code] = current_weeks.get(code, 0) + 1

        # Check breast imaging (12 weeks across residency)
        breast_codes = {"Pcbi", "Sbi"}
        breast_total = sum(res.history.get(c, 0) + current_weeks.get(c, 0)
                          for c in breast_codes)
        if breast_total < 12:
            deficits.append(GradDeficit(
                resident_name=res.name,
                requirement="Breast Imaging (12 weeks + 300 cases)",
                total_weeks=breast_total,
                required_weeks=12,
                deficit=12 - breast_total,
            ))

        # Check nuclear medicine
        nm_codes = {"Mnuc", "Vnuc"}
        nm_total = sum(res.history.get(c, 0) + current_weeks.get(c, 0) for c in nm_codes)

        if res.is_nrdr:
            # NRDR: 48 weeks, NO partial credit from clinical rotations,
            # but research months count toward requirement
            res_weeks = res.history.get("Res", 0) + current_weeks.get("Res", 0)
            nm_with_res = nm_total + res_weeks
            if nm_with_res < 48:
                deficits.append(GradDeficit(
                    resident_name=res.name,
                    requirement="Nuclear Medicine (NRDR - 48 weeks)",
                    total_weeks=nm_with_res,
                    required_weeks=48,
                    deficit=48 - nm_with_res,
                ))
        else:
            # Non-NRDR: 16 weeks, with 4:1 partial credit
            partial = sum(
                (res.history.get(c, 0) + current_weeks.get(c, 0)) * NM_PARTIAL_RATIO
                for c in NM_PARTIAL_CREDIT_ROTATIONS
            )
            nm_with_partial = nm_total + partial
            if nm_with_partial < 16:
                deficits.append(GradDeficit(
                    resident_name=res.name,
                    requirement="Nuclear Medicine (16 weeks)",
                    total_weeks=nm_with_partial,
                    required_weeks=16,
                    deficit=16 - nm_with_partial,
                ))

        # ESIR: 12 weeks IR
        if res.is_esir:
            ir_codes = {"Mir", "Zir", "Sir", "Vir"}
            ir_total = sum(res.history.get(c, 0) + current_weeks.get(c, 0) for c in ir_codes)
            if ir_total < 12:
                deficits.append(GradDeficit(
                    resident_name=res.name,
                    requirement="ESIR (12 weeks IR)",
                    total_weeks=ir_total,
                    required_weeks=12,
                    deficit=12 - ir_total,
                ))

        # ESNR: 6 blocks (24 weeks) neuro in R4, max 1 on Smr
        if res.is_esnr:
            neuro_codes = {"Mucic", "Smr"}
            neuro_total = sum(res.history.get(c, 0) + current_weeks.get(c, 0)
                             for c in neuro_codes)
            if neuro_total < 24:
                deficits.append(GradDeficit(
                    resident_name=res.name,
                    requirement="ESNR (24 weeks neuro, max 1 block Smr)",
                    total_weeks=neuro_total,
                    required_weeks=24,
                    deficit=24 - neuro_total,
                ))

    return deficits


def compute_r34_recs(residents: list[Resident]) -> None:
    """Compute recommended_blocks and deficient_sections for R3/R4 residents.

    Replicates the Excel R3-4 Recs tab formulas using graduation deficit logic.
    Only populates fields that are empty (doesn't overwrite values already set).
    """
    import math

    for res in residents:
        if res.r_year not in (3, 4):
            continue
        # Skip if already populated (e.g. from Excel read)
        if res.recommended_blocks:
            continue

        deficient: list[str] = []
        rec: dict[str, float] = {}

        # ── Breast deficit ──
        breast_codes = {"Pcbi", "Sbi"}
        breast_total = sum(res.history.get(c, 0) for c in breast_codes)
        breast_deficit = max(0, 12 - breast_total)
        if breast_deficit > 0:
            breast_blocks = math.ceil(breast_deficit / 4)
            rec["Pcbi"] = breast_blocks
            deficient.append("Pcbi")

        # ── NucMed deficit ──
        nm_codes = {"Mnuc", "Vnuc"}
        nm_total = sum(res.history.get(c, 0) for c in nm_codes)

        if res.is_nrdr:
            # NRDR: 48 weeks, research counts, no partial credit
            res_weeks = res.history.get("Res", 0)
            nm_with_res = nm_total + res_weeks
            nm_deficit = max(0, 48 - nm_with_res)
            if nm_deficit > 0:
                nm_blocks = math.ceil(nm_deficit / 4)
                # NRDR R3/R4 get 6 blocks Mnuc as fixed commitment
                rec["Mnuc"] = max(nm_blocks, 6)
                deficient.append("Mnuc")
        else:
            # Non-NRDR: 16 weeks, with 4:1 partial credit
            partial = sum(
                res.history.get(c, 0) * NM_PARTIAL_RATIO
                for c in NM_PARTIAL_CREDIT_ROTATIONS
            )
            nm_with_partial = nm_total + partial
            nm_deficit = max(0, 16 - nm_with_partial)
            if nm_deficit > 0:
                nm_blocks = math.ceil(nm_deficit / 4)
                rec["Mnuc"] = nm_blocks
                deficient.append("Mnuc")

        # ── ESIR deficit ──
        if res.is_esir:
            ir_codes = {"Mir", "Zir", "Sir", "Vir"}
            ir_total = sum(res.history.get(c, 0) for c in ir_codes)
            ir_deficit = max(0, 12 - ir_total)
            if ir_deficit > 0:
                if res.r_year == 4:
                    # R4 ESIR: 8 blocks Mir (fixed commitment)
                    rec["Mir"] = 8
                else:
                    # R3 ESIR: ~2 blocks Zir/Mir
                    ir_blocks = math.ceil(ir_deficit / 4)
                    rec["Zir"] = min(ir_blocks, 1)
                    if ir_blocks > 1:
                        rec["Mir"] = ir_blocks - 1
                deficient.append("Mir")

        # ── ESNR deficit ──
        if res.is_esnr:
            neuro_codes = {"Mucic", "Smr"}
            neuro_total = sum(res.history.get(c, 0) for c in neuro_codes)
            neuro_deficit = max(0, 24 - neuro_total)
            if neuro_deficit > 0 and res.r_year == 4:
                # 6 blocks neuro, max 1 on Smr
                rec["Mucic"] = 5
                rec["Smr"] = 1
                deficient.append("Mucic")

        # ── Mx for R4 (unless T32 or dual-pathway) ──
        if res.r_year == 4 and not res.is_t32 and not res.dual_pathway:
            rec.setdefault("Mx", 1)

        res.recommended_blocks = rec
        if not res.deficient_sections:
            res.deficient_sections = deficient
