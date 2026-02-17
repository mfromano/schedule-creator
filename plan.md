│ Plan to implement                                                                                         │
│                                                                                                           │
│ Plan: Radiology Resident Schedule Maker                                                                   │
│                                                                                                           │
│ Context                                                                                                   │
│                                                                                                           │
│ The rotation chief needs to build the 2026-2027 academic year schedule for ~60 radiology residents (15    │
│ per class, R1-R4) across 13 blocks of 4 weeks each. The Schedule Creation (2026-2027).xlsm file has all   │
│ infrastructure (roster, historical data, track templates, staffing constraints) but the Base Schedule and │
│  Night Float tabs are completely empty. A new preferences spreadsheet (Google Forms responses) will       │
│ provide resident preferences.                                                                             │
│                                                                                                           │
│ The scheduling process defined in goals.md is strictly phased and mixes hard constraints (staffing        │
│ minimums, graduation requirements, hospital system conflicts) with subjective judgment calls (intermixing │
│  hard/easy rotations, FSE placement, Mx allocation). This calls for a semi-automated approach: solvers    │
│ handle optimization, humans handle judgment.                                                              │
│                                                                                                           │
│ Key finding: The 2026-2027 file's Overview tab still shows target AY = 2025. Cell B6 needs to be set to   │
│ 2026 to shift all date computations to AY 2026-2027 — the code will handle this automatically.            │
│                                                                                                           │
│ Preferences status: The new 2026-2027 preferences spreadsheet is not yet available. We'll build the       │
│ system using the 2025 responses file as a structural reference, so it works with any future preferences   │
│ file that follows the same Google Forms schema.                                                           │
│                                                                                                           │
│ ---                                                                                                       │
│ Architecture: Modular Pipeline with Jupyter Notebooks                                                     │
│                                                                                                           │
│ schedule_maker/                                                                                           │
│ ├── models/                                                                                               │
│ │   ├── resident.py        # Resident dataclass (name, year, pathway, preferences, history)               │
│ │   ├── rotation.py        # Rotation codes, hospital system mapping, section mapping                     │
│ │   ├── schedule.py        # Schedule grid (60 residents x 52 weeks) + state management                   │
│ │   └── constraints.py     # Staffing mins, graduation reqs, NF rules                                     │
│ ├── io/                                                                                                   │
│ │   ├── excel_reader.py    # Read .xlsm tabs (Key, Historical, Tracks, Preferences, etc.)                 │
│ │   ├── excel_writer.py    # Write back to .xlsm preserving VBA/formulas                                  │
│ │   └── prefs_parser.py    # Parse Google Forms preference .xlsx into Resident models                     │
│ ├── phases/                                                                                               │
│ │   ├── r1_assignment.py   # Phase 1: R1 track assignment (simple 1:1)                                    │
│ │   ├── r2_assignment.py   # Phase 2: R2 track assignment (solver-optimized)                              │
│ │   ├── r3_builder.py      # Phase 3: R3 schedule (AIRP + requirement placement)                          │
│ │   ├── r4_builder.py      # Phase 4: R4 schedule (grad reqs + FSE + research)                            │
│ │   ├── night_float.py     # Phase 5: NF overlay (backwards from constraints)                             │
│ │   └── sampler.py         # Phase 6: Replace Msamp with specific rotations                               │
│ ├── solver/                                                                                               │
│ │   ├── track_matcher.py   # OR-Tools CP-SAT for R2 track optimization                                    │
│ │   └── nf_solver.py       # OR-Tools CP-SAT for NF placement                                             │
│ ├── validation/                                                                                           │
│ │   ├── staffing.py        # Per-week staffing min/max checks                                             │
│ │   ├── graduation.py      # Cumulative graduation requirement verification                               │
│ │   ├── hospital_conflict.py # No two hospital systems in same block                                      │
│ │   └── report.py          # Generate validation summary                                                  │
│ ├── notebooks/                                                                                            │
│ │   ├── 01_data_load.ipynb                                                                                │
│ │   ├── 02_r1_r2_tracks.ipynb                                                                             │
│ │   ├── 03_r3_schedule.ipynb                                                                              │
│ │   ├── 04_r4_schedule.ipynb                                                                              │
│ │   ├── 05_night_float.ipynb                                                                              │
│ │   └── 06_sampler_verify.ipynb                                                                           │
│ └── main.py                # CLI entry point for batch validation                                         │
│                                                                                                           │
│                                                                                                           │
│ Dependencies: openpyxl, pandas, ortools (Google OR-Tools CP-SAT solver)                                   │
│                                                                                                           │
│ ---                                                                                                       │
│ Phase-by-Phase Strategy                                                                                   │
│                                                                                                           │
│ Phase 1: Data Layer (models/ + io/)                                                                       │
│                                                                                                           │
│ - Parse Key tab → rotation code dictionary with site prefix, section, PGY eligibility                     │
│ - Parse Historical tab → resident roster (75 residents, 60 active) with 4 years of weekly schedule        │
│ history                                                                                                   │
│ - Parse Historical Tabulation → cumulative rotation weeks per resident per section                        │
│ - Parse R1 Tracks / R2 Tracks → 15 track templates each (26 biweekly slots → 52 weeks)                    │
│ - Parse Preferences tab → section deficiencies, pathway flags (ESNR/ESIR/T32/NRDR)                        │
│ - Parse R3-4 Recs → graduation gap analysis per resident                                                  │
│ - Parse Base Schedule rows 101-151 → staffing constraint matrix                                           │
│ - Parse preferences .xlsx → per-resident preferences (track rankings, section top/bottom, AIRP rankings,  │
│ no-call dates, vacation, FSE, research/CEP). Built against the 2025 file schema; will work with any       │
│ future file following the same Google Forms structure.                                                    │
│ - Hospital system mapping: M-prefix=Moffitt, Z-prefix=Zuckerberg, S-prefix=SFGH, V-prefix=VA,             │
│ P-prefix=PCMB                                                                                             │
│ - Programmatically set Overview cell B6 to 2026 to configure the target academic year                     │
│                                                                                                           │
│ Phase 2: R1 Track Assignment (automated)                                                                  │
│                                                                                                           │
│ - 15 incoming R1s → 15 pre-defined R1 tracks (1:1 mapping)                                                │
│ - Assignment is arbitrary per goals.md, but can optimize by matching sampler preferences to sections with │
│  trainee shortages                                                                                        │
│ - Each track is a fixed 52-week rotation sequence read from the R1 Tracks tab                             │
│ - Output: 15 rows written to schedule grid                                                                │
│                                                                                                           │
│ Phase 3: R2 Track Assignment (solver-optimized)                                                           │
│                                                                                                           │
│ - 15 rising R2s → 15 pre-defined R2 tracks based on ranked preferences                                    │
│ - OR-Tools CP-SAT assignment problem: minimize total rank penalty (rank 1=0, rank 15=14)                  │
│ - Hard constraints: 1 resident per track, 1 track per resident                                            │
│ - Soft constraints: ESIR track compatibility, Historical Tabulation deficiency coverage                   │
│ - Present assignment with satisfaction scores; allow manual overrides                                     │
│ - Output: 15 rows written to schedule grid                                                                │
│                                                                                                           │
│ Phase 4: R3 Schedule Builder (semi-automated)                                                             │
│                                                                                                           │
│ Most complex phase. 15 rising R3s get individualized schedules.                                           │
│                                                                                                           │
│ Step 4a — AIRP assignment (solver): 15 R3s × 5 AIRP sessions, max 3-4 per session. CP-SAT optimizes based │
│  on ranked session preferences. Lock AIRP blocks first.                                                   │
│                                                                                                           │
│ Step 4b — LC placement: All R3s get LC in the last full block before CORE exam. Lock these.               │
│                                                                                                           │
│ Step 4c — Graduation requirement placement (solver + review):                                             │
│ - For each R3, use R3-4 Recs to identify required blocks (Vnuc, Smr, Ser, Sbi, Mnuc, Pcbi, Mch, Mai, Mus, │
│  Mb, Mucic, Peds, Zir)                                                                                    │
│ - Place required rotations respecting: hospital system constraint (no Moffitt+SFGH in same block),        │
│ top/bottom section preferences, Zir block preferences, no Zir before LC                                   │
│ - NRDR residents: 6 blocks Mnuc; T32/ESIR/ESNR: complete NM/breast by EOY if possible                     │
│ - Present candidate schedule with staffing heatmap for human review                                       │
│                                                                                                           │
│ Phase 5: R4 Schedule Builder (semi-automated)                                                             │
│                                                                                                           │
│ 15 rising R4s, highly individualized.                                                                     │
│                                                                                                           │
│ Step 5a — Place fixed commitments: Research/CEP blocks (from preferences), FSE blocks (contiguous, breast │
│  FSE requires 6 months), NRDR Mnuc blocks (6 blocks), ESIR Mir blocks, ESNR neuro blocks (6 blocks)       │
│                                                                                                           │
│ Step 5b — Graduation requirements: Fill remaining deficiencies from R3-4 Recs. Breast-deficient → Pcbi.   │
│ NucMed-deficient → Mnuc (or Mai/Mch/Peds/Mx for partial credit at 4:1 ratio)                              │
│                                                                                                           │
│ Step 5c — Fill remaining capacity: Mx blocks (all R4s except T32 or dual-pathway), Peds if only 1 block   │
│ completed, MSK to reach 3 blocks total. Fill based on weekly staffing needs.                              │
│                                                                                                           │
│ Step 5d — Human review: Present schedule + staffing levels. Highlight under-staffed weeks (especially     │
│ LC/RSNA periods). Allow manual adjustments.                                                               │
│                                                                                                           │
│ Phase 6: Night Float Overlay (solver + human review)                                                      │
│                                                                                                           │
│ Build backwards from high-constraint periods per goals.md:                                                │
│                                                                                                           │
│ 1. LC/CORE blocks: R2 Mnf + R4 Snf2 only                                                                  │
│ 2. Post-CORE blocks: R2-3 Mnf + R3 Snf2                                                                   │
│ 3. Block 1: R3 Mnf only (longer shifts to ease R2 integration)                                            │
│ 4. AIRP blocks: Avoid affected R3s                                                                        │
│ 5. Remaining weeks: Fill with CP-SAT solver                                                               │
│                                                                                                           │
│ NF counts: R2=2wk Mnf (+ Snf already in track), R3=max 3 total (Mnf+Snf2), R4=2wk Snf2. Min 4-week        │
│ spacing. Respect no-call preferences (red cells in NF tab).                                               │
│                                                                                                           │
│ Excel mechanics: R2 Snf is already in Base Schedule via tracks. All other NF codes (Mnf, Snf2) are        │
│ written to the Night Float tab by replacing formula cells with literal strings.                           │
│                                                                                                           │
│ Pull NF residents preferably from: Pcmb, Mb, Mucic, Peds, Mnuc (per goals.md).                            │
│                                                                                                           │
│ Phase 7: Sampler Resolution (rule-based)                                                                  │
│                                                                                                           │
│ Replace R1 "Msamp" blocks with: Pcbi (1wk), Mucic or Mir (1wk), Mnuc (2wk). Order determined by NF        │
│ schedule — the R1 sampler fills in for whichever upper-level is on NF that week.                          │
│                                                                                                           │
│ Phase 8: Validation & Write-Back                                                                          │
│                                                                                                           │
│ 1. Staffing: Check all 52 weeks against constraint matrix (rows 101-151). Flag under/over-staffed.        │
│ 2. Graduation: Sum historical + current year rotation weeks vs requirements for all seniors (and T32      │
│ juniors).                                                                                                 │
│ 3. Hospital conflicts: Verify no resident has two hospital systems in same 4-week block.                  │
│ 4. NF rules: Verify spacing, counts, distribution.                                                        │
│ 5. Write to Excel: openpyxl.load_workbook(keep_vba=True), write Base Schedule rows 6-65 cols D-BC, write  │
│ NF overlay, save as .xlsm. Always write to a copy first.                                                  │
│                                                                                                           │
│ ---                                                                                                       │
│ Key Technical Decisions                                                                                   │
│                                                                                                           │
│ Decision: Solver                                                                                          │
│ Choice: OR-Tools CP-SAT                                                                                   │
│ Rationale: Best free constraint programming solver; handles assignment + hard/soft constraints natively   │
│ ────────────────────────────────────────                                                                  │
│ Decision: Excel I/O                                                                                       │
│ Choice: openpyxl with keep_vba=True                                                                       │
│ Rationale: Only Python library that preserves .xlsm macros and VBA                                        │
│ ────────────────────────────────────────                                                                  │
│ Decision: Interface                                                                                       │
│ Choice: Jupyter notebooks                                                                                 │
│ Rationale: Iterative workflow with visual inspection between phases; DataFrames render naturally          │
│ ────────────────────────────────────────                                                                  │
│ Decision: Automation level                                                                                │
│ Choice: Semi-automated                                                                                    │
│ Rationale: goals.md requires judgment calls; solver proposes, human reviews/adjusts                       │
│                                                                                                           │
│ ---                                                                                                       │
│ Risk Mitigation                                                                                           │
│                                                                                                           │
│ - Excel formula corruption: Always write to a backup copy. Test with 1 row first. Only write to data      │
│ cells, never formula/constraint rows.                                                                     │
│ - Messy preference data: Build robust date parsing with dateutil. Log all unparseable entries for manual  │
│ review.                                                                                                   │
│ - Infeasible constraints: CP-SAT detects infeasibility. Relax soft constraints (preferences) first.       │
│ Report which constraints are binding.                                                                     │
│ - NF formula replacement: Cache original formula templates to enable "reset NF" function.                 │
│                                                                                                           │
│ ---                                                                                                       │
│ Verification Plan                                                                                         │
│                                                                                                           │
│ 1. After each phase, run the validation suite and inspect staffing heatmaps in the notebook               │
│ 2. After full schedule is written, open .xlsm in Excel and verify:                                        │
│   - "Current Year Tabulation" tab auto-computes correct rotation counts                                   │
│   - "Night Float" tab coverage rows (104-118) show green (within staffing bounds)                         │
│   - No Excel formula errors (#REF!, #NAME?)                                                               │
│ 3. Run the spreadsheet's built-in "Schedule_Publish" macro to verify it generates cleanly                 │
│ 4. Cross-reference a few residents manually against graduation requirements                               │
│                                                                                                           │
│ ---                                                                                                       │
│ Files to Create/Modify                                                                                    │
│                                                                                                           │
│ - pyproject.toml — add dependencies: openpyxl, pandas, ortools, jupyter, click                            │
│ - main.py — expand into CLI orchestrator                                                                  │
│ - All files under schedule_maker/ (new package)                                                           │
│ - All notebooks under notebooks/ (new)                                                                    │
│ - CLAUDE.md — update with new architecture info   