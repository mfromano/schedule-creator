# Scheduling Constraints -- Plain-Language Guide

This document explains all the rules the schedule maker follows when building the annual radiology residency schedule. It is written for rotation chiefs and program directors -- no programming knowledge required.

---

## 1. Graduation Requirements

Every resident must complete minimum rotation weeks in certain areas to graduate. The scheduler tracks cumulative weeks across all four years.

### Breast Imaging
- **All residents**: 12 weeks total, from any combination of PCMB Breast (Pcbi) or ZSFG Breast (Sbi).
- Additionally requires 300 cases tracked externally via BreastTrak.

### Nuclear Medicine
- **Most residents**: 16 weeks from Moffitt Nuclear Medicine (Mnuc) or VA Nuclear Medicine (Vnuc).
  - **Partial credit**: Every 4 weeks spent on Moffitt AI (Mai), Moffitt Chest (Mch/Mch2), Pediatrics (Peds), or Moffitt Mixed (Mx) counts as 1 week of nuclear medicine. This helps residents close small gaps without a full Mnuc block.
  - Moffitt Cardiac (Mc) and Moffitt MR (Mmr) do **not** give partial credit.
- **Nuclear Radiology (NRDR) residents**: 48 weeks, a much higher bar. Partial credit does **not** apply. R4 research weeks count toward this total.

### Interventional Radiology (ESIR)
- 12 weeks total from any IR rotation: Moffitt IR (Mir), Zion IR (Zir), ZSFG IR (Sir), or VA IR (Vir).
- Typical progression: R1 = none, R2 = 2 weeks (Vir/Sir), R3 = 2 weeks (Zir/Mir), R4 = 8 weeks (Mir).

### Neuroradiology (ESNR)
- 6 blocks of neuro rotations in R4, with a maximum of 1 block on ZSFG MR (Smr). The rest are on Moffitt Neuro (Mucic).
- Individual residents may be exempt from this requirement if they have already met it through prior arrangements.

### T32 Research Residents
- Must meet standard breast and non-NRDR nuclear medicine requirements before their research year.

---

## 2. Hospital System Rules

Residents cannot be assigned to two different hospital systems in the same two-week period. This is a payroll and logistics constraint.

The three systems are:
- **UCSF/Moffitt**: All "M" rotations (Mai, Mb, Mch, Mnuc, etc.), all "P" rotations (Pcbi, Peds), and all "Z" rotations (Zai, Zir) -- these are all the same payroll entity. Zion campus is part of UCSF.
- **Zuckerberg San Francisco General (ZSFG)**: All "S" rotations (Ser, Smr, Sbi, Sx, etc.).
- **VA**: All "V" rotations (Vb, Vir).

Non-clinical assignments like Research, CEP, AIRP, Learning Center, and CORE are system-neutral and never cause conflicts.

The hospital conflict check looks at each half of a 4-week block separately (weeks 1-2 and weeks 3-4), so a resident could be at UCSF for the first half and ZSFG for the second half of the same block -- but not in the same half.

Individual residents may be exempt from hospital conflict checks due to dual fellowship arrangements.

---

## 3. Staffing Requirements

Each rotation has a minimum number of residents that must be assigned per week to keep clinical services running. Key minimums include:

| Service | Minimum Residents |
|---------|:-:|
| Moffitt AI (Mai + Zion AI) | 3 |
| Moffitt Ultrasound | 2 |
| Moffitt Cardiothoracic (Mch, Mch2, Mc) | 2 |
| Pediatrics | 1 |
| Moffitt Neuro (Mucic + Mnct) | 3 |
| Moffitt Breast/MSK (Mb) | 1 |
| Moffitt Nuclear Medicine | 2 |
| PCMB Breast (Pcbi) | 1 |
| ZSFG (all rotations combined) | 8 |
| VA MSK/Nucs (Vb) | 1 |
| Mucic (standalone) | 1 |
| Zion IR (Zir) | 1 |

There are also **maximum** caps to prevent overcrowding:

