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
    r4_meta: dict[str, dict] | None = None,
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
            bottom3 = [code for code, _ in sorted_prefs[-3:]] if len(sorted_prefs) > 3 else []

            # Collect all unique sampler rotations assigned
            assigned_codes = []
            if sampler_replacements and res.name in sampler_replacements:
                seen = set()
                for _w, code in sorted(sampler_replacements[res.name].items()):
                    if code not in seen:
                        assigned_codes.append(code)
                        seen.add(code)

            fulfilled = []
            for code in assigned_codes:
                if code in top3:
                    fulfilled.append(f"{code} (top 3)")
                elif code in bottom3:
                    fulfilled.append(f"{code} (bottom 3!)")

            top_str = ", ".join(top3) if top3 else "none"
            btm_str = ", ".join(bottom3) if bottom3 else "none"
            choice_str = ", ".join(assigned_codes) if assigned_codes else "?"
            lines.append(f"  {res.name}: top3=[{top_str}] bottom3=[{btm_str}] → assigned [{choice_str}]")
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
        evaluated_count = 0
        for res in sorted(r3_zir, key=lambda r: r.name):
            # Find actual Zir block
            actual_zir_block = None
            for w, code in res.schedule.items():
                if code == "Zir":
                    actual_zir_block = grid.week_to_block(w)
                    break
            prefs = res.zir_prefs.preferred_blocks
            if actual_zir_block is None and not res.is_esir:
                # Not assigned Zir and not ESIR — not a miss, just skipped
                status = "N/A"
            else:
                evaluated_count += 1
                match = actual_zir_block in prefs if actual_zir_block else False
                if match:
                    fulfilled_count += 1
                status = "MATCH" if match else "miss"
            actual_str = str(actual_zir_block) if actual_zir_block else "none"
            lines.append(f"  {res.name}: preferred={prefs} actual=B{actual_str} [{status}]")
        lines.append(f"  Summary: {fulfilled_count}/{evaluated_count} matched preferred Zir block")
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

            # Find assigned FSE blocks from r4_meta
            fse_blocks = []
            if r4_meta and res.name in r4_meta:
                fse_placed = r4_meta[res.name].get("fse_placed_blocks", [])
                fse_blocks = [(b, code) for b, code in fse_placed]

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

    # ── R3: Longest Uninterrupted Sequential Blocks ───────
    # R4s excluded: consecutive runs are expected (ESNR 6×Mucic, ESIR 8×Mir, etc.)
    lines.append("\n## R3 — LONGEST CONSECUTIVE SAME-ROTATION RUNS")
    for r_year, label in [(3, "R3")]:
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


# ── Satisfaction report helpers ──────────────────────────────────────

_NON_CLINICAL_CODES = {"Res", "CEP", "AIRP", "LC", "CORE", "Mx", "Mnf", "Snf", "Snf2", "Sx", "Msamp"}


def _nf_timing_penalized(pref: str, w: int) -> bool:
    """Return True if NF in week *w* violates the resident's timing preference."""
    if pref == "avoid-july":
        return w <= 4
    elif pref == "early-holidays-ok":
        return w > 40
    elif pref == "late":
        return w <= 16
    elif pref == "late-fall":
        return w <= 16 or w > 36
    elif pref == "avoid-core-adjacent":
        return w >= 41
    # "holidays-ok" or empty → never penalized
    return False


def _section_alignment(res: Resident, grid: ScheduleGrid, num_weeks: int = 52) -> float | None:
    """Compute 0-1 section preference alignment score for a resident.

    Looks up each assigned week's rotation code in ``res.section_prefs.scores``
    (keys are rotation codes like ``"Mai"``, ``"Mucic"``).
    Normalizes the raw average from [-3, +3] to [0, 1].
    """
    if not res.section_prefs or not res.section_prefs.scores:
        return None

    scores = res.section_prefs.scores
    total = 0.0
    count = 0
    for w in range(1, num_weeks + 1):
        code = grid.get(res.name, w)
        if not code or code in _NON_CLINICAL_CODES:
            continue
        if code in scores:
            total += scores[code]
            count += 1

    if count == 0:
        return None
    raw = total / count  # in [-3, 3]
    return max(0.0, min(1.0, (raw + 3) / 6))


