"""Generate validation summary reports."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.validation.staffing import check_staffing, staffing_summary, StaffingViolation
from schedule_maker.validation.graduation import check_graduation, GradDeficit
from schedule_maker.validation.hospital_conflict import check_hospital_conflicts, HospitalConflict


def generate_report(
    residents: list[Resident],
    grid: ScheduleGrid,
    num_weeks: int = 52,
) -> str:
    """Generate a comprehensive validation report.

    Checks:
    1. Staffing levels per week
    2. Graduation requirements for R4s (and T32 juniors)
    3. Hospital system conflicts
    4. NF assignment counts and spacing
    """
    lines = []
    lines.append("=" * 70)
    lines.append("SCHEDULE VALIDATION REPORT")
    lines.append("=" * 70)

    # 1. Staffing
    staffing_violations = check_staffing(grid, num_weeks)
    under_violations = [v for v in staffing_violations if v.is_under]
    lines.append(f"\n## STAFFING ({len(under_violations)} under-minimum violations)")
    if under_violations:
        for v in under_violations[:20]:
            lines.append(
                f"  Block {v.block}, Week {v.week}: {v.label} — "
                f"{v.count} (min: {v.min_required})"
            )
        if len(under_violations) > 20:
            lines.append(f"  ... and {len(under_violations) - 20} more")
    else:
        lines.append("  All rotations meet minimum staffing levels.")

    # Staffing summary by site
    summary = staffing_summary(grid, num_weeks)
    lines.append("\n  Site Staffing Summary (residents/week):")
    for label, stats in summary.items():
        lines.append(
            f"    {label}: avg={stats['avg']:.1f}, "
            f"min={stats['min']} (week {stats['min_week']}), max={stats['max']}"
        )

    # 2. Graduation
    grad_deficits = check_graduation(residents, check_r4_only=False)
    r4_deficits = [d for d in grad_deficits
                   if any(r.name == d.resident_name and r.r_year == 4 for r in residents)]
    other_deficits = [d for d in grad_deficits if d not in r4_deficits]

    lines.append(f"\n## GRADUATION REQUIREMENTS — R4 ({len(r4_deficits)} deficits)")
    if r4_deficits:
        for d in r4_deficits:
            lines.append(
                f"  {d.resident_name}: {d.requirement} — "
                f"{d.total_weeks:.1f}/{d.required_weeks:.0f} weeks "
                f"(deficit: {d.deficit:.1f})"
            )
    else:
        lines.append("  All R4s meet graduation requirements.")

    lines.append(f"\n## GRADUATION REQUIREMENTS — Others ({len(other_deficits)} deficits)")
    if other_deficits:
        for d in other_deficits[:10]:
            lines.append(
                f"  {d.resident_name}: {d.requirement} — "
                f"{d.total_weeks:.1f}/{d.required_weeks:.0f} weeks "
                f"(deficit: {d.deficit:.1f})"
            )
    else:
        lines.append("  No deficits found for non-R4 residents.")

    # 3. Hospital conflicts
    conflicts = check_hospital_conflicts(residents)
    lines.append(f"\n## HOSPITAL SYSTEM CONFLICTS ({len(conflicts)} conflicts)")
    if conflicts:
        for c in conflicts:
            lines.append(
                f"  {c.resident_name}: Block {c.block} — "
                f"systems: {c.systems}, rotations: {c.rotations}"
            )
    else:
        lines.append("  No hospital system conflicts.")

    # 4. NF summary
    lines.append("\n## NIGHT FLOAT SUMMARY")
    for r_year in [2, 3, 4]:
        year_residents = [r for r in residents if r.r_year == r_year]
        nf_counts = []
        for res in year_residents:
            nf_weeks = sum(1 for w, code in grid.nf_assignments.items()
                           if w[0] == res.name)
            nf_counts.append((res.name, nf_weeks))
        if nf_counts:
            avg = sum(c for _, c in nf_counts) / len(nf_counts) if nf_counts else 0
            lines.append(f"  R{r_year}: avg {avg:.1f} NF weeks/resident")
            for name, count in sorted(nf_counts, key=lambda x: -x[1])[:5]:
                lines.append(f"    {name}: {count} weeks")

    # 5. Coverage summary
    lines.append("\n## SCHEDULE COVERAGE")
    for r_year in [1, 2, 3, 4]:
        year_residents = [r for r in residents if r.r_year == r_year]
        empty_counts = []
        for res in year_residents:
            empty = sum(1 for w in range(1, num_weeks + 1) if not res.schedule.get(w))
            empty_counts.append(empty)
        if empty_counts:
            avg_empty = sum(empty_counts) / len(empty_counts)
            lines.append(f"  R{r_year}: avg {avg_empty:.1f} unassigned weeks/resident")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
