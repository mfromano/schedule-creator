# Schedule Maker

Automates building the annual UCSF radiology residency schedule for ~60 residents (15 per class, R1–R4) across 13 four-week blocks. Reads from two Excel files and produces a completed `.xlsm` schedule workbook.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

```bash
uv sync
```

## Usage

### Build a schedule

```bash
uv run python main.py build "Schedule Creation (2025-2026).xlsm" "Schedule Preferences 2025 (Responses).xlsx" --dry-run
uv run python main.py build "Schedule Creation (2025-2026).xlsm" "Schedule Preferences 2025 (Responses).xlsx" -o output.xlsm
```

Options:
- `--dry-run` — run the full pipeline and validate without writing output
- `-o / --output` — output file path (default: `<input>_output.xlsm`)
- `-y / --year` — academic year start (auto-detected if omitted)

### Validate an existing schedule

```bash
uv run python main.py validate "Schedule Creation (2025-2026).xlsm"
```

## Input Files

| File | Description |
|------|-------------|
| `Schedule Creation (20XX-20YY).xlsm` | Macro-enabled template with roster, historical data, tracks, and constraints |
| `Schedule Preferences 20XX (Responses).xlsx` | Google Forms survey responses (track rankings, section prefs, vacation, no-call dates, etc.) |

## Project Structure

```
schedule_maker/
├── main.py                          # CLI entry point (click-based)
├── schedule_maker/
│   ├── models/                      # Core data structures
│   │   ├── resident.py              #   Resident dataclass
│   │   ├── rotation.py              #   HospitalSystem, Section enums, rotation mappings
│   │   ├── schedule.py              #   ScheduleGrid (60×52 matrix), block/week mapping
│   │   └── constraints.py           #   NFRules (night float count/spacing)
│   ├── io/                          # Excel I/O
│   │   ├── excel_reader.py          #   Reads all .xlsm tabs
│   │   ├── excel_writer.py          #   Writes back to .xlsm (preserves macros)
│   │   └── prefs_parser.py          #   Parses Google Forms preference responses
│   ├── phases/                      # Pipeline stages (executed in order)
│   │   ├── r1_assignment.py         #   1. R1 → track (1:1 mapping)
│   │   ├── r2_assignment.py         #   2. R2 → track via CP-SAT (minimize rank penalty)
│   │   ├── r3_builder.py            #   3. R3 schedules (AIRP, LC, pathways, grad reqs)
│   │   ├── r4_builder.py            #   4. R4 schedules (fixed commitments, grad reqs, fill)
│   │   ├── night_float.py           #   5. NF overlay via CP-SAT solver
│   │   └── sampler.py               #   6. Replace R1 "Msamp" with specific rotations
│   ├── solver/                      # OR-Tools CP-SAT wrappers
│   │   ├── track_matcher.py         #   Assignment problem for R2 tracks
│   │   └── nf_solver.py             #   Night float placement with spacing constraints
│   └── validation/                  # Post-build verification
│       ├── staffing.py              #   Per-rotation minimum staffing checks
│       ├── graduation.py            #   Cumulative weeks vs graduation requirements
│       ├── hospital_conflict.py     #   No two hospital systems in same block
│       └── report.py                #   Aggregates all checks into a text report
└── tests/
    ├── generate_dummy_prefs.py      # Generate test preference data
    └── *.xlsm / *.xlsx              # Test fixtures
```

## Pipeline

The build command runs these phases in order:

1. **Data loading** — roster, historical assignments, tracks, preferences, R3-4 recs
2. **R1 track assignment** — 1:1 mapping of R1 residents to tracks
3. **R2 track assignment** — OR-Tools CP-SAT solver minimizes total rank penalty
4. **R3 schedule building** — AIRP, Learning Center, CORE, pathway-specific rotations, graduation requirements
5. **R4 schedule building** — fixed commitments (NRDR/ESIR/ESNR/T32), FSEs, graduation requirements, remaining fill
6. **Night float assignment** — CP-SAT solver with spacing/count constraints, works backwards from high-constraint periods
7. **Sampler resolution** — replaces generic R1 "Msamp" blocks with specific rotations (Pcbi/Mucic/Mir/Mnuc)
8. **Validation** — staffing minimums, graduation requirements, hospital conflicts
9. **Excel write** — writes Base Schedule and Night Float tabs back to `.xlsm`

## Key Dependencies

- [openpyxl](https://openpyxl.readthedocs.io/) — Excel read/write with macro preservation
- [OR-Tools](https://developers.google.com/optimization) — CP-SAT constraint solver for track matching and night float placement
- [click](https://click.palletsprojects.com/) — CLI framework
- [pandas](https://pandas.pydata.org/) — data manipulation for preference parsing
