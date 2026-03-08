# Scheduling Constraints Reference

Comprehensive reference of all constraints implemented in the codebase.

---

## 1. Graduation Requirements (`constraints.py`, `graduation.py`)

| Pathway | Requirement | Weeks | Qualifying Rotations | Notes |
|---------|-------------|-------|---------------------|-------|
| All | Breast Imaging | 12 | Pcbi, Sbi | + 300 cases (tracked externally via BreastTrak) |
| Non-NRDR | Nuclear Medicine | 16 | Mnuc, Vnuc | 4:1 partial credit from Mai, Mch, Mch2, Peds, Mx (0.25 wk NM per 1 wk rotation) |
| NRDR | Nuclear Medicine | 48 | Mnuc, Vnuc | NO partial credit; R4 research weeks count toward requirement |
| ESIR | IR | 12 | Mir, Zir, Sir, Vir | Typical: R1=0, R2=Vir/Sir(2), R3=Zir/Mir(2), R4=Mir x8 |
| ESNR | Neuro (R4) | 24 | Mucic, Smr | 6 blocks, max 1 on Smr |

**ESNR Neuro Exempt**: `{"Anderies, Barrett"}` (`graduation.py:ESNR_NEURO_EXEMPT`, `r4_builder.py:ESNR_NEURO_EXEMPT`) — skips ESNR neuro graduation check and R4 neuro block placement.

## 2. Nuclear Medicine Partial Credit (`rotation.py`)

- **Eligible rotations**: Mai, Mch, Mch2, Peds, Mx (`NM_PARTIAL_CREDIT_ROTATIONS`)
- **Ratio**: 0.25 (`NM_PARTIAL_RATIO`) -- 4 weeks rotation = 1 week NM credit
- **NO credit from**: Mc, Mmr (`NM_NO_CREDIT`)
- **NRDR exclusion**: partial credit does NOT apply to NRDR residents
- **Note**: `STANDARD_GRAD_REQS` only lists {Mai, Mch, Peds, Mx} as partial_credit_rotations (missing Mch2); the standalone constant `NM_PARTIAL_CREDIT_ROTATIONS` includes Mch2

## 3. Hospital System Mapping (`rotation.py`)

| Prefix | System | Examples |
|--------|--------|---------|
| M | UCSF | Mai, Mb, Mch, Mucic, Mnuc, Mnf, Mx, Mir, Mus |
| P | UCSF | Pcbi, Peds (same payroll entity as Moffitt) |
| S | ZSFG | Ser, Smr, Sbi, Sir, Sx, Snf, Snf2, Sus, Snct |
| Z | UCSF | Zai, Zir (Zion campus -- same UCSF payroll entity) |
| V | VA | Vb, Vir |

Special cases (`get_hospital_system`):
- `Peds` -> UCSF (hardcoded override, not prefix-based)
- `FSE-*` -> UCSF (all FSEs mapped to Moffitt sites)
- Non-matching prefixes -> OTHER (no conflict)

## 4. Hospital Conflict Check (`hospital_conflict.py`)

- **Granularity**: Biweek-level (weeks 1-2 and weeks 3-4 checked separately within each block)
- **Rule**: No two different hospital systems (UCSF/ZSFG/VA) in the same biweek
- **Exempt residents**: `Ding, Kevin` (`r4_builder.py` HOSPITAL_CONFLICT_EXEMPT)
- **OTHER system**: ignored in conflict checks (Res, CEP, AIRP, LC, CORE, etc.)

## 5. Staffing Minimums (`staffing.py` ROTATION_MINIMUMS)

| Label | Rotation Codes | Minimum |
|-------|---------------|---------|
| Moffitt AI | Mai, Zai | 3 |
| Moffitt US | Mus | 2 |
| Moffitt Cardiothoracic | Mch, Mch2, Mc | 2 |
| Peds | Peds | 1 |
| Moffitt Neuro | Mucic, Mnct | 3 |
| Moffitt Bone | Mb | 1 |
| Moffitt Nucs | Mnuc | 2 |
| PCMB Breast | Pcbi | 1 |
| ZSFG Total | Ser, Smr, Sbi, Sir, Sus, Sai, Snct, Sch, Sch2, Sx, SSamplerCh2 | 8 |
| VA MSK/Nucs | Vb | 1 |
| Mucic | Mucic | 1 |
| Zir | Zir | 1 |