| Service | Maximum Residents |
|---------|:-:|
| ZSFG Call (Sx) | 1 |
| ZSFG Night Float (Snf) | 1 |
| Moffitt Night Float (Mnf) | 1 |
| ZSFG Senior Night Float (Snf2) | 1 |
| PCMB Breast (Pcbi) | 3 |
| Nuclear Medicine (Mnuc) | 5 |
| VA MSK (Vb) | 1 |
| VA IR (Vir) | 1 |
| Zion IR (Zir) | 1 |
| ZSFG ER (Ser) | 2 |
| Moffitt AI (Mai) | 5 |
| Moffitt Neuro (Mucic) | 6 |

Any rotation not listed above has a default maximum of 6. Fellowship (FSE) rotations count against the cap of their base rotation (e.g., a Breast FSE counts toward the Pcbi cap).

The actual staffing targets may be overridden by data in the Excel workbook (rows 101-151 of the Base Schedule tab).

---

## 4. Rotation Year Eligibility

Not every rotation is open to every class year:

| Rotation | Who Can Do It |
|----------|--------------|
| VA IR (Vir) | R2 only |
| ZSFG IR (Sir) | R2 only |
| Zion IR (Zir) | R3 and R4 (R4 only if ESIR or IR fellowship) |
| Zion AI (Zai) | R2 only |
| Moffitt Neuro CT (Mnct) | R1 only |
| VA Nuclear Medicine (Vnuc) | Retired -- never assigned |

---

## 5. R1 and R2 Track System

### R1 Tracks
- First-year residents are assigned 1:1 to predefined rotation tracks by the rotation chief.
- If there are more residents than tracks, some residents get duplicate tracks.
- "Sampler" blocks are left generic until the final scheduling phase, when they are split into specific 2-week rotations based on staffing needs.

### R2 Tracks
- Second-year residents rank available tracks by preference.
- An optimization solver assigns tracks to minimize total dissatisfaction (lower rank = better outcome). The solver runs for up to 30 seconds.
- Each track gets at least 1 resident when possible; no track gets more than its fair share.
- After track assignment, the scheduler deconflicts weeks where multiple residents would be on ZSFG call (Sx) or ZSFG night float (Snf) at the same time. Displaced rotations come from Breast (Pcbi), MSK (Mb), Neuro (Mucic), Pediatrics (Peds), Nuclear Medicine (Mnuc), AI (Mai), or Chest (Mch). The scheduler first tries to maintain 4-week spacing between call/NF groups, relaxing to no minimum if needed.

---

## 6. R3 Schedule Building

Third-year schedules are built individually (no tracks). The process:

1. **AIRP** (American Institute for Radiologic Pathology): Assigned first, max 4 residents per session. Preferences and groupmate requests are considered.
2. **Learning Center**: All R3s are placed in the last full block before the CORE exam (or specific weeks if provided).
3. **CORE**: Assigned to specific weeks if provided.
4. **Zion IR**: Maximum 1 block per R3. Not allowed in or after the block before Learning Center. Preferred blocks get a soft bonus.
5. **NRDR R3s**: Get 6 blocks of Nuclear Medicine as a fixed commitment.
6. **Remaining blocks**: Filled based on graduation deficiencies, staffing needs, and section preferences. The scheduler considers schedule weighting (front-heavy or back-heavy) when choosing blocks. Consecutive blocks on the same rotation are discouraged unless needed (e.g., NRDR Nuclear Medicine). IR rotations are not placed on blocks where the resident already has night float assigned.

---

## 7. R4 Schedule Building

Fourth-year schedules handle the most complexity:

