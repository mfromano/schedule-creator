"""Soft preference tests for the schedule builder.

Tests compute statistics on preference fulfillment and apply soft thresholds.
Hard asserts are reserved for invariants (hospital conflicts, grad reqs, coverage).
Soft tests warn on poor outcomes but only fail if results are catastrophically bad.
"""

from __future__ import annotations

import pytest

from schedule_maker.validation.hospital_conflict import check_hospital_conflicts
from schedule_maker.validation.graduation import check_graduation
from schedule_maker.validation.staffing import check_staffing, ROTATION_MAXIMUMS
from schedule_maker.phases.r4_builder import _fse_to_rotation_code, HOSPITAL_CONFLICT_EXEMPT
from schedule_maker.staffing_utils import _ROTATION_YEAR_ELIGIBILITY
from schedule_maker.models.resident import Pathway
from schedule_maker.models.rotation import fse_to_base_code


# ── Helpers ──────────────────────────────────────────────────────


def _residents_by_year(residents, year):
    return [r for r in residents if r.r_year == year]


# ── R1: Sampler Preferences ─────────────────────────────────────


class TestR1SamplerPrefs:
    def test_sampler_top3_rate(self, build_result):
        residents, grid, _, _, _, sampler_replacements, *_ = build_result
        r1s = _residents_by_year(residents, 1)
        r1_with_prefs = [r for r in r1s if r.sampler_prefs and r.sampler_prefs.rankings]
        if not r1_with_prefs:
            pytest.skip("No R1 sampler preferences recorded")

        top3_count = 0
        for res in r1_with_prefs:
            sorted_prefs = sorted(res.sampler_prefs.rankings.items(), key=lambda x: x[1])
            top3_codes = {code for code, _ in sorted_prefs[:3]}
            assigned = None
            if res.name in sampler_replacements:
                for _w, code in sampler_replacements[res.name].items():
                    if code in ("Mucic", "Mir"):
                        assigned = code
                        break
            if assigned and assigned in top3_codes:
                top3_count += 1

        rate = top3_count / len(r1_with_prefs)
        print(f"\nR1 sampler top-3 rate: {top3_count}/{len(r1_with_prefs)} = {rate:.0%}")
        if rate < 0.5:
            pytest.xfail(f"R1 sampler top-3 rate {rate:.0%} < 50% threshold")

    def test_sampler_stats(self, build_result):
        residents, _, _, _, _, sampler_replacements, *_ = build_result
        r1s = _residents_by_year(residents, 1)
        r1_with_prefs = [r for r in r1s if r.sampler_prefs and r.sampler_prefs.rankings]
        if not r1_with_prefs:
            pytest.skip("No R1 sampler preferences recorded")

        rank_positions = []
        for res in r1_with_prefs:
            assigned = None
            if res.name in sampler_replacements:
                for _w, code in sampler_replacements[res.name].items():
                    if code in ("Mucic", "Mir"):
                        assigned = code
                        break
            if assigned:
                rank = res.sampler_prefs.rankings.get(assigned)
                if rank is not None:
                    rank_positions.append(rank)
                    print(f"  {res.name}: {assigned} (rank #{rank})")

        if rank_positions:
            avg = sum(rank_positions) / len(rank_positions)
            print(f"\nR1 sampler avg rank: {avg:.1f}, distribution: {sorted(rank_positions)}")


# ── R2: Track Preferences ───────────────────────────────────────


class TestR2TrackPrefs:
    def test_avg_track_rank(self, build_result):
        _, _, r2_result, *_ = build_result
        if not r2_result.feasible or not r2_result.per_resident:
            pytest.skip("R2 assignment not feasible or no data")

        ranks = [info["rank"] for info in r2_result.per_resident.values()]
        avg = sum(ranks) / len(ranks)
        print(f"\nR2 avg rank: {avg:.1f}, distribution: {sorted(ranks)}")
        assert avg <= 8, f"Avg R2 rank {avg:.1f} exceeds soft threshold of 8"

    def test_within_top3_rate(self, build_result):
        _, _, r2_result, *_ = build_result
        if not r2_result.feasible or not r2_result.per_resident:
            pytest.skip("R2 assignment not feasible or no data")

        ranks = [info["rank"] for info in r2_result.per_resident.values()]
        within_3 = sum(1 for r in ranks if r <= 3)
        rate = within_3 / len(ranks)
        print(f"\nR2 within top-3: {within_3}/{len(ranks)} = {rate:.0%}")
        for name, info in sorted(r2_result.per_resident.items()):
            print(f"  {name}: Track {info['track']} (rank #{info['rank']})")
        assert rate >= 0.6, f"R2 top-3 rate {rate:.0%} below 60% threshold"

    def test_no_rank_above_10(self, build_result):
        _, _, r2_result, *_ = build_result
        if not r2_result.feasible or not r2_result.per_resident:
            pytest.skip("R2 assignment not feasible or no data")

        bad = [(name, info["rank"]) for name, info in r2_result.per_resident.items()
               if info["rank"] > 10]
        if bad:
            names = ", ".join(f"{n} (rank #{r})" for n, r in bad)
            pytest.xfail(f"R2s with rank >10: {names}")


