"""Generate validation summary reports."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.models.constraints import StaffingConstraint
from schedule_maker.validation.staffing import check_staffing, staffing_summary, StaffingViolation
from schedule_maker.validation.graduation import check_graduation, GradDeficit
from schedule_maker.validation.hospital_conflict import check_hospital_conflicts, HospitalConflict
from schedule_maker.phases.r4_builder import HOSPITAL_CONFLICT_EXEMPT


def generate_report(
    residents: list[Resident],
    grid: ScheduleGrid,
    num_weeks: int = 52,
    build_metadata: dict[str, dict] | None = None,
    nf_violations: list[str] | None = None,
    staffing_constraints: list[StaffingConstraint] | None = None,
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
    staffing_violations = check_staffing(grid, num_weeks, constraints=staffing_constraints)
    under_violations = [v for v in staffing_violations if v.is_under]
    over_violations = [v for v in staffing_violations if not v.is_under]
    lines.append(f"\n## STAFFING ({len(under_violations)} under-minimum, {len(over_violations)} over-maximum violations)")
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
    if over_violations:
        lines.append(f"\n  Over-maximum violations:")
        for v in over_violations[:20]:
            lines.append(
                f"  Block {v.block}, Week {v.week}: {v.label} — "
                f"{v.count} (max: {v.max_allowed})"
            )
        if len(over_violations) > 20:
            lines.append(f"  ... and {len(over_violations) - 20} more")

    # Staffing summary by site
    summary = staffing_summary(grid, num_weeks)
    lines.append("\n  Site Staffing Summary (residents/week):")
    for label, stats in summary.items():
        lines.append(
            f"    {label}: avg={stats['avg']:.1f}, "
            f"min={stats['min']} (week {stats['min_week']}), max={stats['max']}"
        )

    # Staffing warnings from build phases
    if build_metadata:
        warnings = [
            meta["staffing_warning"]
            for meta in build_metadata.values()
            if "staffing_warning" in meta
        ]
        if warnings:
            lines.append(f"\n  Staffing Warnings ({len(warnings)}):")
            for w in warnings:
                lines.append(f"    {w}")

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
    conflicts = check_hospital_conflicts(residents, exempt_names=HOSPITAL_CONFLICT_EXEMPT)
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
    if nf_violations:
        lines.append(f"\n## NO-CALL PREFERENCE VIOLATIONS ({len(nf_violations)} violations)")
        for v in nf_violations:
            lines.append(f"  {v}")
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


def generate_preference_report(
    residents: list[Resident],
    grid: ScheduleGrid,
    r2_result: object | None = None,
    r3_meta: dict[str, dict] | None = None,
    sampler_replacements: dict[str, dict[int, str]] | None = None,
) -> str:
    """Generate a report on how well the schedule matches resident preferences."""
    lines = []
    lines.append("=" * 70)
    lines.append("PREFERENCE FULFILLMENT REPORT")
    lines.append("=" * 70)

    # ── R1: Sampler Preferences ──────────────────────────────
    r1s = [r for r in residents if r.r_year == 1]
    lines.append("\n## R1 — SAMPLER PREFERENCES")
    r1_with_prefs = [r for r in r1s if r.sampler_prefs and r.sampler_prefs.rankings]
    if r1_with_prefs:
        for res in sorted(r1_with_prefs, key=lambda r: r.name):
            rankings = res.sampler_prefs.rankings
            sorted_prefs = sorted(rankings.items(), key=lambda x: x[1])
            top3 = [code for code, _ in sorted_prefs[:3]]
            bottom3 = [code for code, _ in sorted_prefs[-3:]] if len(sorted_prefs) >= 3 else []

            # Determine what was assigned (Mucic vs Mir)
            assigned_choice = None
            if sampler_replacements and res.name in sampler_replacements:
                for _w, code in sampler_replacements[res.name].items():
                    if code in ("Mucic", "Mir"):
                        assigned_choice = code
                        break

            fulfilled = []
            if assigned_choice and assigned_choice in top3:
                fulfilled.append(f"{assigned_choice} (top 3)")
            elif assigned_choice and assigned_choice in bottom3:
                fulfilled.append(f"{assigned_choice} (bottom 3!)")

            top_str = ", ".join(top3) if top3 else "none"
            btm_str = ", ".join(bottom3) if bottom3 else "none"
            choice_str = assigned_choice or "?"
            lines.append(f"  {res.name}: top3=[{top_str}] bottom3=[{btm_str}] → assigned {choice_str}")
    else:
        lines.append("  No R1 sampler preferences recorded.")

    # ── R2: Track Rankings ───────────────────────────────────
    r2s = [r for r in residents if r.r_year == 2]
    lines.append("\n## R2 — TRACK RANKINGS")
    if r2_result and hasattr(r2_result, "per_resident") and r2_result.per_resident:
        penalties = []
        for name, info in sorted(r2_result.per_resident.items()):
            res = next((r for r in r2s if r.name == name), None)
            rank = info.get("rank", "?")
            track = info.get("track", "?")
            # Show top 3 ranked tracks
            top3_str = "?"
            if res and res.track_prefs and res.track_prefs.rankings:
                inv = {v: k for k, v in res.track_prefs.rankings.items()}
                top3_tracks = [str(inv[r]) for r in sorted(inv)[:3]]
                top3_str = ", ".join(top3_tracks)
            lines.append(f"  {name}: Track {track} (rank #{rank}) — top 3 choices: [{top3_str}]")
            if isinstance(rank, int):
                penalties.append(rank)
        if penalties:
            avg_pen = sum(penalties) / len(penalties)
            within_3 = sum(1 for p in penalties if p <= 3)
            lines.append(f"  Summary: avg rank={avg_pen:.1f}, {within_3}/{len(penalties)} within top 3")
    else:
        lines.append("  No R2 track assignment data.")

    # ── R3: Zir Timing ───────────────────────────────────────
    r3s = [r for r in residents if r.r_year == 3]
    lines.append("\n## R3 — ZIR TIMING PREFERENCES")
    r3_zir = [r for r in r3s if r.zir_prefs and r.zir_prefs.preferred_blocks]
    if r3_zir:
        fulfilled_count = 0
        for res in sorted(r3_zir, key=lambda r: r.name):
            # Find actual Zir block
            actual_zir_block = None
            for w, code in res.schedule.items():
                if code == "Zir":
                    actual_zir_block = grid.week_to_block(w)
                    break
            prefs = res.zir_prefs.preferred_blocks
            match = actual_zir_block in prefs if actual_zir_block else False
            if match:
                fulfilled_count += 1
            status = "MATCH" if match else "miss"
            actual_str = str(actual_zir_block) if actual_zir_block else "none"
            lines.append(f"  {res.name}: preferred={prefs} actual=B{actual_str} [{status}]")
        lines.append(f"  Summary: {fulfilled_count}/{len(r3_zir)} matched preferred Zir block")
    else:
        lines.append("  No R3 Zir timing preferences recorded.")

    # ── R3: AIRP Session & Groupings ─────────────────────────
    lines.append("\n## R3 — AIRP SESSION PREFERENCES")
    r3_airp = [r for r in r3s if r.airp_prefs and r.airp_prefs.rankings]
    if r3_airp and r3_meta:
        fulfilled_count = 0
        for res in sorted(r3_airp, key=lambda r: r.name):
            assigned = r3_meta.get(res.name, {}).get("airp_session", "?")
            inv = {v: k for k, v in res.airp_prefs.rankings.items()}
            top_choices = [inv[r] for r in sorted(inv)[:3] if r in inv]
            rank_of_assigned = res.airp_prefs.rankings.get(assigned)
            if rank_of_assigned and rank_of_assigned <= 3:
                fulfilled_count += 1
            rank_str = f"rank #{rank_of_assigned}" if rank_of_assigned else "unranked"
            top_str = ", ".join(str(s) for s in top_choices[:3])
            lines.append(f"  {res.name}: assigned={assigned} ({rank_str}) — top 3: [{top_str}]")

            # Check groupmate requests
            if res.airp_prefs.group_requests:
                for mate in res.airp_prefs.group_requests:
                    mate_session = r3_meta.get(mate, {}).get("airp_session", "?")
                    co = "YES" if mate_session == assigned else "no"
                    lines.append(f"    groupmate {mate}: {mate_session} [{co}]")

        lines.append(f"  Summary: {fulfilled_count}/{len(r3_airp)} assigned top-3 AIRP session")
    else:
        lines.append("  No R3 AIRP preferences or metadata.")

    # ── R4: FSE Preferences ──────────────────────────────────
    r4s = [r for r in residents if r.r_year == 4]
    lines.append("\n## R4 — MINI-FELLOWSHIP (FSE) PREFERENCES")
    r4_fse = [r for r in r4s if r.fse_prefs and r.fse_prefs.specialties]
    if r4_fse:
        for res in sorted(r4_fse, key=lambda r: r.name):
            pref_spec = res.fse_prefs.specialties
            pref_org = res.fse_prefs.organization or "?"

            # Find assigned FSE blocks
            fse_blocks = []
            for w in sorted(res.schedule):
                code = res.schedule[w]
                if code and code.startswith("FSE"):
                    fse_blocks.append((grid.week_to_block(w), code))

            if fse_blocks:
                assigned_code = fse_blocks[0][1]
                block_nums = sorted(set(b for b, _ in fse_blocks))

                # Contiguity check
                is_contiguous = all(
                    block_nums[i] + 1 == block_nums[i + 1]
                    for i in range(len(block_nums) - 1)
                ) if len(block_nums) > 1 else True
                contig_str = "contiguous" if is_contiguous else "interrupted"

                org_match = ""
                if pref_org:
                    want_contig = "contig" in pref_org.lower()
                    org_match = " MATCH" if want_contig == is_contiguous else " MISMATCH"

                lines.append(
                    f"  {res.name}: pref={pref_spec} org={pref_org} → "
                    f"{assigned_code} blocks={block_nums} ({contig_str}{org_match})"
                )
            else:
                lines.append(f"  {res.name}: pref={pref_spec} → no FSE assigned")
    else:
        lines.append("  No R4 FSE preferences recorded.")

    # ── R3/R4: Longest Uninterrupted Sequential Blocks ───────
    lines.append("\n## R3/R4 — LONGEST CONSECUTIVE SAME-ROTATION RUNS")
    for r_year, label in [(3, "R3"), (4, "R4")]:
        year_residents = [r for r in residents if r.r_year == r_year]
        for res in sorted(year_residents, key=lambda r: r.name):
            # Find longest consecutive run of the same rotation
            best_code = ""
            best_len = 0
            cur_code = ""
            cur_len = 0
            for w in range(1, 53):
                code = res.schedule.get(w, "")
                if code and code == cur_code:
                    cur_len += 1
                else:
                    if cur_len > best_len and cur_code:
                        best_len = cur_len
                        best_code = cur_code
                    cur_code = code
                    cur_len = 1
            if cur_len > best_len and cur_code:
                best_len = cur_len
                best_code = cur_code

            if best_len >= 4:  # Only report runs of 4+ weeks (1+ blocks)
                blocks_equiv = best_len / 4
                lines.append(f"  {res.name}: {best_code} x{best_len}wk ({blocks_equiv:.0f} blocks)")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
