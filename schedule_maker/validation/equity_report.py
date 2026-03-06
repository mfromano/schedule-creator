"""Anonymized equity report — class-level statistics for resident distribution."""

from __future__ import annotations

import statistics
from collections import defaultdict

from schedule_maker.models.resident import Resident, Pathway
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.rotation import (
    ROTATION_SECTION, Section, get_hospital_system, HospitalSystem, fse_to_base_code,
)
from schedule_maker.models.constraints import StaffingConstraint
from schedule_maker.validation.staffing import check_staffing, staffing_summary, ROTATION_MINIMUMS
from schedule_maker.validation.graduation import check_graduation
from schedule_maker.validation.hospital_conflict import check_hospital_conflicts
from schedule_maker.phases.r4_builder import HOSPITAL_CONFLICT_EXEMPT


def _safe_stdev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    return statistics.stdev(vals)


def _fmt(val: float, decimals: int = 1) -> str:
    return f"{val:.{decimals}f}"


def generate_equity_report(
    residents: list[Resident],
    grid: ScheduleGrid,
    staffing_constraints: list[StaffingConstraint] | None = None,
    num_weeks: int = 52,
) -> str:
    """Generate an anonymized, class-level equity report."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("ANONYMIZED EQUITY REPORT")
    lines.append("=" * 70)

    by_year: dict[int, list[Resident]] = defaultdict(list)
    for r in residents:
        by_year[r.r_year].append(r)

    # ── 1. Overview ───────────────────────────────────────────
    lines.append("\n## 1. OVERVIEW")
    for yr in sorted(by_year):
        group = by_year[yr]
        pathways = []
        for p in (Pathway.ESIR, Pathway.ESNR, Pathway.T32, Pathway.NRDR):
            count = sum(1 for r in group if p in r.pathway)
            if count:
                pathways.append(f"{p.name}={count}")
        pw_str = f" ({', '.join(pathways)})" if pathways else ""

        # Coverage %
        filled = 0
        total = len(group) * num_weeks
        for r in group:
            for w in range(1, num_weeks + 1):
                if r.schedule.get(w) or grid.get(r.name, w):
                    filled += 1
        pct = (filled / total * 100) if total else 0
        lines.append(f"  R{yr}: {len(group)} residents{pw_str}, coverage {_fmt(pct)}%")

    # ── 2. Night Float Distribution ───────────────────────────
    lines.append("\n## 2. NIGHT FLOAT DISTRIBUTION")
    nf_codes = {"Mnf", "Snf2", "Snf"}
    for yr in sorted(by_year):
        group = by_year[yr]
        nf_per_resident: list[int] = []
        mnf_counts: list[int] = []
        snf2_counts: list[int] = []
        spacings: list[int] = []

        for r in group:
            nf_weeks_list: list[int] = []
            mnf = 0
            snf2 = 0
            for w in range(1, num_weeks + 1):
                code = grid.nf_assignments.get((r.name, w), "")
                if not code:
                    code_sched = r.schedule.get(w, "")
                    if code_sched in nf_codes:
                        code = code_sched
                if code in nf_codes:
                    nf_weeks_list.append(w)
                    if code == "Mnf":
                        mnf += 1
                    elif code == "Snf2":
                        snf2 += 1

            nf_per_resident.append(len(nf_weeks_list))
            mnf_counts.append(mnf)
            snf2_counts.append(snf2)

            # Inter-NF spacing
            for i in range(1, len(nf_weeks_list)):
                spacings.append(nf_weeks_list[i] - nf_weeks_list[i - 1])

        if not nf_per_resident:
            continue

        lines.append(f"  R{yr} ({len(group)} residents):")
        lines.append(
            f"    Total NF weeks: {sum(nf_per_resident)}, "
            f"mean={_fmt(statistics.mean(nf_per_resident))}, "
            f"median={_fmt(statistics.median(nf_per_resident))}, "
            f"min={min(nf_per_resident)}, max={max(nf_per_resident)}, "
            f"stdev={_fmt(_safe_stdev([float(x) for x in nf_per_resident]))}"
        )
        lines.append(
            f"    Mnf: mean={_fmt(statistics.mean(mnf_counts))}, "
            f"Snf2: mean={_fmt(statistics.mean(snf2_counts))}"
        )
        if spacings:
            lines.append(
                f"    Inter-NF spacing: mean={_fmt(statistics.mean(spacings))} wks, "
                f"min={min(spacings)}, max={max(spacings)}"
            )

        # No-call compliance
        nocall_total = 0
        nocall_violated = 0
        for r in group:
            if not r.no_call.raw_dates:
                continue
            for w in range(1, num_weeks + 1):
                code = grid.nf_assignments.get((r.name, w), "")
                if not code:
                    code = r.schedule.get(w, "")
                if code in nf_codes:
                    nocall_total += 1
                    # Simple check: raw_dates is the pool, no week-level date resolution
                    # so we skip detailed compliance here
        if nocall_total:
            lines.append(f"    NF assignments with no-call dates available: {nocall_total}")

    # ── 3. R2 Track Preferences ───────────────────────────────
    lines.append("\n## 3. R2 TRACK PREFERENCE FULFILLMENT")
    r2s = by_year.get(2, [])
    r2_with_prefs = [r for r in r2s if r.track_prefs and r.track_prefs.rankings and r.track_number is not None]
    if r2_with_prefs:
        ranks: list[int] = []
        for r in r2_with_prefs:
            rank = r.track_prefs.rankings.get(r.track_number)
            if rank is not None:
                ranks.append(rank)
        if ranks:
            rank_dist: dict[int, int] = defaultdict(int)
            for rk in ranks:
                rank_dist[rk] += 1
            within3 = sum(1 for rk in ranks if rk <= 3)
            lines.append(f"  {len(ranks)} R2s with track preferences:")
            lines.append(f"    Mean rank: {_fmt(statistics.mean(ranks))}")
            lines.append(f"    Within top 3: {within3}/{len(ranks)} ({_fmt(within3/len(ranks)*100)}%)")
            dist_parts = [f"#{k}={v}" for k, v in sorted(rank_dist.items())]
            lines.append(f"    Distribution: {', '.join(dist_parts)}")
        else:
            lines.append("  Track preferences recorded but no rank data matched.")
    else:
        lines.append("  No R2 track preference data available.")

    # ── 4. Staffing Balance ───────────────────────────────────
    lines.append("\n## 4. STAFFING BALANCE")
    violations = check_staffing(grid, num_weeks, constraints=staffing_constraints)
    under = [v for v in violations if v.is_under]
    over = [v for v in violations if not v.is_under]
    lines.append(f"  Under-minimum violations: {len(under)}")
    lines.append(f"  Over-maximum violations: {len(over)}")

    # Per rotation group: avg/min/max residents/week
    min_entries: list[tuple[str, set[str], int]]
    if staffing_constraints:
        min_entries = [(sc.label, sc.rotation_codes, sc.min_count) for sc in staffing_constraints]
    else:
        min_entries = [(label, codes, mn) for label, (codes, mn) in ROTATION_MINIMUMS.items()]

    lines.append("  Per-rotation staffing (residents/week):")
    for label, codes, min_req in min_entries:
        weekly_counts: list[int] = []
        for w in range(1, num_weeks + 1):
            assignments = grid.get_week_assignments(w)
            count = sum(1 for c in assignments.values()
                        if c in codes or fse_to_base_code(c) in codes)
            weekly_counts.append(count)
        if weekly_counts:
            lines.append(
                f"    {label}: avg={_fmt(statistics.mean(weekly_counts))}, "
                f"min={min(weekly_counts)}, max={max(weekly_counts)}, "
                f"target_min={min_req}"
            )

    # Per hospital system
    summary = staffing_summary(grid, num_weeks)
    lines.append("  Per-system staffing (residents/week):")
    for label, stats in summary.items():
        lines.append(
            f"    {label}: avg={_fmt(stats['avg'])}, "
            f"min={stats['min']}, max={stats['max']}"
        )

    # ── 5. Graduation Progress ────────────────────────────────
    lines.append("\n## 5. GRADUATION PROGRESS")
    deficits = check_graduation(residents, check_r4_only=False)
    deficits_by_year: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    # Build requirement progress per resident
    for yr in sorted(by_year):
        group = by_year[yr]
        yr_deficits = [d for d in deficits
                       if any(r.name == d.resident_name and r.r_year == yr for r in group)]
        deficit_count = len(set(d.resident_name for d in yr_deficits))
        lines.append(f"  R{yr}: {deficit_count}/{len(group)} residents with graduation deficits")
        # Group by requirement type
        req_groups: dict[str, list] = defaultdict(list)
        for d in yr_deficits:
            req_groups[d.requirement].append(d)
        for req, ds in sorted(req_groups.items()):
            progress_pcts = [d.total_weeks / d.required_weeks * 100 for d in ds]
            lines.append(
                f"    {req}: {len(ds)} deficits, "
                f"mean progress {_fmt(statistics.mean(progress_pcts))}%"
            )

    # ── 6. Hospital System Compliance ─────────────────────────
    lines.append("\n## 6. HOSPITAL SYSTEM COMPLIANCE")
    conflicts = check_hospital_conflicts(residents, exempt_names=HOSPITAL_CONFLICT_EXEMPT)
    lines.append(f"  Total conflicts: {len(conflicts)}")
    if conflicts:
        # Count by class
        for yr in sorted(by_year):
            names = {r.name for r in by_year[yr]}
            yr_conflicts = [c for c in conflicts if c.resident_name in names]
            if yr_conflicts:
                lines.append(f"    R{yr}: {len(yr_conflicts)} conflicts")

    # ── 7. Rotation Diversity ─────────────────────────────────
    lines.append("\n## 7. ROTATION DIVERSITY")
    for yr in sorted(by_year):
        group = by_year[yr]
        distinct_rots: list[int] = []
        distinct_secs: list[int] = []
        longest_runs: list[int] = []

        for r in group:
            rotations_seen: set[str] = set()
            sections_seen: set[Section] = set()
            best_run = 0
            cur_code = ""
            cur_run = 0

            for w in range(1, num_weeks + 1):
                code = grid.get(r.name, w) or r.schedule.get(w, "")
                if not code:
                    if cur_run > best_run:
                        best_run = cur_run
                    cur_code = ""
                    cur_run = 0
                    continue

                rotations_seen.add(code)
                base = fse_to_base_code(code)
                sec = ROTATION_SECTION.get(base)
                if sec:
                    sections_seen.add(sec)

                if code == cur_code:
                    cur_run += 1
                else:
                    if cur_run > best_run:
                        best_run = cur_run
                    cur_code = code
                    cur_run = 1

            if cur_run > best_run:
                best_run = cur_run

            distinct_rots.append(len(rotations_seen))
            distinct_secs.append(len(sections_seen))
            longest_runs.append(best_run)

        if not group:
            continue
        lines.append(f"  R{yr} ({len(group)} residents):")
        lines.append(
            f"    Distinct rotations: mean={_fmt(statistics.mean(distinct_rots))}, "
            f"min={min(distinct_rots)}, max={max(distinct_rots)}"
        )
        lines.append(
            f"    Distinct sections: mean={_fmt(statistics.mean(distinct_secs))}, "
            f"min={min(distinct_secs)}, max={max(distinct_secs)}"
        )
        lines.append(
            f"    Longest same-rotation run (wks): mean={_fmt(statistics.mean(longest_runs))}, "
            f"min={min(longest_runs)}, max={max(longest_runs)}"
        )

    # ── 8. Section Exposure Balance ───────────────────────────
    lines.append("\n## 8. SECTION EXPOSURE BALANCE")
    # Major sections to report on
    section_groups: dict[str, set[str]] = {
        "AI": {"Mai", "Zai", "Sai"},
        "Breast": {"Pcbi", "Sbi"},
        "NucMed": {"Mnuc", "Mnct", "Snct"},
        "Neuro": {"Mucic", "Smr"},
        "MSK": {"Mb", "Vb", "Ser"},
        "Chest": {"Mch", "Mch2", "Sch"},
        "Peds": {"Peds"},
        "IR": {"Mir", "Zir", "Sir", "Vir"},
        "US": {"Mus", "Sus"},
    }

    for yr in sorted(by_year):
        group = by_year[yr]
        if not group:
            continue
        lines.append(f"  R{yr}:")
        for sec_name, sec_codes in section_groups.items():
            weeks_per_resident: list[float] = []
            for r in group:
                total = 0.0
                for w in range(1, num_weeks + 1):
                    code = grid.get(r.name, w) or r.schedule.get(w, "")
                    base = fse_to_base_code(code)
                    if base in sec_codes:
                        total += 1
                weeks_per_resident.append(total)

            if not weeks_per_resident or max(weeks_per_resident) == 0:
                continue
            lines.append(
                f"    {sec_name}: mean={_fmt(statistics.mean(weeks_per_resident))} wks, "
                f"min={int(min(weeks_per_resident))}, max={int(max(weeks_per_resident))}, "
                f"stdev={_fmt(_safe_stdev(weeks_per_resident))}"
            )

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