Dynamic constraints from Base Schedule rows 101-151 override these when loaded.

## 6. Staffing Maximums (`staffing.py` ROTATION_MAXIMUMS)

| Label | Rotation Codes | Maximum |
|-------|---------------|---------|
| Sx | Sx | 1 |
| Snf | Snf | 1 |
| Mnf | Mnf | 1 |
| Snf2 | Snf2 | 1 |
| PCMB Breast | Pcbi | 3 |
| NucMed Total | Mnuc | 5 |
| VA MSK | Vb | 1 |
| VA IR | Vir | 1 |
| Zir | Zir | 1 |
| Ser | Ser | 2 |
| Mai | Mai | 5 |
| Mucic | Mucic | 6 |

FSE codes are mapped to base codes for max checks (e.g., FSE-Bre counts against Pcbi cap). Default max for unlisted rotations: 6 (`staffing_utils.py:block_exceeds_max`).

## 7. Rotation Year Eligibility (`staffing_utils.py`)

| Rotation | Eligible Years | Notes |
|----------|---------------|-------|
| Vir | R2 only | |
| Sir | R2 only | |
| Zir | R3, R4 | R4 only if ESIR or IR FSE |
| Zai | R2 only | |
| Mnct | R1 only | |
| Vnuc | none | Retired rotation, never assign |

## 8. R1 Assignment (`r1_assignment.py`)

- 1:1 track mapping (rotation chief assigns tracks)
- Wraps around if more residents than tracks (duplicate schedules expected)
- Msamp blocks left generic until Phase 8 (sampler resolution)

## 9. R2 Track Assignment (`track_matcher.py`, `r2_assignment.py`)

### Solver (CP-SAT)
- **Objective**: Minimize total rank penalty (rank 1 = 0 penalty, rank N = N-1)
- **Each resident**: exactly 1 track
- **Max per track**: ceil(n / num_tracks) -- allows sharing when n > tracks
- **Min per track**: 1 when n > num_tracks (minimizes duplicates for Sx/Snf deconfliction)
- **Unranked penalty**: num_tracks (worst possible)
- **Optional max_rank**: hard limit on worst allowed rank
- **Time limit**: 30 seconds

### Sx/Snf Deconfliction (`r2_assignment.py`)
- **Standard pattern**: [Sx, Snf, Snf, Sx] (4-week group)
- **Max 1 per code per week**: Sx and Snf tracked independently
- **Swappable rotations**: Pcbi, Mb, Mucic, Peds, Mnuc, Mai, Mch (displaced when Sx/Snf moves)
- **Free-track pool**: unassigned tracks' Sx/Snf positions used as priority targets (bonus 100 per match)
- **Two passes**: (1) same-track deconfliction, (2) cross-track deconfliction
- **Spacing**: prefers 4-week min between Sx/Snf groups; relaxes to 0 if needed
- **Max iterations**: 50 for cross-track deconfliction safety limit

## 10. R3 Builder (`r3_builder.py`)

### AIRP
- **Max per session**: 4 (`MAX_PER_AIRP_SESSION`)
- **Scoring**: rank weight = 10 (`AIRP_RANK_WEIGHT`), groupmate bonus = 8 (`AIRP_GROUPMATE_BONUS`)
- **Fallback**: if no preferred session available, assign to least-full session
- **Name resolution**: supports first name, "First Last", "Last, First" formats for group requests

### Learning Center
- Assigned to all R3s in the last full block before CORE exam (or specific weeks via --lc-weeks)

### CORE
- Assigned to specific weeks via --core-weeks for all R3s

### Zir Caps
- **R3**: max 1 block Zir
- **No Zir** in or after the block before LC (block >= lc_block - 1)
- Zir block preferences: soft bonus (+2.0) for preferred blocks

### NRDR R3
- 6 blocks Mnuc inserted at priority (before other rotations)

