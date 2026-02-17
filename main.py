"""CLI entry point for the radiology residency schedule maker."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from schedule_maker.io.excel_reader import ExcelReader
from schedule_maker.io.excel_writer import ExcelWriter
from schedule_maker.io.prefs_parser import PrefsParser
from schedule_maker.models.schedule import ScheduleGrid, compute_blocks
from schedule_maker.models.constraints import NFRules
from schedule_maker.phases.r1_assignment import assign_r1_tracks
from schedule_maker.phases.r2_assignment import assign_r2_tracks, print_r2_assignment_matrix
from schedule_maker.phases.r3_builder import build_r3_schedules
from schedule_maker.phases.r4_builder import build_r4_schedules
from schedule_maker.phases.night_float import assign_night_float
from schedule_maker.phases.sampler import resolve_samplers
from schedule_maker.validation.report import generate_report


@click.group()
def cli():
    """Radiology residency schedule maker."""
    pass


@cli.command()
@click.argument("schedule_file", type=click.Path(exists=True))
@click.argument("prefs_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output .xlsm file path (default: <input>_output.xlsm)")
@click.option("--year", "-y", type=int, default=None,
              help="Academic year start (e.g. 2025). Auto-detected if not specified.")
@click.option("--dry-run", is_flag=True, help="Validate only, don't write to Excel")
def build(schedule_file: str, prefs_file: str, output: str | None,
          year: int | None, dry_run: bool):
    """Build the full schedule from a .xlsm template and preferences file."""

    schedule_path = Path(schedule_file)
    prefs_path = Path(prefs_file)

    click.echo(f"Reading schedule template: {schedule_path.name}")
    click.echo(f"Reading preferences: {prefs_path.name}")

    # ── Phase 0: Load data ────────────────────────────────────
    with ExcelReader(schedule_path) as reader:
        if year is None:
            year = reader.read_academic_year()
        click.echo(f"Academic year: {year}-{year + 1}")

        rotation_codes = reader.read_rotation_codes()
        click.echo(f"Loaded {len(rotation_codes)} rotation codes")

        residents = reader.read_roster()
        click.echo(f"Loaded {len(residents)} residents")

        # Load historical data
        reader.read_historical_assignments(residents)

        # Load tracks
        r1_tracks = reader.read_r1_tracks()
        r2_tracks = reader.read_r2_tracks()
        click.echo(f"Loaded {len(r1_tracks)} R1 tracks, {len(r2_tracks)} R2 tracks")

        # Load schedule structure
        base_structure = reader.read_base_schedule_structure()

    # Load preferences (before R3-4 Recs so authoritative pathways override)
    click.echo("Parsing preference responses...")
    with PrefsParser(prefs_path) as parser:
        parser.parse_all(residents)

    # Load R3-4 recommendations AFTER preferences — R3-4 Recs is the
    # authoritative source for pathway flags, overriding self-reported prefs
    with ExcelReader(schedule_path) as reader:
        reader.read_r34_recs(residents)

    # ── Initialize schedule grid ──────────────────────────────
    blocks = compute_blocks(year)
    grid = ScheduleGrid(blocks=blocks)

    r1s = [r for r in residents if r.r_year == 1]
    r2s = [r for r in residents if r.r_year == 2]
    r3s = [r for r in residents if r.r_year == 3]
    r4s = [r for r in residents if r.r_year == 4]
    click.echo(f"R1: {len(r1s)}, R2: {len(r2s)}, R3: {len(r3s)}, R4: {len(r4s)}")

    # ── Phase 1: R1 Tracks ────────────────────────────────────
    click.echo("\n--- Phase 1: R1 Track Assignment ---")
    r1_assignments = assign_r1_tracks(r1s, r1_tracks, grid)
    click.echo(f"Assigned {len(r1_assignments)} R1s to tracks")

    # ── Phase 2: R2 Tracks ────────────────────────────────────
    click.echo("\n--- Phase 2: R2 Track Assignment ---")
    click.echo(print_r2_assignment_matrix(r2s, len(r2_tracks)))
    r2_result = assign_r2_tracks(r2s, r2_tracks, grid)
    if r2_result.feasible:
        click.echo(f"Assigned {len(r2_result.assignments)} R2s (total penalty: {r2_result.total_rank_penalty})")
        for name, info in sorted(r2_result.per_resident.items()):
            click.echo(f"  {name}: Track {info['track']} (rank #{info['rank']})")
    else:
        click.echo(f"R2 assignment FAILED: {r2_result.status}")

    # ── Phase 3: R3 Schedules ─────────────────────────────────
    click.echo("\n--- Phase 3: R3 Schedule Building ---")
    r3_meta = build_r3_schedules(r3s, grid)
    for name, meta in sorted(r3_meta.items()):
        click.echo(f"  {name}: AIRP={meta.get('airp_session', '?')}, "
                    f"filled={len(meta.get('filled_blocks', {}))}")

    # ── Phase 4: R4 Schedules ─────────────────────────────────
    click.echo("\n--- Phase 4: R4 Schedule Building ---")
    r4_meta = build_r4_schedules(r4s, grid, all_residents=residents)
    for name, meta in sorted(r4_meta.items()):
        if meta.get("t32_clinical_filled") is not None:
            # T32 resident
            research = meta.get("research_blocks", 0)
            clinical = meta.get("t32_clinical_filled", {})
            click.echo(f"  {name} [T32]: research={research}, clinical={len(clinical)} "
                        f"({', '.join(f'B{b}={c}' for b, c in sorted(clinical.items()))})")
        else:
            fixed = (meta.get("nrdr_mnuc_blocks", 0) + meta.get("esnr_neuro_blocks", 0)
                     + meta.get("esir_mir_blocks", 0) + meta.get("research_blocks", 0)
                     + meta.get("fse_blocks", 0))
            grad_req = len(meta.get("grad_req_filled", {}))
            remaining = len(meta.get("remaining_filled", {}))
            click.echo(f"  {name}: fixed={fixed}, grad_req={grad_req}, fill={remaining}")

    # ── Phase 5: Night Float ──────────────────────────────────
    click.echo("\n--- Phase 5: Night Float Assignment ---")
    nf_result = assign_night_float(
        residents=residents, grid=grid,
        airp_assignments={n: m.get("airp_session", "") for n, m in r3_meta.items()},
    )
    if nf_result.feasible:
        total_nf = sum(len(v) for v in nf_result.assignments.values())
        click.echo(f"Assigned {total_nf} NF weeks across {len(nf_result.assignments)} residents")
    else:
        click.echo(f"NF assignment FAILED: {nf_result.status}")

    # ── Phase 6: Sampler Resolution ───────────────────────────
    click.echo("\n--- Phase 6: Sampler Resolution ---")
    sampler_replacements = resolve_samplers(r1s, grid, all_residents=residents)
    total_replaced = sum(len(v) for v in sampler_replacements.values())
    click.echo(f"Replaced {total_replaced} Msamp weeks across {len(sampler_replacements)} R1s")

    # ── Phase 7: Validation ───────────────────────────────────
    click.echo("\n--- Phase 7: Validation ---")
    report = generate_report(residents, grid)
    click.echo(report)

    # ── Phase 8: Write to Excel ───────────────────────────────
    if not dry_run:
        click.echo(f"\n--- Phase 8: Writing to Excel ---")
        with ExcelWriter(schedule_path, output) as writer:
            writer.set_academic_year(year)

            # Build assignment dicts
            all_assignments = {}
            for res in residents:
                if res.schedule:
                    all_assignments[res.name] = dict(res.schedule)

            nf_assignments = {}
            for name, nf_list in nf_result.assignments.items():
                nf_assignments[name] = {w: code for w, code in nf_list}

            writer.write_base_schedule(
                all_assignments,
                base_structure["resident_rows"],
            )

            # NF writer
            nf_structure = ExcelReader(schedule_path).read_night_float_structure()
            writer.write_night_float(
                nf_assignments,
                nf_structure["resident_rows"],
            )

        click.echo(f"Schedule written to: {output or schedule_path.stem + '_output.xlsm'}")
    else:
        click.echo("\n(Dry run — no Excel output written)")


@cli.command()
@click.argument("schedule_file", type=click.Path(exists=True))
def validate(schedule_file: str):
    """Validate an existing schedule file."""
    with ExcelReader(schedule_file) as reader:
        residents = reader.read_roster()
        reader.read_historical_assignments(residents)
        reader.read_r34_recs(residents)

    grid = ScheduleGrid()
    for res in residents:
        for w, code in res.schedule.items():
            grid.assign(res.name, w, code)

    report = generate_report(residents, grid)
    click.echo(report)


if __name__ == "__main__":
    cli()
