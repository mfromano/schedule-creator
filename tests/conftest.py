"""Shared fixtures for schedule maker tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from schedule_maker.io.excel_reader import ExcelReader
from schedule_maker.io.prefs_parser import PrefsParser
from schedule_maker.models.schedule import ScheduleGrid, compute_blocks
from schedule_maker.models.constraints import NFRules
from schedule_maker.phases.r1_assignment import assign_r1_tracks
from schedule_maker.phases.r2_assignment import assign_r2_tracks
from schedule_maker.phases.r3_builder import assign_r3_fixed, fill_r3_clinical
from schedule_maker.phases.r4_builder import assign_r4_fixed, fill_r4_clinical
from schedule_maker.phases.night_float import assign_night_float
from schedule_maker.phases.sampler import resolve_samplers
from main import apply_comment_overrides


# Path to the _with_prefs file (preferences already imported, Excel recalculated)
_SCHEDULE_DIR = Path(__file__).resolve().parent.parent
_WITH_PREFS_CANDIDATES = sorted(_SCHEDULE_DIR.glob("*_with_prefs.xlsm"))


def _find_schedule_file() -> Path | None:
    """Find the most recent _with_prefs.xlsm file."""
    for p in reversed(_WITH_PREFS_CANDIDATES):
        if not p.name.startswith("~$"):
            return p
    return None


@pytest.fixture(scope="session")
def build_result():
    """Run the full build pipeline once and yield all results.

    Mirrors the logic in main.py build command (phases 0-8).
    Skips the entire test session if the schedule file is not found.
    """
    schedule_path = _find_schedule_file()
    if schedule_path is None:
        pytest.skip("No *_with_prefs.xlsm file found — skipping build-dependent tests")

    # ── Phase 0: Load data ──
    with ExcelReader(schedule_path) as reader:
        year = reader.read_academic_year()
        rotation_codes = reader.read_rotation_codes()
        residents = reader.read_roster()
        reader.read_historical_assignments(residents)
        r1_tracks = reader.read_r1_tracks()
        r2_tracks = reader.read_r2_tracks()
        base_structure = reader.read_base_schedule_structure()
        staffing_constraints = reader.read_staffing_constraints()
        nf_recs = reader.read_nf_recs()

    # Read preferences from Preferences tab (already imported)
    with ExcelReader(schedule_path) as reader:
        reader.read_preferences_tab(residents)

    # R3-4 Recs override pathway flags
    with ExcelReader(schedule_path) as reader:
        reader.read_r34_recs(residents)

    # Manual research overrides (same as main.py)
    _research_overrides = {
        "Yu, Theresa": 1,
        "Boddu, Priyanka": 1,
        "Hu, Anne": 1,
        "Deshpande, Nikita": 1,
        "Chan, Kaelan": 1,
        "Moushey, Alexander": 1,
        "Sivanushanthan, Shan": 1,
        "Ding, Kevin": 2,
        "Morkos, John": 2,
    }
    name_map = {r.name: r for r in residents}
    for name, months in _research_overrides.items():
        if name in name_map:
            name_map[name].research_months = months

    # Comment-derived overrides (same as main.py)
    apply_comment_overrides(residents)

    # ── Initialize grid ──
    blocks = compute_blocks(year)
    grid = ScheduleGrid(blocks=blocks)

    r1s = [r for r in residents if r.r_year == 1]
    r2s = [r for r in residents if r.r_year == 2]
    r3s = [r for r in residents if r.r_year == 3]
    r4s = [r for r in residents if r.r_year == 4]

    # ── Phase 1: R1 Tracks ──
    assign_r1_tracks(r1s, r1_tracks, grid)

    # ── Phase 2: R2 Tracks ──
    r2_result = assign_r2_tracks(r2s, r2_tracks, grid)

    # ── Phase 3: R3 Fixed ──
    r3_fixed = assign_r3_fixed(r3s, grid, core_exam_block=13)
    airp_assignments = r3_fixed["airp_assignments"]

    # ── Phase 4: R4 Fixed ──
    t32_clinical_blocks = [12, 13]
    r4_fixed_meta = assign_r4_fixed(r4s, grid, t32_clinical_blocks=t32_clinical_blocks, lc_block=12)

    # ── Phase 5: Night Float ──
    nf_rules = NFRules.from_nf_recs(nf_recs) if nf_recs else NFRules()
    nf_result = assign_night_float(
        residents=residents, grid=grid,
        rules=nf_rules,
        airp_assignments=airp_assignments,
        staffing_constraints=staffing_constraints or None,
    )

    # ── Phase 6: R3 Clinical Fill ──
    r3_clinical_meta = fill_r3_clinical(r3s, grid, staffing_constraints=staffing_constraints or None)
    r3_meta = {}
    for res in r3s:
        meta = r3_clinical_meta.get(res.name, {"filled_blocks": {}})
        meta["airp_session"] = airp_assignments.get(res.name, "")
        r3_meta[res.name] = meta

    # ── Phase 7: R4 Clinical Fill ──
    r4_meta = fill_r4_clinical(
        r4s, grid, all_residents=residents, fixed_meta=r4_fixed_meta,
        staffing_constraints=staffing_constraints or None,
        lc_block=12,
    )

    # ── Phase 8: Sampler Resolution ──
    sampler_replacements = resolve_samplers(
        r1s, grid, all_residents=residents,
        staffing_constraints=staffing_constraints or None,
    )

    return (residents, grid, r2_result, r3_meta, r4_meta,
            sampler_replacements, nf_result, staffing_constraints)