### Fill Logic (`_fill_r3_requirements`, `_fill_r3_remaining`)
- Rotation-first iteration: for each needed rotation, find best available block
- Staffing-aware scoring: blocks with highest deficit preferred (via `get_staffing_need`)
- Hospital conflict check at block level
- Section preferences influence rotation ordering
- Run penalty weight: 3.0 (`_RUN_PENALTY_WEIGHT`) — discourages consecutive same-rotation blocks (except NRDR Mnuc)
- Schedule weight bonus: front-heavy (+1.0 if block <= 6, -0.5 if block >= 10), back-heavy (+1.0 if block >= 8, -0.5 if block <= 4)
- Remaining blocks filled via `rank_rotations_by_combined_score` with staffing_weight=2, pref_weight=3
- No IR rotations (Zir, Vir, Sir) on blocks that already have NF assigned (`block_has_nf`)

## 11. R4 Builder (`r4_builder.py`)

### Research/CEP Placement
- **Authoritative source**: `.claude/rules/cep.md` lists all approved CEP/Research blocks for the year. Residents not listed get zero blocks. Parsed by `cep_parser.py`, which zeroes all R4 CEP/Research counts then applies only listed approvals.
- Avoid blocks 5-7 (RSNA/LC area)
- Preferred blocks: 3, 4, 8, 9, 10, 11, 2, 12
- Max 2 months research/CEP unless supplementary funding
- Block requests from comments honored first (e.g. CEP in specific block)

### NRDR R4
- 6 blocks Mnuc (fixed commitment)

### ESIR R4
- 8 blocks Mir (fixed commitment)

### ESNR R4
- 6 blocks neuro total, max 1 on Smr (rest on Mucic)
- **Exempt**: `ESNR_NEURO_EXEMPT = {"Anderies, Barrett"}` — skips ESNR neuro placement

### FSE Rules
- Breast FSE: 6 months (no exception)
- Other FSE: 2 blocks typical
- ALL FSE specialties processed (not just first)
- FSE codes mapped via `_fse_to_rotation_code` using `SECTION_TO_ROTATION_CODES` + `_FSE_NAME_ALIASES` for full form names (e.g. "Abdominal Imaging" -> "AI" -> "Mai", "Interventional Radiology" -> "IR" -> "Mir")
- Hospital conflict exempt residents can skip conflict check for FSE rotations

### _FSE_NAME_ALIASES
- "abdominal imaging" -> "AI"
- "interventional radiology" -> "IR"
- "neuroradiology" -> "Neuro"
- "nuclear medicine" -> "NucMed"
- "musculoskeletal" -> "MSK"
- "chest/cardiac" -> "Chest"
- "breast imaging" -> "Breast"
- "ultrasound" -> "US"
- "pediatrics" -> "Peds"

### Mx Rules
- All R4s get Mx blocks except T32 or dual-pathway residents
- Count from recommended_blocks["Mx"], default 1

### R4 Zir Eligibility (`_r4_zir_eligible`)
- Only ESIR or IR FSE residents (never T32)
- Only in blocks >= lc_block - 1

### Pathway/FSE Organization Preference
- "contiguous" (sequential) or "interspersed" (interrupted) block placement
- Weight: 0.3 (`_ORG_PREF_WEIGHT`, lowest of all soft constraints)
- Applies to NRDR Mnuc, ESIR Mir, and FSE block placement

### Fill Scoring (`_fill_remaining`)
- Combined score: staffing_weight(2) * need + pref_weight(3) * preference
- FSE rotation codes boosted to pref_weight=5 and max score=3
- Schedule weight bonus applied during grad requirement fill
- No IR rotations on blocks that already have NF assigned (`block_has_nf`)

## 12. T32 Rules (`r4_builder.py`)

- Research for entire year except clinical coverage blocks
- Clinical blocks: typically blocks 12-13, derived from --lc-weeks/--core-weeks
- Clinical blocks filled with: breast deficit first, then graduation requirements, then staffing needs
- No Zir for T32 residents
- Max 2 months clinical pull (from goals.md)

## 13. Night Float Rules (`constraints.py` NFRules)

### Shift Counts
| Year | Shift | Count | Notes |
|------|-------|-------|-------|
| R2 | Mnf | 2 weeks | Snf already in track |
| R3 | Mnf+Snf2 | max 3 total | Mnf <= 2, Snf2 <= 2, min 1 NF week |
| R4 | Snf2 | 2 weeks | Mnf normally 0 (overridable via NF Recs) |

