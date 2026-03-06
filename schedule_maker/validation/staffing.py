"""Per-week staffing validation."""

from __future__ import annotations

from dataclasses import dataclass

from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import get_hospital_system, HospitalSystem, fse_to_base_code
from schedule_maker.models.constraints import StaffingConstraint


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
# Updated for 2026-2027 spreadsheet layout.
ROTATION_MINIMUMS: dict[str, tuple[set[str], int]] = {
    # ── Group-level minimums (all R-years) ──
    "Moffitt AI": ({"Mai", "Zai"}, 3),
    "Moffitt US": ({"Mus"}, 2),
    "Moffitt Cardiothoracic": ({"Mch", "Mch2", "Mc"}, 2),
    "Peds": ({"Peds"}, 1),
    "Moffitt Neuro": ({"Mucic", "Mnct"}, 3),
    "Moffitt Bone": ({"Mb"}, 1),
    "Moffitt Nucs": ({"Mnuc"}, 2),
    "PCMB Breast": ({"Pcbi"}, 1),
    "ZSFG Total": ({"Ser", "Smr", "Sbi", "Sir", "Sus", "Sai", "Snct",
                     "Sch", "Sch2", "Sx", "SSamplerCh2"}, 8),
    "VA MSK/Nucs": ({"Vb"}, 1),
    "Mucic": ({"Mucic"}, 1),
    "Zir": ({"Zir"}, 1),
}

# Per-rotation maximum constraints (exclusivity rules).
ROTATION_MAXIMUMS: dict[str, tuple[set[str], int]] = {
    "Sx": ({"Sx"}, 1),
    "Snf": ({"Snf"}, 1),
    "Mnf": ({"Mnf"}, 1),
    "Snf2": ({"Snf2"}, 1),
    "PCMB Breast": ({"Pcbi"}, 3),
    "NucMed Total": ({"Mnuc"}, 5),
    "VA MSK": ({"Vb"}, 1),
    "VA IR": ({"Vir"}, 1),
    "Zir": ({"Zir"}, 1),
    "Ser": ({"Ser"}, 2),
    "Mai": ({"Mai"}, 5),
    "Mucic": ({"Mucic"}, 6),
}


def check_staffing(
    grid: ScheduleGrid,
    num_weeks: int = 52,
    constraints: list[StaffingConstraint] | None = None,
) -> list[StaffingViolation]:
    """Check staffing levels using per-rotation minimums and maximums.

    If dynamic constraints are provided, uses those for minimum checks.
    Always uses ROTATION_MAXIMUMS for maximum checks.
    Falls back to ROTATION_MINIMUMS when no dynamic constraints given.
    """
    violations = []

    # Build minimums source
    if constraints:
        min_entries = [(sc.label, sc.rotation_codes, sc.min_count) for sc in constraints]
    else:
        min_entries = [(label, codes, min_req) for label, (codes, min_req) in ROTATION_MINIMUMS.items()]

    for week in range(1, num_weeks + 1):
        week_assignments = grid.get_week_assignments(week)
        block = grid.week_to_block(week)

        for label, codes, min_req in min_entries:
            count = sum(1 for code in week_assignments.values()
                        if code in codes or fse_to_base_code(code) in codes)
            if count < min_req:
                violations.append(StaffingViolation(
                    week=week, block=block, label=label,
                    count=count, min_required=min_req, max_allowed=99,
                    is_under=True,
                ))

        for label, (codes, max_allowed) in ROTATION_MAXIMUMS.items():
            count = sum(1 for code in week_assignments.values()
                        if code in codes or fse_to_base_code(code) in codes)
            if count > max_allowed:
                violations.append(StaffingViolation(
                    week=week, block=block, label=label,
                    count=count, min_required=0, max_allowed=max_allowed,
                    is_under=False,
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