def _nf_compliance(
    res: Resident,
    nf_weeks: list[tuple[int, str]],
    blocks: list,
) -> dict:
    """Compute NF compliance sub-scores for a resident.

    Returns dict with keys: nocall, timing, holiday, combined, details.
    """
    details: list[str] = []
    total_nf = len(nf_weeks)
    if total_nf == 0:
        return {"nocall": 1.0, "timing": 1.0, "holiday": 1.0, "combined": 1.0, "details": ["no NF assigned"]}

    from schedule_maker.phases.night_float import nocall_dates_to_weeks, compute_holiday_weeks

    # No-call compliance
    forbidden = set()
    if res.no_call and res.no_call.raw_dates:
        forbidden = nocall_dates_to_weeks(res.no_call.raw_dates, blocks)
    nocall_violations = sum(1 for w, _ in nf_weeks if w in forbidden)
    nocall_score = 1.0 - nocall_violations / total_nf
    if nocall_violations:
        details.append(f"no-call violations: {nocall_violations}/{total_nf}")

    # Timing compliance
    pref = res.nf_timing_pref
    if pref:
        penalized = sum(1 for w, _ in nf_weeks if _nf_timing_penalized(pref, w))
        timing_score = 1.0 - penalized / total_nf
        if penalized:
            details.append(f"timing violations ({pref}): {penalized}/{total_nf}")
    else:
        timing_score = 1.0

    # Holiday compliance  (compute_holiday_weeks imported above)
    holiday_map = compute_holiday_weeks(blocks)
    all_holiday_weeks = set()
    for hw_list in holiday_map.values():
        all_holiday_weeks.update(hw_list)
    nf_week_set = {w for w, _ in nf_weeks}
    holiday_overlaps = nf_week_set & all_holiday_weeks
    if holiday_overlaps:
        # Check if resident wanted to work holidays
        hw_pref = getattr(res.no_call, "holiday_work_pref", "")
        if hw_pref and hw_pref.lower() not in ("no preference", ""):
            # They expressed a holiday they'd work — only penalize mismatches
            wanted_holidays = set()
            for hol_name, hol_weeks in holiday_map.items():
                if hw_pref.lower() in hol_name.lower():
                    wanted_holidays.update(hol_weeks)
            unwanted = holiday_overlaps - wanted_holidays
            holiday_score = 1.0 - len(unwanted) / len(holiday_overlaps) if holiday_overlaps else 1.0
        else:
            # No preference — penalize all holiday NF
            holiday_score = 1.0 - len(holiday_overlaps) / total_nf
        if holiday_score < 1.0:
            details.append(f"holiday NF: {len(holiday_overlaps)} weeks")
    else:
        holiday_score = 1.0

    combined = (nocall_score + timing_score + holiday_score) / 3
    return {
        "nocall": nocall_score,
        "timing": timing_score,
        "holiday": holiday_score,
        "combined": combined,
        "details": details,
    }


def _composite_score(components: dict[str, float | None], weights: dict[str, float]) -> float:
    """Compute weighted composite score (0-100), redistributing weight from None components."""
    active = {k: v for k, v in components.items() if v is not None and k in weights}
    if not active:
        return 0.0
    total_weight = sum(weights[k] for k in active)
    if total_weight == 0:
        return 0.0
    score = sum(active[k] * weights[k] for k in active) / total_weight
    return round(score * 100, 1)


