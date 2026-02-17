"""Resident data model with preferences and history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Flag, auto


class Pathway(Flag):
    """Subspecialty pathway flags — can be combined."""
    NONE = 0
    ESIR = auto()
    ESNR = auto()
    T32 = auto()
    NRDR = auto()


@dataclass
class SamplerPrefs:
    """R1 sampler rotation preferences (ranked)."""
    rankings: dict[str, int] = field(default_factory=dict)  # rotation_code → rank (1=top)


@dataclass
class TrackPrefs:
    """R2 track ranking preferences."""
    rankings: dict[int, int] = field(default_factory=dict)  # track_number → rank (1=top)


@dataclass
class SectionPrefs:
    """R3/R4 section preferences (top/bottom)."""
    top: list[str] = field(default_factory=list)       # section codes ranked as top
    bottom: list[str] = field(default_factory=list)     # section codes ranked as bottom
    # Per-rotation preference scores (from form: TOP 1/2/3, BOTTOM 1/2/3)
    scores: dict[str, int] = field(default_factory=dict)  # code → score (-3 to 3)


@dataclass
class AIRPPrefs:
    """R3 AIRP session preferences."""
    rankings: dict[str, int] = field(default_factory=dict)  # session_id → rank
    group_requests: list[str] = field(default_factory=list)  # names of desired groupmates


@dataclass
class ZirPrefs:
    """Zir block timing preferences."""
    preferred_blocks: list[int] = field(default_factory=list)  # block numbers preferred


@dataclass
class BlockPrefs:
    """Generic block-level preferences (R3/R4)."""
    # block_number → rotation code preference
    assignments: dict[int, str] = field(default_factory=dict)


@dataclass
class FSEPrefs:
    """R4 focused subspecialty experience preferences."""
    specialties: list[str] = field(default_factory=list)  # e.g. ["Abdominal Imaging", "Chest"]
    organization: str = ""  # "Contiguous" or "Interrupted interspersed blocks"


@dataclass
class NoCallDates:
    """Dates when a resident should not be assigned call/NF."""
    weekends: list[date] = field(default_factory=list)
    weeks: list[tuple[date, date]] = field(default_factory=list)  # (start, end) ranges
    holidays: list[str] = field(default_factory=list)  # e.g. ["Christmas", "Thanksgiving"]
    raw_dates: list[date] = field(default_factory=list)  # parsed MM/DD dates for NF tab


@dataclass
class Resident:
    """A radiology resident with all scheduling-relevant data."""
    name: str                          # "Last, First" format
    first_name: str = ""
    last_name: str = ""
    pgy: int = 0                       # current PGY level (1-5)
    r_year: int = 0                    # radiology year (1-4), = pgy - 1 for most
    pathway: Pathway = Pathway.NONE

    # Historical rotation weeks (section_code → total weeks across all prior years)
    history: dict[str, float] = field(default_factory=dict)

    # Current year schedule (week_number → rotation_code), filled during scheduling
    schedule: dict[int, str] = field(default_factory=dict)

    # Track assignment (for R1/R2)
    track_number: int | None = None

    # Preferences
    sampler_prefs: SamplerPrefs | None = None
    track_prefs: TrackPrefs | None = None
    section_prefs: SectionPrefs | None = None
    airp_prefs: AIRPPrefs | None = None
    zir_prefs: ZirPrefs | None = None
    block_prefs: BlockPrefs | None = None
    fse_prefs: FSEPrefs | None = None
    no_call: NoCallDates = field(default_factory=NoCallDates)

    # R4 specific
    research_months: int = 0
    cep_months: int = 0

    # Deficiency analysis (from R3-4 Recs tab)
    deficient_sections: list[str] = field(default_factory=list)
    recommended_blocks: dict[str, float] = field(default_factory=dict)  # rotation → # blocks

    # Vacation/academic/leave dates
    vacation_dates: list[str] = field(default_factory=list)
    academic_dates: list[str] = field(default_factory=list)
    leave_info: str = ""

    @property
    def is_nrdr(self) -> bool:
        return Pathway.NRDR in self.pathway

    @property
    def is_esir(self) -> bool:
        return Pathway.ESIR in self.pathway

    @property
    def is_esnr(self) -> bool:
        return Pathway.ESNR in self.pathway

    @property
    def is_t32(self) -> bool:
        return Pathway.T32 in self.pathway

    @property
    def dual_pathway(self) -> bool:
        """True if pursuing 2+ subspecialization pathways."""
        count = sum(1 for p in [Pathway.ESIR, Pathway.ESNR, Pathway.T32, Pathway.NRDR]
                    if p in self.pathway)
        return count >= 2

    def get_schedule_for_block(self, block: int) -> list[str]:
        """Get rotation codes for a given block (up to 4 weeks)."""
        # Blocks are 4 weeks each; block 1 = weeks 1-4, block 2 = weeks 5-8, etc.
        start_week = (block - 1) * 4 + 1
        return [self.schedule.get(w, "") for w in range(start_week, start_week + 4)]