# ── R3: AIRP Preferences ────────────────────────────────────────


class TestR3AIRP:
    def test_airp_top3_rate(self, build_result):
        residents, _, _, r3_meta, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        r3_airp = [r for r in r3s if r.airp_prefs and r.airp_prefs.rankings]
        if not r3_airp:
            pytest.skip("No R3 AIRP preferences")

        top3_count = 0
        for res in r3_airp:
            assigned = r3_meta.get(res.name, {}).get("airp_session", "")
            rank = res.airp_prefs.rankings.get(assigned)
            if rank is not None and rank <= 3:
                top3_count += 1
            print(f"  {res.name}: assigned={assigned}, rank={rank}")

        rate = top3_count / len(r3_airp)
        print(f"\nAIRP top-3 rate: {top3_count}/{len(r3_airp)} = {rate:.0%}")
        assert rate >= 0.8, f"AIRP top-3 rate {rate:.0%} below 80% threshold"

    def test_airp_session_balance(self, build_result):
        residents, _, _, r3_meta, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        if not r3_meta:
            pytest.skip("No R3 metadata")

        sessions: dict[str, int] = {}
        for res in r3s:
            session = r3_meta.get(res.name, {}).get("airp_session", "")
            if session:
                sessions[session] = sessions.get(session, 0) + 1

        if not sessions:
            pytest.skip("No AIRP sessions assigned")

        counts = list(sessions.values())
        imbalance = max(counts) - min(counts)
        print(f"\nAIRP session sizes: {sessions} (imbalance={imbalance})")
        assert imbalance <= 2, f"AIRP session imbalance {imbalance} > 2"

    def test_airp_groupmates(self, build_result):
        residents, _, _, r3_meta, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        r3_with_groups = [r for r in r3s
                          if r.airp_prefs and r.airp_prefs.group_requests]
        if not r3_with_groups:
            pytest.skip("No groupmate requests")

        fulfilled = 0
        total = 0
        for res in r3_with_groups:
            my_session = r3_meta.get(res.name, {}).get("airp_session", "")
            for mate in res.airp_prefs.group_requests:
                mate_session = r3_meta.get(mate, {}).get("airp_session", "")
                total += 1
                if mate_session == my_session and my_session:
                    fulfilled += 1
                print(f"  {res.name} + {mate}: {my_session} vs {mate_session}")

        rate = fulfilled / total if total else 0
        print(f"\nGroupmate fulfillment: {fulfilled}/{total} = {rate:.0%}")
        if rate < 0.5:
            pytest.xfail(f"Groupmate fulfillment {rate:.0%} < 50%")


# ── R3: Zir Preferences ─────────────────────────────────────────


class TestR3Zir:
    def test_max_one_zir_per_r3(self, build_result):
        residents, grid, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        for res in r3s:
            zir_weeks = sum(1 for w, code in res.schedule.items() if code == "Zir")
            assert zir_weeks <= 4, (
                f"{res.name} has {zir_weeks} Zir weeks (>1 block)")

    def test_zir_pref_match_rate(self, build_result):
        residents, grid, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        r3_zir = [r for r in r3s if r.zir_prefs and r.zir_prefs.preferred_blocks]
        if not r3_zir:
            pytest.skip("No R3 Zir preferences")

        matched = 0
        for res in r3_zir:
            actual_block = None
            for w, code in res.schedule.items():
                if code == "Zir":
                    actual_block = grid.week_to_block(w)
                    break
            match = actual_block in res.zir_prefs.preferred_blocks if actual_block else False
            if match:
                matched += 1
            print(f"  {res.name}: pref={res.zir_prefs.preferred_blocks} actual=B{actual_block} "
                  f"[{'MATCH' if match else 'miss'}]")

        rate = matched / len(r3_zir)
        print(f"\nZir pref match rate: {matched}/{len(r3_zir)} = {rate:.0%}")


