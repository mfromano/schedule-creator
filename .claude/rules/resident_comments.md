# Resident Free-Text Comments & Constraint Mappings

Survey column: "Please enter additional comments here if you desire" (col 93, 0-based)

Categories:
- **A**: Maps to existing fields (no-call dates, section pref boosts)
- **B**: New lightweight fields (nf_timing_pref, schedule_weight, block_requests)
- **C**: Document-only (too personal/specific for code)

---

## R2 (Rising R3)

### Moushey, Alexander
**Comment**: Getting married and going on honeymoon 7/11-8/1, would prefer no NF in July
**Category**: A + B
**Mapping**: Extra no-call dates (7/11, 7/18, 7/25, 8/1), nf_timing_pref="avoid-july"

### Liu, Gary
**Comment**: Vacation 9/12-9/19, wedding 12/18-12/20
**Category**: A
**Mapping**: Extra no-call dates (9/12-9/19, 12/18-12/20)

### Boddu, Priyanka
**Comment**: Would like Smr for ESNR pathway preparation
**Category**: A
**Mapping**: Section pref boost Smr +2

### Chan, Shin Mei
**Comment**: Happy to front-load harder rotations and NF, fine with holidays
**Category**: B
**Mapping**: nf_timing_pref="early-holidays-ok", schedule_weight="front-heavy"

### Bermudez, Mario
**Comment**: Wants breast and nucs early to help decide fellowship direction
**Category**: A
**Mapping**: Section pref boost Pcbi +1, Mnuc +1

### Garigipati, Pranavi
**Comment**: Would prefer IR earlier in the year
**Category**: B
**Mapping**: schedule_weight="front-heavy"

### Marsh, Margaret
**Comment**: Maternity leave July/Aug, prefer NF late fall/early winter, Christmas off
**Category**: A + B
**Mapping**: Extra no-call date (12/25), nf_timing_pref="late-fall", schedule_weight="back-heavy"

---

## R3 (Rising R4)

### Yu, Theresa
**Comment**: Wants neuro, breast, AI, MSK blocks; prefers 3 not 4 months chest
**Category**: A
**Mapping**: Section pref boost Smr +1, Pcbi +1, Mai +1, Mb +1

### Hu, Anne
**Comment**: Wants neuro, chest, MSK blocks
**Category**: A
**Mapping**: Section pref boost Smr +1, Mch +1, Mb +1

### Deshpande, Nikita
**Comment**: Wants AI, neuro, MSK, MSK, Peds; CEP in Block 9 (wedding in India)
**Category**: A + B
**Mapping**: Section pref boost Mai +1, Smr +1, Mb +1, Ser +1, Peds +1; block_requests={9: "CEP"}

### Stahl, Alexandra
**Comment**: CEP in Block 2
**Category**: B
**Mapping**: block_requests={2: "CEP"}

### Diwanji, Tanay
**Comment**: Prefers lighter schedule around CORE prep
**Category**: B
**Mapping**: nf_timing_pref="avoid-core-adjacent"

### Rincon-Hekking, Jorge
**Comment**: Mom undergoing bone marrow transplant, needs lighter first 3-4 months, backload NF
**Category**: B + C
**Mapping**: nf_timing_pref="late", schedule_weight="back-heavy"
**Note**: Full personal context documented here for rotation chief awareness; code uses schedule_weight and nf_timing_pref only

### Talebi, Arian
**Comment**: Wedding party Aug 14-15, Sep 3-5, Oct 8-12; willing to work all holidays
**Category**: A + B
**Mapping**: Extra no-call dates (8/14, 8/15, 9/3, 9/4, 9/5, 10/8-10/12), nf_timing_pref="holidays-ok"

---

## Document-Only (Category C)

### Pan (R3)
**Comment**: Prefers Saturday over Sunday call
**Note**: Call chief territory, not handled in rotation scheduling

### Bahar (R2)
**Comment**: Track #8 preference
**Note**: Already captured in track rankings form data

### Saikia (R3)
**Comment**: Interest in NIR
**Note**: Not a standard rotation code; documented for awareness only

---

## Residents with non-actionable comments (thank-yous, acknowledgments, etc.)
Not listed individually — approximately 20 of 38 comments were non-actionable.
