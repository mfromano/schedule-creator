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
        breast_codes = {"Pcbi", "Mb", "Sbi", "Vb"}
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
        nm_codes = {"Mnuc", "Vnuc", "Snct", "Mnct"}
        nm_total = sum(res.history.get(c, 0) + current_weeks.get(c, 0) for c in nm_codes)

        if res.is_nrdr:
            # NRDR: 48 weeks, NO partial credit
            if nm_total < 48:
                deficits.append(GradDeficit(
                    resident_name=res.name,
                    requirement="Nuclear Medicine (NRDR - 48 weeks)",
                    total_weeks=nm_total,
                    required_weeks=48,
                    deficit=48 - nm_total,
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
            neuro_codes = {"Zai", "Smr"}
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