# ── R3: Section Preferences ─────────────────────────────────────


class TestR3SectionPrefs:
    def test_top_sections_assigned(self, build_result):
        residents, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        r3_with_prefs = [r for r in r3s if r.section_prefs and r.section_prefs.top]
        if not r3_with_prefs:
            pytest.skip("No R3 section preferences")

        total_top = 0
        assigned_top = 0
        for res in r3_with_prefs:
            scheduled_codes = set(res.schedule.values())
            hits = [c for c in res.section_prefs.top if c in scheduled_codes]
            misses = [c for c in res.section_prefs.top if c not in scheduled_codes]
            assigned_top += len(hits)
            total_top += len(res.section_prefs.top)
            if misses:
                print(f"  {res.name}: missing top prefs {misses} (got {hits})")

        rate = assigned_top / total_top if total_top else 0
        print(f"\nR3 top-section assignment rate: {assigned_top}/{total_top} = {rate:.0%}")
        assert rate >= 0.15, f"R3 top-section rate {rate:.0%} below 15% threshold"

    def test_bottom_sections_avoided(self, build_result):
        residents, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        r3_with_prefs = [r for r in r3s if r.section_prefs and r.section_prefs.bottom]
        if not r3_with_prefs:
            pytest.skip("No R3 bottom section preferences")

        violations = []
        for res in r3_with_prefs:
            scheduled_codes = set(res.schedule.values())
            for code in res.section_prefs.bottom:
                if code in scheduled_codes:
                    violations.append(f"{res.name} assigned bottom-pref {code}")

        for v in violations:
            print(f"  {v}")
        rate = len(violations) / sum(len(r.section_prefs.bottom) for r in r3_with_prefs)
        print(f"\nR3 bottom-section violation rate: {len(violations)} violations ({rate:.0%})")
        assert len(violations) <= 10, f"{len(violations)} bottom-section violations (max 10)"


# ── R4: Graduation Requirements ─────────────────────────────────


class TestR4GradRequirements:
    def test_no_r4_grad_deficits(self, build_result):
        residents, *_ = build_result
        deficits = check_graduation(residents, check_r4_only=True)
        for d in deficits:
            print(f"  DEFICIT: {d.resident_name}: {d.requirement} "
                  f"({d.total_weeks:.1f}/{d.required_weeks:.0f}, gap={d.deficit:.1f})")
        assert len(deficits) == 0, f"{len(deficits)} R4 graduation deficits"


# ── R4: FSE Preferences ─────────────────────────────────────────


class TestR4FSE:
    def test_fse_assigned_if_requested(self, build_result):
        residents, grid, *_ = build_result
        r4s = _residents_by_year(residents, 4)
        r4_fse = [r for r in r4s if r.fse_prefs and r.fse_prefs.specialties]
        if not r4_fse:
            pytest.skip("No R4 FSE preferences")

        missing = []
        partial = []
        for res in r4_fse:
            # Map each FSE specialty to its actual rotation code
            expected_codes = {
                _fse_to_rotation_code(spec): spec
                for spec in res.fse_prefs.specialties
            }
            assigned_codes = {code for code in res.schedule.values() if code}
            found = {rc for rc in expected_codes if rc in assigned_codes}
            not_found = set(expected_codes) - found

            if not found:
                missing.append(res.name)
                print(f"  {res.name}: requested FSE={res.fse_prefs.specialties} "
                      f"(codes={list(expected_codes.keys())}) but NONE assigned")
            elif not_found:
                partial.append(res.name)
                print(f"  {res.name}: requested FSE={res.fse_prefs.specialties} — "
                      f"got {sorted(found)}, missing {sorted(not_found)}")
            else:
                # Count blocks of each FSE code
                for rc, spec in expected_codes.items():
                    blocks = sum(1 for w, c in res.schedule.items() if c == rc) // 4 or 1
                    print(f"  {res.name}: FSE {spec} ({rc}) = {blocks} blocks")

        if missing:
            pytest.xfail(f"{len(missing)} R4s with FSE prefs but no matching rotation codes assigned")
        if partial:
            print(f"  NOTE: {len(partial)} R4s with partial FSE fulfillment")


# ── Hospital Conflicts ───────────────────────────────────────────