def generate_satisfaction_report(
    residents: list[Resident],
    grid: ScheduleGrid,
    nf_result: object | None = None,
    r2_result: object | None = None,
    r3_meta: dict[str, dict] | None = None,
    r4_meta: dict[str, dict] | None = None,
    sampler_replacements: dict[str, dict[int, str]] | None = None,
) -> str:
    """Generate a per-resident satisfaction report with composite scores."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("RESIDENT SATISFACTION REPORT")
    lines.append("=" * 70)

    # Build NF lookup: name → [(week, code)]
    nf_by_name: dict[str, list[tuple[int, str]]] = {}
    if nf_result and nf_result.feasible:
        nf_by_name = dict(nf_result.assignments)

    blocks = grid.blocks

    # ── R1 ──
    r1s = sorted([r for r in residents if r.r_year == 1], key=lambda r: r.name)
    r1_weights = {"sampler": 1.0}
    lines.append("\n## R1 — SATISFACTION SCORES")
    lines.append(f"  {'Name':<30} {'Sampler':>8} {'Composite':>10}")
    r1_composites: list[float] = []
    for res in r1s:
        sampler_score: float | None = None
        if sampler_replacements and res.name in sampler_replacements and res.sampler_prefs and res.sampler_prefs.rankings:
            rankings = res.sampler_prefs.rankings
            sorted_prefs = sorted(rankings.items(), key=lambda x: x[1])
            top3 = {code for code, _ in sorted_prefs[:3]}
            assigned = sampler_replacements[res.name]
            assigned_codes = set(assigned.values())
            if assigned_codes:
                matches = len(assigned_codes & top3)
                sampler_score = matches / len(assigned_codes)
        comps = {"sampler": sampler_score}
        composite = _composite_score(comps, r1_weights)
        r1_composites.append(composite)
        sam_str = f"{sampler_score:.2f}" if sampler_score is not None else "N/A"
        lines.append(f"  {res.name:<30} {sam_str:>8} {composite:>10.1f}")
    if r1_composites:
        lines.append(f"  R1 avg: {sum(r1_composites) / len(r1_composites):.0f}")

    # ── R2 ──
    r2s = sorted([r for r in residents if r.r_year == 2], key=lambda r: r.name)
    r2_weights = {"track": 0.6, "nf": 0.4}
    lines.append(f"\n## R2 — SATISFACTION SCORES")
    lines.append(f"  {'Name':<30} {'Track':>8} {'NF':>8} {'Composite':>10}")
    r2_composites: list[float] = []
    for res in r2s:
        # Track rank score
        track_score: float | None = None
        if r2_result and hasattr(r2_result, "per_resident") and r2_result.per_resident:
            info = r2_result.per_resident.get(res.name)
            if info:
                rank = info.get("rank")
                num_tracks = len(r2_result.per_resident) if hasattr(r2_result, "per_resident") else 15
                # Get actual number of tracks from track_prefs if available
                if res.track_prefs and res.track_prefs.rankings:
                    num_tracks = len(res.track_prefs.rankings)
                if isinstance(rank, int) and num_tracks > 1:
                    track_score = 1.0 - (rank - 1) / (num_tracks - 1)

        # NF compliance
        nf_weeks = nf_by_name.get(res.name, [])
        nf_comp = _nf_compliance(res, nf_weeks, blocks)
        nf_score = nf_comp["combined"]

        comps = {"track": track_score, "nf": nf_score}
        composite = _composite_score(comps, r2_weights)
        r2_composites.append(composite)
        trk_str = f"{track_score:.2f}" if track_score is not None else "N/A"
        lines.append(f"  {res.name:<30} {trk_str:>8} {nf_score:>8.2f} {composite:>10.1f}")
    if r2_composites:
        lines.append(f"  R2 avg: {sum(r2_composites) / len(r2_composites):.0f}")

    # ── R3 ──
    r3s = sorted([r for r in residents if r.r_year == 3], key=lambda r: r.name)
    r3_weights = {"section": 0.35, "zir": 0.10, "airp": 0.15, "nf": 0.40}
    lines.append(f"\n## R3 — SATISFACTION SCORES")
    lines.append(f"  {'Name':<30} {'Section':>8} {'Zir':>6} {'AIRP':>6} {'NF':>8} {'Composite':>10}")
    r3_composites: list[float] = []
    for res in r3s:
        sec_score = _section_alignment(res, grid)

        # Zir timing
        zir_score: float | None = None
        if res.zir_prefs and res.zir_prefs.preferred_blocks:
            actual_zir_block = None
            for w, code in res.schedule.items():
                if code == "Zir":
                    actual_zir_block = grid.week_to_block(w)
                    break
            if actual_zir_block is not None:
                zir_score = 1.0 if actual_zir_block in res.zir_prefs.preferred_blocks else 0.0
            else:
                zir_score = None  # not assigned Zir — skip
        elif not res.is_esir:
            zir_score = None  # no pref and not ESIR — skip

        # AIRP session
        airp_score: float | None = None
        if res.airp_prefs and res.airp_prefs.rankings and r3_meta:
            assigned_session = r3_meta.get(res.name, {}).get("airp_session", "")
            if assigned_session:
                rank = res.airp_prefs.rankings.get(assigned_session)
                num_sessions = len(res.airp_prefs.rankings)
                if rank is not None and num_sessions > 1:
                    airp_score = 1.0 - (rank - 1) / (num_sessions - 1)
                elif rank is not None:
                    airp_score = 1.0

        # NF compliance
        nf_weeks = nf_by_name.get(res.name, [])
        nf_comp = _nf_compliance(res, nf_weeks, blocks)
        nf_score = nf_comp["combined"]

        comps = {"section": sec_score, "zir": zir_score, "airp": airp_score, "nf": nf_score}
        composite = _composite_score(comps, r3_weights)
        r3_composites.append(composite)
        sec_str = f"{sec_score:.2f}" if sec_score is not None else "N/A"
        zir_str = f"{zir_score:.1f}" if zir_score is not None else "N/A"
        airp_str = f"{airp_score:.2f}" if airp_score is not None else "N/A"
        lines.append(f"  {res.name:<30} {sec_str:>8} {zir_str:>6} {airp_str:>6} {nf_score:>8.2f} {composite:>10.1f}")
    if r3_composites:
        lines.append(f"  R3 avg: {sum(r3_composites) / len(r3_composites):.0f}")

    # ── R4 ──
    r4s = sorted([r for r in residents if r.r_year == 4], key=lambda r: r.name)
    r4_weights = {"section": 0.30, "fse": 0.20, "block": 0.20, "nf": 0.30}
    lines.append(f"\n## R4 — SATISFACTION SCORES")
    lines.append(f"  {'Name':<30} {'Section':>8} {'FSE':>6} {'Block':>6} {'NF':>8} {'Composite':>10}")
    r4_composites: list[float] = []
    for res in r4s:
        sec_score = _section_alignment(res, grid)

        # FSE match
        fse_score: float | None = None
        if res.fse_prefs and res.fse_prefs.specialties and r4_meta:
            meta = r4_meta.get(res.name, {})
            fse_placed = meta.get("fse_placed_blocks", [])
            if fse_placed:
                # Specialty placed = 1.0
                spec_placed = 1.0
                # Contiguity match
                block_nums = sorted(set(b for b, _ in fse_placed))
                is_contiguous = all(
                    block_nums[i] + 1 == block_nums[i + 1]
                    for i in range(len(block_nums) - 1)
                ) if len(block_nums) > 1 else True
                org_pref = res.fse_prefs.organization or ""
                if org_pref:
                    want_contig = "contig" in org_pref.lower()
                    contig_match = 1.0 if want_contig == is_contiguous else 0.0
                else:
                    contig_match = 1.0  # no pref → no penalty
                fse_score = (spec_placed + contig_match) / 2
            else:
                fse_score = 0.0

        # Block requests
        block_score: float | None = None
        if res.block_requests:
            fulfilled = 0
            total = len(res.block_requests)
            for blk, wanted_code in res.block_requests.items():
                # Check if that block has the wanted rotation
                start_w = (blk - 1) * 4 + 1
                for w in range(start_w, start_w + 4):
                    if res.schedule.get(w) == wanted_code:
                        fulfilled += 1
                        break
            block_score = fulfilled / total if total > 0 else 1.0

        # NF compliance
        nf_weeks = nf_by_name.get(res.name, [])
        nf_comp = _nf_compliance(res, nf_weeks, blocks)
        nf_score = nf_comp["combined"]

        comps = {"section": sec_score, "fse": fse_score, "block": block_score, "nf": nf_score}
        composite = _composite_score(comps, r4_weights)
        r4_composites.append(composite)
        sec_str = f"{sec_score:.2f}" if sec_score is not None else "N/A"
        fse_str = f"{fse_score:.2f}" if fse_score is not None else "N/A"
        blk_str = f"{block_score:.2f}" if block_score is not None else "N/A"
        lines.append(f"  {res.name:<30} {sec_str:>8} {fse_str:>6} {blk_str:>6} {nf_score:>8.2f} {composite:>10.1f}")
    if r4_composites:
        lines.append(f"  R4 avg: {sum(r4_composites) / len(r4_composites):.0f}")

    # ── Per-Resident Details (R3/R4) ──
    lines.append(f"\n## PER-RESIDENT DETAILS (R3/R4)")
    for res in sorted([r for r in residents if r.r_year in (3, 4)], key=lambda r: r.name):
        lines.append(f"\n  --- {res.name} (R{res.r_year}) ---")

        # Section prefs detail
        if res.section_prefs and res.section_prefs.scores:
            scores = res.section_prefs.scores
            sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
            top_prefs = [f"{c}({s:+d})" for c, s in sorted_scores if s > 0][:5]
            bot_prefs = [f"{c}({s:+d})" for c, s in sorted_scores if s < 0][:3]
            lines.append(f"  Section prefs: top=[{', '.join(top_prefs)}] bottom=[{', '.join(bot_prefs)}]")

            # Assigned rotation counts
            rot_counts: dict[str, int] = {}
            pos_weeks = 0
            neg_weeks = 0
            scored_weeks = 0
            for w in range(1, 53):
                code = grid.get(res.name, w)
                if not code or code in _NON_CLINICAL_CODES:
                    continue
                rot_counts[code] = rot_counts.get(code, 0) + 1
                if code in scores:
                    scored_weeks += 1
                    if scores[code] > 0:
                        pos_weeks += 1
                    elif scores[code] < 0:
                        neg_weeks += 1
            rot_str = ", ".join(f"{c} x{n}wk" for c, n in sorted(rot_counts.items(), key=lambda x: -x[1])[:6])
            lines.append(f"  Assigned: {rot_str}")
            if scored_weeks:
                total_clin = sum(rot_counts.values())
                lines.append(f"  Alignment: positive-pref weeks: {pos_weeks}/{total_clin}, negative-pref weeks: {neg_weeks}/{total_clin}")

        # NF detail
        nf_weeks = nf_by_name.get(res.name, [])
        if nf_weeks:
            nf_str = ", ".join(f"{code} wk{w}" for w, code in sorted(nf_weeks))
            nf_comp = _nf_compliance(res, nf_weeks, blocks)
            detail_str = " — " + "; ".join(nf_comp["details"]) if nf_comp["details"] else " — all OK"
            lines.append(f"  NF: {nf_str}{detail_str}")

        # Block requests
        if res.block_requests:
            for blk, wanted in res.block_requests.items():
                start_w = (blk - 1) * 4 + 1
                actual = res.schedule.get(start_w, "?")
                status = "MATCH" if actual == wanted else f"got {actual}"
                lines.append(f"  Block request: B{blk}={wanted} [{status}]")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def compute_staffing_variance(
    grid: ScheduleGrid,
    constraints: list[StaffingConstraint] | None = None,
    num_weeks: int = 52,
) -> float:
    """Compute variance of staffing levels across weeks.

    Lower variance indicates more evenly distributed staffing throughout
    the academic year. Uses dynamic staffing constraints if provided,
    otherwise falls back to ROTATION_MINIMUMS.

    Returns:
        Standard deviation of weekly staffing totals.
    """
    import statistics
    from schedule_maker.validation.staffing import ROTATION_MINIMUMS

    # Gather all constraint groups
    constraint_groups: list[set[str]] = []
    if constraints:
        for sc in constraints:
            if sc.rotation_codes not in constraint_groups:
                constraint_groups.append(sc.rotation_codes)
    else:
        for _label, (codes, _min) in ROTATION_MINIMUMS.items():
            if codes not in constraint_groups:
                constraint_groups.append(codes)

    if not constraint_groups:
        return 0.0

    weekly_totals = []
    for w in range(1, num_weeks + 1):
        total = sum(
            grid.get_section_staffing(w, codes)
            for codes in constraint_groups
        )
        weekly_totals.append(total)

    if len(weekly_totals) < 2:
        return 0.0
    return statistics.stdev(weekly_totals)


def compute_multi_objective_score(
    residents: list[Resident],
    grid: ScheduleGrid,
    nf_result: object | None = None,
    r3_meta: dict[str, dict] | None = None,
    r4_meta: dict[str, dict] | None = None,
    sampler_replacements: dict | None = None,
    staffing_constraints: list[StaffingConstraint] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute multi-objective optimization score for a schedule.

    Components:
    - mean_satisfaction: Average R3/R4 composite satisfaction (0-100)
    - min_satisfaction: Minimum R3/R4 composite satisfaction (fairness)
    - staffing_variance: Standard deviation of weekly staffing (lower=better)

    Args:
        weights: Optional dict with keys "mean", "min", "variance".
            Default weights: {"mean": 0.5, "min": 0.3, "variance": 0.2}

    Returns:
        Dict with keys: mean_satisfaction, min_satisfaction, staffing_variance,
        composite (weighted combination where higher is better).
    """
    if weights is None:
        weights = {"mean": 0.5, "min": 0.3, "variance": 0.2}

    # Compute per-resident satisfaction scores
    individual_scores = []
    nf_by_name: dict[str, list[tuple[int, str]]] = {}
    if nf_result and nf_result.feasible:
        nf_by_name = dict(nf_result.assignments)

    blocks = grid.blocks

    # R3 scores
    r3_weights = {"section": 0.35, "zir": 0.10, "airp": 0.15, "nf": 0.40}
    for res in residents:
        if res.r_year != 3:
            continue
        sec_score = _section_alignment(res, grid)

        zir_score: float | None = None
        if res.zir_prefs and res.zir_prefs.preferred_blocks:
            for w, code in res.schedule.items():
                if code == "Zir":
                    actual_zir_block = grid.week_to_block(w)
                    zir_score = 1.0 if actual_zir_block in res.zir_prefs.preferred_blocks else 0.0
                    break
        elif not res.is_esir:
            zir_score = None

        airp_score: float | None = None
        if res.airp_prefs and res.airp_prefs.rankings and r3_meta:
            assigned_session = r3_meta.get(res.name, {}).get("airp_session", "")
            if assigned_session:
                rank = res.airp_prefs.rankings.get(assigned_session)
                num_sessions = len(res.airp_prefs.rankings)
                if rank is not None and num_sessions > 1:
                    airp_score = 1.0 - (rank - 1) / (num_sessions - 1)
                elif rank is not None:
                    airp_score = 1.0

        nf_weeks = nf_by_name.get(res.name, [])
        nf_comp = _nf_compliance(res, nf_weeks, blocks)
        nf_score = nf_comp["combined"]

        score = _composite_score(
            {"section": sec_score, "zir": zir_score, "airp": airp_score, "nf": nf_score},
            r3_weights,
        )
        individual_scores.append(score)

    # R4 scores
    r4_weights = {"section": 0.30, "fse": 0.20, "block": 0.20, "nf": 0.30}
    for res in residents:
        if res.r_year != 4:
            continue
        sec_score = _section_alignment(res, grid)

        fse_score: float | None = None
        if res.fse_prefs and res.fse_prefs.specialties and r4_meta:
            meta = r4_meta.get(res.name, {})
            fse_placed = meta.get("fse_placed_blocks", [])
            if fse_placed:
                block_nums = sorted(set(b for b, _ in fse_placed))
                is_contiguous = all(
                    block_nums[i] + 1 == block_nums[i + 1]
                    for i in range(len(block_nums) - 1)
                ) if len(block_nums) > 1 else True
                org_pref = res.fse_prefs.organization or ""
                if org_pref:
                    want_contig = "contig" in org_pref.lower()
                    contig_match = 1.0 if want_contig == is_contiguous else 0.0
                else:
                    contig_match = 1.0
                fse_score = (1.0 + contig_match) / 2
            else:
                fse_score = 0.0

        block_score: float | None = None
        if res.block_requests:
            fulfilled = 0
            total = len(res.block_requests)
            for blk, wanted_code in res.block_requests.items():
                start_w = (blk - 1) * 4 + 1
                for w in range(start_w, start_w + 4):
                    if res.schedule.get(w) == wanted_code:
                        fulfilled += 1
                        break
            block_score = fulfilled / total if total > 0 else 1.0

        nf_weeks = nf_by_name.get(res.name, [])
        nf_comp = _nf_compliance(res, nf_weeks, blocks)
        nf_score = nf_comp["combined"]

        score = _composite_score(
            {"section": sec_score, "fse": fse_score, "block": block_score, "nf": nf_score},
            r4_weights,
        )
        individual_scores.append(score)

    # Compute aggregate metrics
    if not individual_scores:
        return {
            "mean_satisfaction": 0.0,
            "min_satisfaction": 0.0,
            "staffing_variance": 0.0,
            "composite": 0.0,
        }

    import statistics
    mean_sat = statistics.mean(individual_scores)
    min_sat = min(individual_scores)
    staffing_var = compute_staffing_variance(grid, staffing_constraints)

    # Normalize staffing variance to 0-100 scale (lower variance = higher score)
    # Cap at 20 as typical variance, so variance=20 -> 0, variance=0 -> 100
    variance_score = max(0.0, 100.0 - staffing_var * 5.0)

    # Compute weighted composite
    composite = (
        weights.get("mean", 0.5) * mean_sat +
        weights.get("min", 0.3) * min_sat +
        weights.get("variance", 0.2) * variance_score
    )

    return {
        "mean_satisfaction": mean_sat,
        "min_satisfaction": min_sat,
        "staffing_variance": staffing_var,
        "composite": composite,
    }