### Shift Eligibility
| Shift | Eligible Years |
|-------|---------------|
| Snf | R2 (in track) |
| Mnf | R2, R3 |
| Snf2 | R3, R4 |
| Sx | R2 (in track) |

### Spacing
- Minimum 4-week spacing between NF assignments for same resident

### NF Pull Preferences
- Prefer pulling from: Pcmb, Mb, Mucic, Peds, Mnuc, Pcbi
- Pull bonus: +10 for preferred rotations, -5 penalty for others

### NF Recs Override
- `NFRules.from_nf_recs()` parses NF Recs tab data (PGY-3/4/5 rows)
- Columns: mnf_1wk, mnf_2wk, snf2_1wk, snf2_2wk counts
- Stores raw census as `r2_mnf_census`, `r3_mnf_census`, `r3_snf2_census`, `r4_snf2_census` tuples of (count_1wk, count_2wk)
- **Critical**: `from_nf_recs()` must NOT store class totals in per-resident fields (`r2_mnf_weeks`, `r3_max_nf`, `r3_mnf_max`, `r3_snf2_max`, `r4_snf2_weeks`). Those fields are per-resident limits used only in fallback mode. Census data drives solver distribution constraints instead.
- Census data used by solver for aggregate class-level distribution constraints
- Always loaded in single-step build mode (not gated by `prefs_path`)

## 14. NF Solver (`nf_solver.py`)

### Hard Constraints
1. **Per-week exclusivity**: max 1 Mnf and 1 Snf2 across all residents per week
2. **No double-assignment**: can't have both Mnf and Snf2 same resident same week
3. **Eligibility**: R2 -> Mnf only (Snf2 forbidden), R4 -> Snf2 only (when r4_mnf_weeks=0), R3 -> both
4. **No NF adjacent to existing Sx/Mnf/Snf2** in base schedule (Snf excluded -- paired with Sx by design)
5. **No Mnf during Vb**: hard constraint
6. **No NF (Mnf or Snf2) during IR rotations (Zir, Vir, Sir)**: hard constraint
7. **No NF on existing Sx/Snf weeks**: hard constraint (prevents stacking solver NF on top of track-assigned call/NF)
8. **No NF for R4 on CEP/Research weeks**: forbid both Mnf and Snf2 when R4 has CEP or Res in base schedule
9. **Staffing hard constraint**: forbid NF if pulling would drop rotation below minimum staffing (current < min_req)
10. **Locked assignments**: pre-assigned NF must be respected
11. **Total NF counts**: R2/R3/R4 use census-based distribution when available (see below); fallback to per-resident limits (R2 Mnf == r2_mnf_weeks, R3 total <= r3_max_nf >= 1, R4 Snf2 == r4_snf2_weeks)
12. **Census-based R2 distribution** (when `r2_mnf_census` nonzero): each R2 gets either 2-Mnf or 1-Mnf via boolean var; aggregate count of 2-Mnf residents == `r2_mnf_census[1]`
13. **Census-based R3 distribution** (when `r3_mnf_census` nonzero): each R3 is assigned to either 2-Mnf/1-Snf2 or 1-Mnf/2-Snf2 pattern via boolean var; aggregate count of 2-Mnf residents == `r3_mnf_census[1]`
14. **Census-based R4 distribution** (when `r4_snf2_census` nonzero): each R4 gets either 2-Snf2 or 1-Snf2 via boolean var; aggregate count of 2-Snf2 residents == `r4_snf2_census[1]`

### Soft Constraints (Objective Penalties)
| Penalty | Weight | Trigger |
|---------|--------|---------|
| No-call weeks | 20 (`no_call_penalty_weight`) | NF assigned on resident's no-call week |
| Staffing at minimum | 2 x 20 (`staffing_penalty_weight`) | Pulling from rotation at exactly min staffing (current == min_req) |
| Staffing near-minimum | 1 x 20 (`staffing_penalty_weight`) | Pulling from rotation at min+1 staffing |
| Holiday non-preference | 5 (`holiday_penalty_weight`) | NF on holiday resident doesn't prefer to work |
| Holiday history | 5 | NF on holiday resident worked in prior year |
| No-call weekend buffer | 3 (`nocall_buffer_weight`) | NF on weeks adjacent to no-call dates |
| Snf spacing proximity | 3 (`nocall_buffer_weight`) | Solver-assigned NF within min_spacing_weeks of existing R2 track Snf |
| NF timing preference | 3 (`nf_timing_weight`) | NF in unpreferred timing window (from comments) |

