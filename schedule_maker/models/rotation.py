"""Rotation codes, hospital system mapping, and section definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HospitalSystem(Enum):
    """Hospital systems — no resident can be at two systems in the same block.

    Per goals.md the constraint is about payroll.  UCSF encompasses both
    Moffitt/Mission Bay and Parnassus/China Basin (PCMB), so they share a
    single payroll entity.  Only UCSF vs ZSFG vs VA are truly distinct.
    """
    UCSF = "UCSF (Moffitt/Parnassus)"
    ZSFG = "Zuckerberg SF General"
    VA = "VA"
    OTHER = "Other"


class Section(Enum):
    """Clinical sections for rotation grouping and graduation tracking."""
    NM = "Nuclear Medicine"
    BI = "Breast Imaging"
    NR = "Neuroradiology"
    AI = "Abdominal Imaging"
    US = "Ultrasound"
    CH = "Chest/Cardiac"
    CV = "Cardiovascular"
    MSK = "Musculoskeletal"
    PD = "Pediatrics"
    IR = "Interventional Radiology"
    ADMIN = "Administrative"


# Prefix → hospital system mapping
SITE_PREFIX_MAP: dict[str, HospitalSystem] = {
    "M": HospitalSystem.UCSF,
    "Z": HospitalSystem.ZSFG,
    "S": HospitalSystem.ZSFG,  # SFGH rotations (Sx, Sir, Ser, Smr, Sbi, Snf, Snf2, Sus, Snct)
    "V": HospitalSystem.VA,
    "P": HospitalSystem.UCSF,  # Parnassus/China Basin = same UCSF payroll as Moffitt
}

# Rotation code → section mapping (comprehensive from Key tab + goals.md)
ROTATION_SECTION: dict[str, Section] = {
    # Nuclear medicine
    "Mnuc": Section.NM, "Vnuc": Section.NM, "Snct": Section.NM, "Mnct": Section.NM,
    # Breast imaging
    "Pcbi": Section.BI, "Mb": Section.BI, "Sbi": Section.BI, "Vb": Section.BI,
    # Neuroradiology
    "Zai": Section.NR, "Smr": Section.NR,
    # Abdominal imaging
    "Mai": Section.AI, "Sai": Section.AI,
    # Ultrasound
    "Mus": Section.US, "Sus": Section.US,
    # Chest/cardiac
    "Mch": Section.CH, "Mch2": Section.CH, "Sch": Section.CH,
    # MSK
    "Mb": Section.MSK,  # also BI — dual-counted
    "Ser": Section.MSK, "Mucic": Section.MSK,
    # Pediatrics
    "Peds": Section.PD,
    # IR
    "Mir": Section.IR, "Zir": Section.IR, "Sir": Section.IR, "Vir": Section.IR,
    # Admin/other
    "Mx": Section.ADMIN, "Mc": Section.ADMIN,
}

# Rotations that give partial NucMed credit (4 weeks = 1 week NM credit)
NM_PARTIAL_CREDIT_ROTATIONS = {"Mai", "Mch", "Peds", "Mx"}
NM_PARTIAL_RATIO = 0.25  # 1 week NM credit per 4-week block

# Rotations that do NOT give NM partial credit
NM_NO_CREDIT = {"Mc", "Mmr", "Zai"}


@dataclass
class RotationCode:
    """A rotation code from the Key tab."""
    code: str
    section: str          # section label from Key tab
    label: str            # human-readable label
    pgy_eligible: set[int] = field(default_factory=set)  # which PGY years can do this
    r1_eligible: bool = False
    r2_eligible: bool = False
    r3_eligible: bool = False
    r4_eligible: bool = False

    @property
    def hospital_system(self) -> HospitalSystem:
        """Determine hospital system from rotation code prefix."""
        if not self.code:
            return HospitalSystem.OTHER
        first = self.code[0]
        return SITE_PREFIX_MAP.get(first, HospitalSystem.OTHER)


def get_hospital_system(code: str) -> HospitalSystem:
    """Get hospital system for a rotation code string."""
    if not code:
        return HospitalSystem.OTHER
    # Special cases
    if code in ("Peds",):
        return HospitalSystem.UCSF
    first = code[0]
    return SITE_PREFIX_MAP.get(first, HospitalSystem.OTHER)


def is_night_float(code: str) -> bool:
    """Check if a rotation code is a night float assignment."""
    return code in ("Snf", "Snf2", "Mnf", "Sx")


@dataclass
class Rotation:
    """A specific rotation assignment for one biweek slot."""
    code: str
    block: int          # 1-13
    biweek: str         # "A" or "B"
    week_number: int    # 1-52 absolute week in academic year

    @property
    def hospital_system(self) -> HospitalSystem:
        return get_hospital_system(self.code)