def compute_r3r4_satisfaction(
    residents: list[Resident],
    grid: ScheduleGrid,
    nf_result: object | None = None,
    r3_meta: dict[str, dict] | None = None,
    r4_meta: dict[str, dict] | None = None,
    sampler_replacements: dict | None = None,
    r2_result: object | None = None,
) -> float:
    """Mean composite satisfaction for R3+R4 residents (0–100 scale).

    Used by the multi-trial optimizer to compare trial outcomes.
    Reuses the same per-resident scoring logic as generate_satisfaction_report().
    """
    nf_by_name: dict[str, list[tuple[int, str]]] = {}
    if nf_result and nf_result.feasible:
        nf_by_name = dict(nf_result.assignments)

    blocks = grid.blocks
    composites: list[float] = []

    # ── R3 ──
    r3_weights = {"section": 0.35, "zir": 0.10, "airp": 0.15, "nf": 0.40}
    for res in residents:
        if res.r_year != 3:
            continue
        sec_score = _section_alignment(res, grid)

        zir_score: float | None = None
        if res.zir_prefs and res.zir_prefs.preferred_blocks:
            for w, code in res.schedule.items():
                if code == "Zir":
                    actual_zir_block = grid.week_to_block(w)
                    zir_score = 1.0 if actual_zir_block in res.zir_prefs.preferred_blocks else 0.0
                    break
        elif not res.is_esir:
            zir_score = None

        airp_score: float | None = None
        if res.airp_prefs and res.airp_prefs.rankings and r3_meta:
            assigned_session = r3_meta.get(res.name, {}).get("airp_session", "")
            if assigned_session:
                rank = res.airp_prefs.rankings.get(assigned_session)
                num_sessions = len(res.airp_prefs.rankings)
                if rank is not None and num_sessions > 1:
                    airp_score = 1.0 - (rank - 1) / (num_sessions - 1)
                elif rank is not None:
                    airp_score = 1.0

        nf_weeks = nf_by_name.get(res.name, [])
        nf_comp = _nf_compliance(res, nf_weeks, blocks)
        nf_score = nf_comp["combined"]

        composites.append(_composite_score(
            {"section": sec_score, "zir": zir_score, "airp": airp_score, "nf": nf_score},
            r3_weights,
        ))

    # ── R4 ──
    r4_weights = {"section": 0.30, "fse": 0.20, "block": 0.20, "nf": 0.30}
    for res in residents:
        if res.r_year != 4:
            continue
        sec_score = _section_alignment(res, grid)

        fse_score: float | None = None
        if res.fse_prefs and res.fse_prefs.specialties and r4_meta:
            meta = r4_meta.get(res.name, {})
            fse_placed = meta.get("fse_placed_blocks", [])
            if fse_placed:
                block_nums = sorted(set(b for b, _ in fse_placed))
                is_contiguous = all(
                    block_nums[i] + 1 == block_nums[i + 1]
                    for i in range(len(block_nums) - 1)
                ) if len(block_nums) > 1 else True
                org_pref = res.fse_prefs.organization or ""
                if org_pref:
                    want_contig = "contig" in org_pref.lower()
                    contig_match = 1.0 if want_contig == is_contiguous else 0.0
                else:
                    contig_match = 1.0
                fse_score = (1.0 + contig_match) / 2
            else:
                fse_score = 0.0

        block_score: float | None = None
        if res.block_requests:
            fulfilled = 0
            total = len(res.block_requests)
            for blk, wanted_code in res.block_requests.items():
                start_w = (blk - 1) * 4 + 1
                for w in range(start_w, start_w + 4):
                    if res.schedule.get(w) == wanted_code:
                        fulfilled += 1
                        break
            block_score = fulfilled / total if total > 0 else 1.0

        nf_weeks = nf_by_name.get(res.name, [])
        nf_comp = _nf_compliance(res, nf_weeks, blocks)
        nf_score = nf_comp["combined"]

        composites.append(_composite_score(
            {"section": sec_score, "fse": fse_score, "block": block_score, "nf": nf_score},
            r4_weights,
        ))

    if not composites:
        return 0.0
    return sum(composites) / len(composites)
