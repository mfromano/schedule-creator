"""Hospital system conflict detection."""

from __future__ import annotations

from dataclasses import dataclass

from schedule_maker.models.resident import Resident
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem


@dataclass
class HospitalConflict:
    resident_name: str
    block: int
    systems: set[str]  # names of conflicting hospital systems
    rotations: list[str]  # the rotation codes causing the conflict


def check_hospital_conflicts(
    residents: list[Resident],
    num_blocks: int = 13,
) -> list[HospitalConflict]:
    """Check that no resident has two hospital systems in the same block.

    Per goals.md: No resident can be assigned to two different hospital systems
    (e.g., UCSF, SFGH, VA) in the same block as it creates problems for payroll.
    """
    conflicts = []

    for res in residents:
        for block in range(1, num_blocks + 1):
            start_week = (block - 1) * 4 + 1

            # Check biweeks separately: A = weeks 1-2, B = weeks 3-4
            # Hospital conflicts within a biweek are the real issue
            # (different rotations in the same 2-week period at different sites)
            for biweek_start in (start_week, start_week + 2):
                systems_seen: dict[HospitalSystem, list[str]] = {}

                for w in range(biweek_start, biweek_start + 2):
                    code = res.schedule.get(w, "")
                    if not code:
                        continue

                    system = get_hospital_system(code)
                    if system == HospitalSystem.OTHER:
                        continue

                    if system not in systems_seen:
                        systems_seen[system] = []
                    systems_seen[system].append(code)

                # Check if multiple systems present in this biweek
                real_systems = {s: codes for s, codes in systems_seen.items()
                                if s != HospitalSystem.OTHER}
                if len(real_systems) > 1:
                    all_codes = []
                    for codes in real_systems.values():
                        all_codes.extend(codes)
                    biweek_label = "A" if biweek_start == start_week else "B"
                    conflicts.append(HospitalConflict(
                        resident_name=res.name,
                        block=block,
                        systems={s.value for s in real_systems},
                        rotations=all_codes,
                    ))

    return conflicts
