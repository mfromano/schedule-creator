"""Staffing constraints, graduation requirements, and night float rules."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StaffingBound:
    """Min/max residents for a rotation or section per week."""
    rotation_codes: set[str]  # which rotation codes count toward this group
    label: str
    min_residents: int = 0
    max_residents: int = 99


@dataclass
class StaffingConstraints:
    """Per-week staffing min/max from Base Schedule rows 101-151."""
    bounds: list[StaffingBound] = field(default_factory=list)

    def check_week(self, week_assignments: dict[str, str]) -> list[str]:
        """Check all staffing bounds for a week. Returns list of violations."""
        violations = []
        for bound in self.bounds:
            count = sum(1 for code in week_assignments.values()
                        if code in bound.rotation_codes)
            if count < bound.min_residents:
                violations.append(
                    f"{bound.label}: {count} < min {bound.min_residents}")
            if count > bound.max_residents:
                violations.append(
                    f"{bound.label}: {count} > max {bound.max_residents}")
        return violations


@dataclass
class GraduationRequirement:
    """A single graduation requirement."""
    label: str
    section: str                          # e.g. "NM", "BI"
    required_weeks: float                 # minimum weeks needed
    qualifying_rotations: set[str]        # rotation codes that count
    partial_credit_rotations: dict[str, float] = field(default_factory=dict)
    # rotation_code → credit_ratio (e.g. Mai → 0.25 for NM)
    applies_to_pathway: str | None = None  # None = all, or "NRDR", "ESIR", etc.


# Standard graduation requirements from goals.md
STANDARD_GRAD_REQS = [
    GraduationRequirement(
        label="Breast Imaging",
        section="BI",
        required_weeks=12,
        qualifying_rotations={"Pcbi", "Mb", "Sbi", "Vb"},
    ),
    GraduationRequirement(
        label="Nuclear Medicine (non-NRDR)",
        section="NM",
        required_weeks=16,
        qualifying_rotations={"Mnuc", "Vnuc", "Snct", "Mnct"},
        partial_credit_rotations={"Mai": 0.25, "Mch": 0.25, "Peds": 0.25, "Mx": 0.25},
        applies_to_pathway="non-NRDR",
    ),
    GraduationRequirement(
        label="Nuclear Medicine (NRDR)",
        section="NM",
        required_weeks=48,
        qualifying_rotations={"Mnuc", "Vnuc", "Snct", "Mnct"},
        # NB: 4:1 partial credit does NOT apply to NRDR
        applies_to_pathway="NRDR",
    ),
    GraduationRequirement(
        label="ESIR (IR)",
        section="IR",
        required_weeks=12,
        qualifying_rotations={"Mir", "Zir", "Sir", "Vir"},
        applies_to_pathway="ESIR",
    ),
    GraduationRequirement(
        label="ESNR (Neuro R4)",
        section="NR",
        required_weeks=24,  # 6 blocks × 4 weeks, max 1 on Smr
        qualifying_rotations={"Zai", "Smr"},
        applies_to_pathway="ESNR",
    ),
]


@dataclass
class GraduationRequirements:
    """Container for all graduation requirements."""
    requirements: list[GraduationRequirement] = field(
        default_factory=lambda: list(STANDARD_GRAD_REQS)
    )

    def check_resident(
        self,
        pathway_str: str,
        historical_weeks: dict[str, float],
        current_weeks: dict[str, float],
    ) -> list[str]:
        """Check if a resident meets all applicable graduation requirements.

        Args:
            pathway_str: e.g. "NRDR", "ESIR", "non-NRDR", "ESNR", or ""
            historical_weeks: rotation_code → total weeks from prior years
            current_weeks: rotation_code → weeks in current year

        Returns list of unmet requirements.
        """
        violations = []
        for req in self.requirements:
            if req.applies_to_pathway and req.applies_to_pathway != pathway_str:
                if not (req.applies_to_pathway == "non-NRDR" and pathway_str != "NRDR"):
                    continue

            total = 0.0
            for code in req.qualifying_rotations:
                total += historical_weeks.get(code, 0) + current_weeks.get(code, 0)
            for code, ratio in req.partial_credit_rotations.items():
                total += (historical_weeks.get(code, 0) + current_weeks.get(code, 0)) * ratio

            if total < req.required_weeks:
                violations.append(
                    f"{req.label}: {total:.1f}/{req.required_weeks} weeks "
                    f"(deficit: {req.required_weeks - total:.1f})"
                )
        return violations


@dataclass
class NFRules:
    """Night float assignment rules from goals.md."""
    # R2 gets 2 weeks Mnf (Snf already in track)
    r2_mnf_weeks: int = 2
    # R3 max total NF = 3 (Snf2 + Mnf combined)
    r3_max_nf: int = 3
    # R4 gets 2 weeks Snf2
    r4_snf2_weeks: int = 2
    # Minimum spacing between NF assignments (weeks)
    min_spacing_weeks: int = 4

    # Shift applicability
    # Snf: R2 (in track), Mnf: R2+R3, Snf2: R3+R4, Sx: R2 (in track), Mx: R4
    shift_eligibility: dict[str, set[int]] = field(default_factory=lambda: {
        "Snf": {2},
        "Mnf": {2, 3},
        "Snf2": {3, 4},
        "Sx": {2},
    })

    # Pull preferences for NF (which base rotations to pull from)
    preferred_pull_rotations: set[str] = field(default_factory=lambda: {
        "Pcmb", "Mb", "Mucic", "Peds", "Mnuc", "Pcbi",
    })