### NF Timing Preference Details
| Pref Value | Penalty Applied When |
|------------|---------------------|
| avoid-july | w <= 4 |
| early-holidays-ok | w > 40 penalized; w <= 20 gets bonus |
| late | w <= 16 |
| late-fall | w <= 16 or w > 36 |
| avoid-core-adjacent | w >= 41 |
| holidays-ok | no timing penalty (holiday penalties handle bonus) |

### Solver Parameters
- **Time limit**: 60 seconds
- **Objective**: maximize pull_bonus - staffing_penalties - no_call_penalties - holiday_penalties - buffer_penalties - timing_penalties - snf_spacing_penalties

## 15. NF Pre-locking (`night_float.py`)

- **Block 1**: Mnf locked to first available R3 (not on no-call)
- **AIRP weeks**: marked as no-NF for affected R3s
- **LC weeks**: marked as no-NF for all R3s
- **No-call dates**: converted from M/D strings to week numbers using block date ranges

## 16. Holiday Tracking (`night_float.py`)

Holidays mapped to week numbers for NF soft constraints:
- **Thanksgiving**: 4th Thursday of November (academic year start year)
- **Christmas**: December 25 (start year)
- **New Years**: January 1 (start year + 1)

## 17. Sampler Resolution (`sampler.py`)

- **Pool**: Pcbi, Mnuc, Mucic, Mb (`SAMPLER_POOL`)
- **Split**: each 4-week Msamp block -> 2 weeks rotation A + 2 weeks rotation B
- **Scoring**: 2.0 * staffing_need + preference_bonus(max 5 - rank) - dedup_penalty(100)
- **Dedup**: large penalty (-100) prevents same rotation appearing in multiple sampler blocks
- Top 2 distinct rotations chosen per block
- Groups split at schedule block boundaries
- **Pref-to-rotation map**: "Msk" -> "Mb"
- **IR inclusion**: IR rotations (Nir, Mir) included conditionally only when no pool rotation is understaffed; max 1 IR per block

## 18. Comment-Derived Soft Constraints (`main.py` apply_comment_overrides)

Extra no-call dates: Moushey (7/10-7/11 wedding), Talebi (8/14-8/15, 9/3-9/5, 10/8-10/12 wedding parties), Liu (9/12-9/19 vacation, 12/18-12/20 wedding), Garigipati (12/14-12/18 wedding), Lue (12/14-12/18 wedding), Marsh (12/25 Christmas)
Section pref boosts: Boddu (Smr+2), Yu (Smr/Pcbi/Mai/Mb+1), Hu (Smr/Mch/Mb+1), Bermudez Garolera (Pcbi/Mnuc+1), Deshpande (Mai/Smr/Mb/Ser/Peds+1), Chan Kaelan (Smr/Mb+1), Ding (Mucic/Smr+1)
NF timing: Moushey=avoid-july, Chan Shin Mei=early-holidays-ok, Marsh=late-fall, Diwanji=avoid-core-adjacent, Rincon-Hekking=late, Talebi=holidays-ok
Schedule weight: Chan Shin Mei/Garigipati/Liu=front-heavy, Marsh/Rincon-Hekking=back-heavy
Block requests: Stahl CEP Block 2, Deshpande CEP Block 9
Pathway/FSE org pref: parsed from form cols 60/63, weight=0.3 (lowest)

## 19. Research Overrides

CEP/Research approvals are now handled entirely via `.claude/rules/cep.md` (see Section 11). The cep.md file zeroes all R4 CEP/Research counts first, then applies only the listed approvals. Residents not listed get zero blocks regardless of form responses.

## 20. Phase Ordering (`main.py`)

1. Load data (roster, history, tracks, staffing constraints, NF Recs)
2. Parse preferences (from file or Preferences tab)
3. Load R3-4 Recs **AFTER** preferences (authoritative for pathway flags, overwrites with `=`)
4. Apply CEP/Research from `.claude/rules/cep.md` (overrides form-derived values)
5. Apply comment-derived overrides
6. R1 track assignment
7. R2 track assignment + Sx/Snf deconfliction
8. R3 fixed (AIRP + LC + CORE)
9. R4 fixed (research, NRDR Mnuc, ESIR Mir, ESNR neuro, FSE)
10. Night float assignment (solver)
11. R3 clinical fill (after NF so staffing accounts for absences)
12. R4 clinical fill (after NF)
13. Sampler resolution
14. Validation + output