class TestHospitalConflicts:
    def test_no_hospital_conflicts(self, build_result):
        residents, *_ = build_result
        conflicts = check_hospital_conflicts(residents, exempt_names=HOSPITAL_CONFLICT_EXEMPT)
        for c in conflicts:
            print(f"  CONFLICT: {c.resident_name} Block {c.block}: "
                  f"systems={c.systems}, rotations={c.rotations}")
        assert len(conflicts) == 0, f"{len(conflicts)} hospital system conflicts"


# ── Night Float ──────────────────────────────────────────────────


class TestNightFloat:
    def test_nf_no_call_violations(self, build_result):
        _, _, _, _, _, _, nf_result, *_ = build_result
        if not nf_result.feasible:
            pytest.skip("NF assignment not feasible")

        violations = nf_result.violations or []
        for v in violations:
            print(f"  {v}")
        print(f"\nNF no-call violations: {len(violations)}")

    def test_nf_spacing(self, build_result):
        residents, grid, *_ = build_result
        violations = []
        for res in residents:
            nf_weeks = sorted(w for (name, w) in grid.nf_assignments if name == res.name)
            if len(nf_weeks) < 2:
                continue
            for i in range(1, len(nf_weeks)):
                gap = nf_weeks[i] - nf_weeks[i - 1]
                if gap < 4:
                    violations.append(
                        f"{res.name}: NF weeks {nf_weeks[i-1]} and {nf_weeks[i]} "
                        f"only {gap} weeks apart (min 4)")

        for v in violations:
            print(f"  {v}")
        assert len(violations) == 0, f"{len(violations)} NF spacing violations (<4 weeks)"

    def test_no_back_to_back_nf(self, build_result):
        """No resident can have back-to-back Sx, Mnf, or Snf2 weeks.

        Snf is excluded — it's packaged with Sx in R2 tracks by design.
        """
        residents, grid, *_ = build_result
        NF_CODES = {"Sx", "Mnf", "Snf2"}
        violations = []
        for res in residents:
            # Merge base schedule and NF overlay
            combined: dict[int, str] = {}
            for w in range(1, 53):
                nf_code = grid.nf_assignments.get((res.name, w))
                if nf_code:
                    combined[w] = nf_code
                elif res.schedule.get(w, "") in NF_CODES:
                    combined[w] = res.schedule[w]

            weeks = sorted(combined.keys())
            for i in range(1, len(weeks)):
                if weeks[i] == weeks[i - 1] + 1:
                    violations.append(
                        f"{res.name}: back-to-back NF weeks {weeks[i-1]} "
                        f"({combined[weeks[i-1]]}) and {weeks[i]} ({combined[weeks[i]]})")

        for v in violations:
            print(f"  {v}")
        assert len(violations) == 0, f"{len(violations)} back-to-back NF violations"


# ── Schedule Coverage ────────────────────────────────────────────


class TestScheduleCoverage:
    def test_no_unassigned_weeks(self, build_result):
        residents, grid, *_ = build_result
        missing = []
        for res in residents:
            empty_weeks = [w for w in range(1, 53) if not res.schedule.get(w)]
            if empty_weeks:
                missing.append((res.name, len(empty_weeks), empty_weeks[:5]))

        for name, count, examples in missing:
            print(f"  {name}: {count} unassigned weeks (e.g. {examples})")
        assert len(missing) == 0, (
            f"{len(missing)} residents have unassigned weeks")


# ── Staffing ─────────────────────────────────────────────────────


class TestStaffing:
    def test_under_minimum_count(self, build_result):
        _, grid, _, _, _, _, _, staffing_constraints = build_result
        violations = check_staffing(grid, 52, constraints=staffing_constraints)
        under = [v for v in violations if v.is_under]

        # Summarize by rotation label
        by_label: dict[str, int] = {}
        for v in under:
            by_label[v.label] = by_label.get(v.label, 0) + 1
        for label, count in sorted(by_label.items(), key=lambda x: -x[1]):
            print(f"  {label}: {count} under-minimum weeks")

        print(f"\nTotal under-minimum violations: {len(under)}")
        if len(under) > 100:
            pytest.xfail(f"{len(under)} under-minimum violations exceeds warning threshold of 100")


# ── Night Float Counts ──────────────────────────────────────────


