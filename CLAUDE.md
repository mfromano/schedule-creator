# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Schedule Maker automates building the annual radiology residency schedule for ~60 residents (15 per class, R1-R4) across 13 four-week blocks. It reads from two Excel files and produces a completed `.xlsm` schedule workbook.

Input files:
- `Schedule Creation (20XX-20YY).xlsm` — macro-enabled template with roster, historical data, tracks, constraints
- `Schedule Preferences 20XX (Responses).xlsx` — Google Forms survey responses

## Setup & Running

Uses **uv** for package management, requires **Python 3.14**.

```bash
uv sync                        # install dependencies
uv run python main.py build "Schedule Creation (2025-2026).xlsm" "Schedule Preferences 2025 (Responses).xlsx" --dry-run
uv run python main.py build "Schedule Creation (2025-2026).xlsm" "Schedule Preferences 2025 (Responses).xlsx" -o output.xlsm
uv run python main.py validate "Schedule Creation (2025-2026).xlsm"
```

## Architecture

CLI entry point is `main.py` (click-based). The `schedule_maker/` package has five subpackages:

### `models/` — Core data structures
- `resident.py` — `Resident` dataclass (name, r_year, pathway flags, schedule dict, preferences, history)
- `rotation.py` — `HospitalSystem` enum (UCSF/ZSFG/VA/OTHER), `Section` enum, rotation→system/section mappings
- `schedule.py` — `ScheduleGrid` (60×52 assignment matrix), `compute_blocks()` for block↔week mapping
- `constraints.py` — `NFRules` (night float count/spacing constraints by year)

### `io/` — Excel I/O
- `excel_reader.py` — Reads all `.xlsm` tabs: roster, tracks, historical data, R3-4 recs, base schedule structure, NF structure. **Critical**: uses Future PGY (column B) not Current PGY (column A) from Historical tab. Track formulas are derived from base sequence using `pos = ((track-1) + (block-1)*2) % seq_len + 1`.
- `excel_writer.py` — Writes back to `.xlsm` with `keep_vba=True` preserving macros
- `prefs_parser.py` — Parses Google Forms preference `.xlsx` (track rankings, section prefs, AIRP, vacation, no-call dates, FSE, research)

### `phases/` — Pipeline stages (executed in order)
1. `r1_assignment.py` — R1→track (1:1 mapping)
2. `r2_assignment.py` — R2→track via OR-Tools CP-SAT (minimizes rank penalty)
3. `r3_builder.py` — R3 schedules (AIRP, LC, graduation reqs, pathway-specific)
4. `r4_builder.py` — R4 schedules (fixed commitments, grad reqs, fill remaining)
5. `night_float.py` — NF overlay via CP-SAT solver (backwards from high-constraint periods)
6. `sampler.py` — Replace R1 "Msamp" with specific rotations (Pcbi/Mucic/Mir/Mnuc)

### `solver/` — OR-Tools CP-SAT wrappers
- `track_matcher.py` — Assignment problem for R2 tracks
- `nf_solver.py` — Night float placement with spacing/count constraints

### `validation/` — Post-build verification
- `staffing.py` — Per-rotation minimum staffing checks (from Base Schedule rows 101-151)
- `graduation.py` — Cumulative rotation weeks vs graduation requirements
- `hospital_conflict.py` — No two hospital systems in same 4-week block
- `report.py` — Aggregates all validation into a text report

## Key Domain Rules

- **Hospital systems**: UCSF (M-prefix + P-prefix + Peds) vs ZSFG (S-prefix + Z-prefix) vs VA (V-prefix). No resident at two systems in same block.
- **Pathway authority**: R3-4 Recs tab is authoritative for ESIR/ESNR/T32/NRDR flags. Must be loaded AFTER preferences to override self-reported data.
- **NF rules**: R2=2wk Mnf, R3=max 3 total (Mnf+Snf2), R4=2wk Snf2. Min 4-week spacing.
- **NucMed credit**: 4 weeks of Mai/Mch/Peds/Mx = 1 week Mnuc equivalent (non-NRDR only)
- **Track rotation formula**: `position = ((track_num - 1) + (block - 1) * 2) % seq_len + 1`

## Excel / openpyxl Gotchas

- openpyxl `data_only=True` only reads cached values; formula cells may return `None` if Excel hasn't recalculated. Track grid columns are formula-based — derive from base sequence in column C instead.
- Always use `keep_vba=True` when loading `.xlsm` files to preserve macros.
- Never Cut/Paste or Delete rows/columns in the Excel — only Clear Contents (per goals.md).
- Historical tab Column A = Current PGY (prior year), Column B = Future PGY (target year). Always use Column B.
- PCMB (P-prefix) is the same payroll entity as Moffitt (M-prefix) — both map to `HospitalSystem.UCSF`.
- R3-4 Recs is authoritative for pathway flags. `PrefsParser` uses `|=` (additive), so `read_r34_recs` must run AFTER `parse_all` to overwrite with `=`.

## Test Results (2025-2026 data)

- 60 residents (15/class), R2 penalty=6, 0 hospital conflicts, 0 R4 grad deficits
- R1/R2: full 52-week coverage via derived tracks
- NF: 104 weeks across 45 residents
- 65 under-minimum staffing violations (mostly early blocks where R3 schedules are partially filled by design)

## Data Files

The `~$` prefixed Excel files are temporary lock files from having spreadsheets open — do not read or commit them.