### Fixed Commitments (Placed First)
- **Block requests**: Specific block/rotation requests from comments are placed first (e.g., CEP in Block 2 or Block 9).
- **Research/CEP**: Maximum 2 months unless supplementary funding. Placed away from high-need periods (blocks 5-7 around RSNA/Learning Center). Preferred blocks: 3, 4, 8, 9, 10, 11, 2, 12. Approved CEP/Research blocks come from an authoritative approvals list -- residents not on the list get zero blocks regardless of what they requested on the form.
- **NRDR R4s**: 6 blocks Nuclear Medicine (Mnuc).
- **ESIR R4s**: 8 blocks Moffitt IR (Mir).
- **ESNR R4s**: 6 blocks neuro (max 1 on ZSFG MR/Smr, rest on Moffitt Neuro/Mucic). Individual residents may be exempt.
- **Fellowships (FSE)**: Breast fellowship requires 6 months without exception. Other fellowships typically get 2 blocks. All fellowship specialties are scheduled (not just the first listed). Block placement respects organization preferences (contiguous vs. interspersed).

### Graduation Requirements (Placed Second)
- Breast imaging deficits are covered with Pcbi or Sbi blocks.
- Nuclear medicine deficits are covered with Mnuc blocks.
- Other recommended rotations filled by staffing need.
- Schedule weighting (front-heavy/back-heavy) influences block selection.

### Mixed Radiology (Mx)
- All R4s get at least one Mx block unless they are T32 or have dual subspecialty commitments.
- Block count comes from recommendations, defaulting to 1.

### T32 Research Residents
- Research for the entire year except up to 2 months of clinical coverage.
- Clinical blocks are typically near the Learning Center/CORE period (blocks 12-13).
- Clinical blocks filled with: breast deficits first, then graduation requirements, then staffing needs.
- T32 residents are never assigned Zion IR.

### Remaining Blocks
- Filled using a scoring system that balances staffing needs (weight 2) and resident preferences (weight 3). Fellowship rotation codes are boosted (weight 5, max preference score 3). IR rotations are not placed on blocks where the resident already has night float assigned.

---

## 8. Night Float Assignment

Night float is one of the most constrained parts of the schedule. Each class year has specific rules:

### Who Does What
| Shift | Class Years | Typical Count |
|-------|------------|---------------|
| ZSFG Night Float (Snf) | R2 | Built into tracks |
| Moffitt Night Float (Mnf) | R2, R3 | R2: 2 weeks; R3: up to 2 weeks |
| ZSFG Senior Night Float (Snf2) | R3, R4 | R3: up to 2 weeks; R4: 2 weeks |

- **R3 cap**: Total of Mnf + Snf2 weeks cannot exceed 3, with at least 1 NF week required.
- **R4 Mnf**: Normally 0, but can be overridden by NF Recs tab data.
- **Spacing**: At least 4 weeks between any night float assignments for the same resident.
- **Census-based distribution**: When the NF Recs tab provides class-level census data (e.g., how many R2s get 1 vs. 2 Mnf weeks), the solver uses those exact distributions rather than per-resident defaults.

### Assignment Priority (Backwards from Hardest Periods)
1. Block 1: Assign an R3 to Mnf (first R3 not on no-call)
2. AIRP weeks: marked as unavailable for affected R3s
3. LC weeks: marked as unavailable for all R3s
4. Remaining: solver fills optimally

### Hard Rules (Cannot Be Violated)
- Only 1 Moffitt night float and 1 ZSFG senior night float per week across the entire program.
- A resident cannot have both Mnf and Snf2 in the same week.
- No night float adjacent to existing call/NF weeks (Sx, Mnf, Snf2) in the base schedule.
- No night float on weeks where a resident already has Sx or Snf assigned (prevents stacking).
- No Moffitt night float during weeks a resident is on VA MSK (Vb).
- No night float during IR rotations (Zir, Vir, Sir).
- No night float for R4s during CEP or Research weeks.
- Night float cannot be assigned if pulling the resident would drop their daytime rotation below minimum staffing.

