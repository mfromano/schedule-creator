"""Per-week staffing validation."""

from __future__ import annotations

from dataclasses import dataclass

from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem


@dataclass
class StaffingViolation:
    week: int
    block: int
    label: str
    count: int
    min_required: int
    max_allowed: int
    is_under: bool


# Per-rotation minimum requirements derived from Base Schedule rows 101-151.
# Format: label → (set of rotation codes, minimum required)
# Maximums are not enforced (they depend on total class size and are informational).
ROTATION_MINIMUMS: dict[str, tuple[set[str], int]] = {
    "Moffitt AI": ({"Mai"}, 3),
    "Moffitt US": ({"Mus"}, 2),
    "Moffitt Cardiothoracic": ({"Mch", "Mch2"}, 2),
    "Peds": ({"Peds"}, 1),
    "Moffitt Bone": ({"Mb"}, 1),
    "Moffitt Nucs": ({"Mnuc", "Mnct"}, 2),
    "PCMB Breast": ({"Pcbi"}, 1),
    "ZSFG Total": ({"Ser", "Smr", "Sbi", "Sir", "Sus", "Sai", "Snct",
                     "Sch", "Sch2", "Sx", "SSamplerCh2"}, 8),
    "VA MSK/Nucs": ({"Vnuc", "Vb", "Vn"}, 1),
    "IR Total": ({"Mir", "Zir", "Sir", "Vir"}, 1),
    "Mucic": ({"Mucic"}, 1),
}


def check_staffing(
    grid: ScheduleGrid,
    num_weeks: int = 52,
    bounds: dict | None = None,
) -> list[StaffingViolation]:
    """Check staffing levels using per-rotation minimums.

    Only flags UNDER-staffing (below minimum). Over-staffing is reported
    in the summary but not treated as a violation since maximums vary.
    """
    violations = []

    for week in range(1, num_weeks + 1):
        week_assignments = grid.get_week_assignments(week)
        block = grid.week_to_block(week)

        for label, (codes, min_req) in ROTATION_MINIMUMS.items():
            count = sum(1 for code in week_assignments.values() if code in codes)
            if count < min_req:
                violations.append(StaffingViolation(
                    week=week, block=block, label=label,
                    count=count, min_required=min_req, max_allowed=99,
                    is_under=True,
                ))

    return violations


def staffing_summary(
    grid: ScheduleGrid,
    num_weeks: int = 52,
) -> dict[str, dict]:
    """Generate per-site staffing summary (avg/min/max across weeks).

    Returns {site_label: {"avg": float, "min": int, "max": int, "min_week": int}}.
    """
    site_groups = {
        "UCSF (Moffitt/Parnassus)": HospitalSystem.UCSF,
        "ZSFG": HospitalSystem.ZSFG,
        "VA": HospitalSystem.VA,
    }

    result = {}
    for site_label, system in site_groups.items():
        weekly_counts = []
        for week in range(1, num_weeks + 1):
            assignments = grid.get_week_assignments(week)
            count = sum(1 for code in assignments.values()
                        if get_hospital_system(code) == system)
            weekly_counts.append((week, count))

        counts = [c for _, c in weekly_counts]
        if counts:
            min_val = min(counts)
            min_week = [w for w, c in weekly_counts if c == min_val][0]
            result[site_label] = {
                "avg": sum(counts) / len(counts),
                "min": min_val,
                "max": max(counts),
                "min_week": min_week,
            }

    return result