class TestNightFloatCounts:
    """Verify NF week counts per resident year match NFRules constraints."""

    def test_r2_mnf_count(self, build_result):
        residents, grid, *_ = build_result
        r2s = _residents_by_year(residents, 2)
        for res in r2s:
            mnf_weeks = sum(
                1 for (name, w), code in grid.nf_assignments.items()
                if name == res.name and code == "Mnf"
            )
            assert mnf_weeks == 2, (
                f"{res.name} has {mnf_weeks} Mnf weeks (expected 2)")

    def test_r3_total_nf_max(self, build_result):
        residents, grid, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        for res in r3s:
            nf_weeks = sum(
                1 for (name, w), code in grid.nf_assignments.items()
                if name == res.name and code in ("Mnf", "Snf2")
            )
            assert nf_weeks <= 3, (
                f"{res.name} has {nf_weeks} NF weeks (max 3)")
            assert nf_weeks >= 1, (
                f"{res.name} has {nf_weeks} NF weeks (min 1)")

    def test_r4_snf2_count(self, build_result):
        residents, grid, *_ = build_result
        r4s = _residents_by_year(residents, 4)
        for res in r4s:
            snf2_weeks = sum(
                1 for (name, w), code in grid.nf_assignments.items()
                if name == res.name and code == "Snf2"
            )
            assert snf2_weeks == 2, (
                f"{res.name} has {snf2_weeks} Snf2 weeks (expected 2)")


# ── Night Float Eligibility ─────────────────────────────────────


class TestNightFloatEligibility:
    """R2 cannot get Snf2, R4 cannot get Mnf (by default)."""

    def test_r2_no_snf2(self, build_result):
        residents, grid, *_ = build_result
        r2s = _residents_by_year(residents, 2)
        for res in r2s:
            snf2 = [w for (name, w), code in grid.nf_assignments.items()
                    if name == res.name and code == "Snf2"]
            assert not snf2, f"{res.name} (R2) has Snf2 in weeks {snf2}"

    def test_r4_no_mnf_default(self, build_result):
        """R4 should not get Mnf unless overridden by NF Recs."""
        residents, grid, *_, nf_result, _ = build_result
        r4s = _residents_by_year(residents, 4)
        violations = []
        for res in r4s:
            mnf = [w for (name, w), code in grid.nf_assignments.items()
                   if name == res.name and code == "Mnf"]
            if mnf:
                violations.append(f"{res.name} (R4) has Mnf in weeks {mnf}")
        # This is soft — NF Recs can override r4_mnf_weeks
        if violations:
            for v in violations:
                print(f"  {v}")
            print("  (May be valid if NF Recs overrides r4_mnf_weeks > 0)")


# ── Night Float Exclusivity ─────────────────────────────────────


class TestNightFloatExclusivity:
    """Max 1 Mnf and 1 Snf2 per week across all residents."""

    def test_max_one_mnf_per_week(self, build_result):
        _, grid, *_ = build_result
        for w in range(1, 53):
            mnf_count = sum(
                1 for (name, week), code in grid.nf_assignments.items()
                if week == w and code == "Mnf"
            )
            assert mnf_count <= 1, f"Week {w}: {mnf_count} Mnf assignments (max 1)"

    def test_max_one_snf2_per_week(self, build_result):
        _, grid, *_ = build_result
        for w in range(1, 53):
            snf2_count = sum(
                1 for (name, week), code in grid.nf_assignments.items()
                if week == w and code == "Snf2"
            )
            assert snf2_count <= 1, f"Week {w}: {snf2_count} Snf2 assignments (max 1)"


# ── Staffing Maximums ───────────────────────────────────────────


class TestStaffingMaximums:
    """No per-week maximum violations across the schedule."""

    def test_no_max_violations(self, build_result):
        residents, grid, *_ = build_result
        violations = []
        for w in range(1, 53):
            week_assignments = grid.get_week_assignments(w)
            # Map FSE codes to base codes for max checks
            mapped: dict[str, str] = {}
            for name, code in week_assignments.items():
                base = fse_to_base_code(code) if code.startswith("FSE-") else code
                mapped[name] = base

            for label, (codes, max_allowed) in ROTATION_MAXIMUMS.items():
                count = sum(1 for c in mapped.values() if c in codes)
                if count > max_allowed:
                    violations.append(
                        f"Week {w}: {label} has {count} (max {max_allowed})")

        for v in violations:
            print(f"  {v}")
        print(f"\nTotal max violations: {len(violations)}")
        if len(violations) > 20:
            pytest.xfail(f"{len(violations)} staffing max violations exceeds warning threshold of 20")