### Preferences Respected (Soft -- Solver Tries to Honor)
- **No-call dates** (weight 20): Strongly avoided but not absolutely forbidden.
- **Staffing near-minimum** (weight 20): Avoid pulling from rotations at or near minimum staffing. Pulling from a rotation at exactly minimum is penalized twice as heavily as pulling from minimum + 1.
- **Holiday preferences** (weight 5): Considers Thanksgiving, Christmas, and New Year's. Penalizes assigning holidays the resident doesn't prefer and holidays they worked in prior years.
- **No-call buffer** (weight 3): Avoids weeks adjacent to no-call dates.
- **Snf proximity** (weight 3): Avoids placing solver-assigned night float too close to existing junior night float (Snf) weeks from R2 tracks.
- **NF timing preferences** (weight 3): Honors requests for early-year, late-year, avoid-July, etc.
- **Rotation pull preferences** (bonus 10): Night float residents are preferably pulled from Breast (Pcmb, Pcbi), MSK (Mb), Neuro (Mucic), Pediatrics, or Nuclear Medicine. Other rotations get a penalty of -5.

The solver runs for up to 60 seconds to find the best assignment.

---

## 9. Sampler Block Resolution

R1 "sampler" blocks are 4-week rotations split into two 2-week halves. Each half is assigned to one of: PCMB Breast (Pcbi), Nuclear Medicine (Mnuc), Moffitt Neuro (Mucic), or Moffitt MSK (Mb).

The two halves are chosen to:
1. Maximize staffing coverage (filling in for upper-level residents on night float)
2. Respect sampler preferences (lower rank = more preferred)
3. Avoid repeating the same rotation across different sampler blocks (strong deduplication penalty)

IR rotations may be included as a sampler option when all standard pool rotations are adequately staffed.

---

## 10. Comment-Based Adjustments

Some residents provide free-text comments in the preference survey that result in schedule accommodations:

- **Extra no-call dates**: Weddings, honeymoons, and family events are added as protected dates.
- **Night float timing**: Some residents prefer early-year, late-year, or holiday night float; others need to avoid specific periods (e.g., avoid July, avoid CORE-adjacent weeks).
- **Schedule weighting**: Some residents request front-loaded or back-loaded schedules (harder rotations early vs. late).
- **Specific block requests**: Certain residents need CEP or research in a particular block.
- **Section preference boosts**: Residents preparing for specific fellowships or with stated interests get small boosts toward relevant rotations.

These are soft preferences -- the solver tries to honor them but staffing and graduation requirements take priority.

---

## 11. Preference Parsing

When reading resident preferences from Google Forms responses, the scheduler matches each response to a resident on the roster:

- **Primary match**: Full name ("First Last" or "Last, First"), case-insensitive.
- **Fallback match**: Last name only, but **only if no other resident shares the same last name**. If two residents have the same last name, the fallback is skipped to prevent data from one resident being applied to the wrong person.
- **Pathway authority**: The R3-R4 Recommendations tab is the definitive source for subspecialty pathway flags (ESIR, ESNR, T32, NRDR). It is loaded after preferences and overwrites any self-reported pathway data from the survey.
- **FSE opt-out**: If a resident's entire FSE response is a negative phrase like "no", "none", "n/a", "not interested", "no preference", or "I don't want...", the response is treated as blank (no FSE preference). Only full-response negatives are filtered -- a response that contains an actual specialty name alongside a negative word is kept.

---

## 12. Phase Ordering

The schedule is built in a specific sequence to ensure dependencies are respected:

1. Load roster, history, tracks, and staffing data
2. Import resident preferences
3. Load R3-R4 recommendations (overrides self-reported pathway data)
4. Apply approved CEP/Research blocks (overrides form-derived values)
5. Apply comment-derived adjustments
6. Assign R1 tracks
7. Assign R2 tracks and deconflict overlapping call/night float
8. Place R3 fixed commitments (AIRP, Learning Center, CORE)
9. Place R4 fixed commitments (research, fellowships, subspecialty blocks)
10. Assign night float across all eligible residents
11. Fill remaining R3 clinical blocks
12. Fill remaining R4 clinical blocks
13. Resolve R1 sampler blocks into specific rotations
14. Validate and output the final schedule