## 21. FSE Staffing Mapping (`rotation.py`)

FSE specialty abbreviations map to base rotation codes for staffing:

| FSE Suffix | Base Code |
|-----------|-----------|
| Abd | Mai |
| Bre | Pcbi |
| Che/Car | Mch |
| Mus | Mb |
| Ped | Peds |
| Nuc | Mnuc |
| Neu | Mucic |
| Ult | Mus |
| IR/Int | Mir |

## 22. Staffing-Aware Fill Utilities (`staffing_utils.py`)

### Combined Scoring
- `rank_rotations_by_combined_score`: staffing_weight(2) * need + pref_weight(3) * pref_score
- `get_staffing_need`: full deficit if understaffed, deficit * 0.25 if overstaffed (dampened)
- `block_exceeds_max`: checks per-week against ROTATION_MAXIMUMS with FSE mapping

### Run Penalty
- Weight: 1.0 per adjacent block with same rotation code (`staffing_utils.py:compute_run_penalty`)
- R3 builder applies multiplier of 3.0 (`_RUN_PENALTY_WEIGHT`)
- Exception: NRDR R3 Mnuc (no penalty for consecutive)

### Fill Candidates
- Base list: Mai, Mch, Mus, Mucic, Mb, Ser
- Expanded with all rotation codes from staffing constraints
- Excluded codes: Res, CEP, AIRP, LC, Mx, Sx, Snf, Snf2, Mnf, Msamp, Msampler, SSamplerCh2, Vch, Vn, Vnuc
- Filtered by year eligibility when r_year specified

### No IR on NF Blocks
- IR rotations (Zir, Vir, Sir) are not assigned to blocks that already have NF in the resident's schedule or grid NF overlay (`block_has_nf`)

## 23. Preference Parsing Safety (`prefs_parser.py`)

### Name Matching (`_find_resident_combined`)
- Primary: exact match on "First Last" or "Last, First" (case-insensitive)
- Fallback: last-name-only match, but **only if the last name is unique** among all residents in the roster
- If multiple residents share a last name (e.g., two residents named "Chan"), the fallback is skipped to prevent cross-contamination of pathway flags
- R3-4 Recs is authoritative for pathways and runs AFTER preferences to overwrite with `=`

### FSE Negative Response Filtering (`_is_negative_fse`)
- Full-string match: entire response must be a negative phrase (not word-boundary matching)
- Matches: "no", "none", "n/a", "na", "not applicable", "not interested", "no preference", "no thanks", "i do not want...", "i don't want...", "no, thank...", "not at this time..."
- Pattern: `^(no|none|n/?a|na|not applicable|not interested|no preference|no thanks|i do not want.*|i don'?t want.*|no,?\s*thank.*|not at this time.*)$` (case-insensitive)
- Applies to both dict-based (`_parse_r4_rotations`) and column-index (`_parse_combined_r4`) FSE parsing paths

## 24. Section Mapping (`rotation.py` ROTATION_SECTION)

| Rotation Codes | Section |
|---------------|---------|
| Mnuc, Snct, Mnct | NM |
| Pcbi, Sbi | BI |
| Smr | NR |
| Zai, Mai, Sai | AI |
| Mus, Sus | US |
| Mch, Mch2, Sch | CH |
| Mb, Vb, Ser, Mucic | MSK |
| Peds | PD |
| Mir, Zir, Sir, Vir | IR |
| Mx, Mc | ADMIN |

## 25. SECTION_TO_ROTATION_CODES (`rotation.py`)

Maps section abbreviations to rotation code lists for FSE and fill logic:

| Section | Rotation Codes |
|---------|---------------|
| AI | Mai, Zai |
| Breast | Pcbi, Sbi |
| Cardiac | Mch |
| Chest | Mch |
| MSK | Mb, Ser |
| Neuro | Mucic |
| Peds | Peds |
| US | Mus |
| NucMed | Mnuc |
| IR | Mir, Zir |