# ── Rotation Year Eligibility ───────────────────────────────────


class TestRotationYearEligibility:
    """Residents should only be assigned rotations eligible for their year."""

    def test_year_eligibility(self, build_result):
        residents, grid, *_ = build_result
        violations = []
        for res in residents:
            full_sched = grid.get_resident_schedule(res.name)
            for w, code in full_sched.items():
                if code in _ROTATION_YEAR_ELIGIBILITY:
                    allowed = _ROTATION_YEAR_ELIGIBILITY[code]
                    if res.r_year not in allowed:
                        violations.append(
                            f"{res.name} (R{res.r_year}) assigned {code} "
                            f"week {w} (eligible: R{allowed or 'none'})")

        for v in violations:
            print(f"  {v}")
        assert len(violations) == 0, f"{len(violations)} year eligibility violations"


# ── ESNR Smr Cap ────────────────────────────────────────────────


class TestESNRSmrCap:
    """ESNR R4 residents: max 1 block (4 weeks) on Smr."""

    def test_esnr_max_one_smr(self, build_result):
        residents, grid, *_ = build_result
        r4s = _residents_by_year(residents, 4)
        esnr_r4s = [r for r in r4s if r.pathway & Pathway.ESNR]
        if not esnr_r4s:
            pytest.skip("No ESNR R4 residents")

        for res in esnr_r4s:
            sched = grid.get_resident_schedule(res.name)
            smr_weeks = sum(1 for c in sched.values() if c == "Smr")
            assert smr_weeks <= 4, (
                f"{res.name} (ESNR) has {smr_weeks} Smr weeks (max 4 = 1 block)")
            print(f"  {res.name}: {smr_weeks} Smr weeks")


# ── Pathway Block Counts (soft) ─────────────────────────────────


class TestPathwayBlockCounts:
    """Pathway-specific block counts (soft — xfail if unmet)."""

    def test_nrdr_r3_mnuc(self, build_result):
        residents, grid, *_ = build_result
        r3s = _residents_by_year(residents, 3)
        nrdr_r3s = [r for r in r3s if r.pathway & Pathway.NRDR]
        if not nrdr_r3s:
            pytest.skip("No NRDR R3 residents")

        for res in nrdr_r3s:
            sched = grid.get_resident_schedule(res.name)
            mnuc_weeks = sum(1 for c in sched.values() if c == "Mnuc")
            mnuc_blocks = mnuc_weeks // 4
            print(f"  {res.name}: {mnuc_blocks} blocks Mnuc ({mnuc_weeks} weeks)")
            if mnuc_blocks < 6:
                pytest.xfail(
                    f"{res.name} (NRDR R3) has {mnuc_blocks} blocks Mnuc (expected 6)")

    def test_esir_r4_mir(self, build_result):
        residents, grid, *_ = build_result
        r4s = _residents_by_year(residents, 4)
        esir_r4s = [r for r in r4s if r.pathway & Pathway.ESIR]
        if not esir_r4s:
            pytest.skip("No ESIR R4 residents")

        for res in esir_r4s:
            sched = grid.get_resident_schedule(res.name)
            mir_weeks = sum(1 for c in sched.values() if c == "Mir")
            mir_blocks = mir_weeks // 4
            print(f"  {res.name}: {mir_blocks} blocks Mir ({mir_weeks} weeks)")
            if mir_blocks < 8:
                pytest.xfail(
                    f"{res.name} (ESIR R4) has {mir_blocks} blocks Mir (expected 8)")


# ── T32 Rules ───────────────────────────────────────────────────


class TestT32Rules:
    """T32 residents: max 2 months (8 weeks) clinical pull."""

    def test_t32_max_clinical(self, build_result):
        residents, grid, *_ = build_result
        r4s = _residents_by_year(residents, 4)
        t32s = [r for r in r4s if r.pathway & Pathway.T32]
        if not t32s:
            pytest.skip("No T32 R4 residents")

        non_clinical = {"Res", "CEP", "AIRP", "LC"}
        for res in t32s:
            sched = grid.get_resident_schedule(res.name)
            clinical_weeks = sum(
                1 for c in sched.values()
                if c and c not in non_clinical
            )
            print(f"  {res.name}: {clinical_weeks} clinical weeks")
            if clinical_weeks > 8:
                pytest.xfail(
                    f"{res.name} (T32) has {clinical_weeks} clinical weeks (max 8)")
