Update the scheduling constraints documentation by reading all constraint-bearing source files and rewriting both docs.

## Steps

1. Read all of these source files to extract current constraint values and logic:
   - `schedule_maker/models/constraints.py`
   - `schedule_maker/models/rotation.py`
   - `schedule_maker/models/resident.py`
   - `schedule_maker/phases/r1_assignment.py`
   - `schedule_maker/phases/r2_assignment.py`
   - `schedule_maker/phases/r3_builder.py`
   - `schedule_maker/phases/r4_builder.py`
   - `schedule_maker/phases/night_float.py`
   - `schedule_maker/phases/sampler.py`
   - `schedule_maker/solver/nf_solver.py`
   - `schedule_maker/solver/track_matcher.py`
   - `schedule_maker/validation/staffing.py`
   - `schedule_maker/validation/graduation.py`
   - `schedule_maker/validation/hospital_conflict.py`
   - `schedule_maker/staffing_utils.py`
   - `main.py`

2. Also read the domain rules reference:
   - `.claude/rules/goals.md`
   - `.claude/rules/resident_comments.md`

3. Rewrite `.claude/rules/constraints.md` — the **technical** constraints reference:
   - Include exact values, code references (file:function), rotation codes, solver parameters
   - Organized by numbered sections matching the current structure
   - Update any values that have changed in the code since the last version

4. Rewrite `CONSTRAINTS.md` (top-level) — the **layman-friendly** constraints guide:
   - No code references, no file paths, no function names
   - Explain rotation code abbreviations in parentheses on first use
   - Written so a rotation chief or program director can understand it
   - Organized by topic: Graduation, Hospital Rules, Staffing, Tracks, Night Float, etc.

5. Report a summary of what changed in each file (new sections, updated values, removed items).
