"""Unit tests for constraint definitions and rotation mappings.

These tests verify the data tables and constants match the documented
constraints in constraints.md / goals.md — no Excel files or build pipeline needed.
"""

from __future__ import annotations

import pytest

from schedule_maker.models.constraints import STANDARD_GRAD_REQS, NFRules
from schedule_maker.models.rotation import (
    HospitalSystem,
    NM_PARTIAL_CREDIT_ROTATIONS,
    NM_PARTIAL_RATIO,
    NM_NO_CREDIT,
    SITE_PREFIX_MAP,
    FSE_STAFFING_MAP,
    get_hospital_system,
    fse_to_base_code,
)
from schedule_maker.validation.staffing import ROTATION_MINIMUMS, ROTATION_MAXIMUMS
from schedule_maker.staffing_utils import _ROTATION_YEAR_ELIGIBILITY, build_fill_candidates


# ── Helpers ──────────────────────────────────────────────────────


def _find_grad_req(label_prefix: str):
    """Find a STANDARD_GRAD_REQS entry by label prefix."""
    matches = [r for r in STANDARD_GRAD_REQS if r.label.startswith(label_prefix)]
    assert matches, f"No grad req starting with '{label_prefix}'"
    return matches[0]


# ── 1. Graduation Requirements ──────────────────────────────────


class TestGradReqBreast:
    def test_qualifying_rotations(self):
        req = _find_grad_req("Breast")
        assert req.qualifying_rotations == {"Pcbi", "Sbi"}

    def test_required_weeks(self):
        req = _find_grad_req("Breast")
        assert req.required_weeks == 12

    def test_no_partial_credit(self):
        req = _find_grad_req("Breast")
        assert req.partial_credit_rotations == {}

    def test_applies_to_all(self):
        req = _find_grad_req("Breast")
        assert req.applies_to_pathway is None


class TestGradReqNucMedNonNRDR:
    def test_qualifying_rotations(self):
        req = _find_grad_req("Nuclear Medicine (non")
        assert req.qualifying_rotations == {"Mnuc", "Vnuc"}

    def test_required_weeks(self):
        req = _find_grad_req("Nuclear Medicine (non")
        assert req.required_weeks == 16

    def test_partial_credit_rotations(self):
        req = _find_grad_req("Nuclear Medicine (non")
        assert "Mai" in req.partial_credit_rotations
        assert "Mch" in req.partial_credit_rotations
        assert "Peds" in req.partial_credit_rotations
        assert "Mx" in req.partial_credit_rotations
        for ratio in req.partial_credit_rotations.values():
            assert ratio == 0.25

    def test_no_credit_from_mc_mmr(self):
        req = _find_grad_req("Nuclear Medicine (non")
        assert "Mc" not in req.partial_credit_rotations
        assert "Mmr" not in req.partial_credit_rotations

    def test_applies_to_non_nrdr(self):
        req = _find_grad_req("Nuclear Medicine (non")
        assert req.applies_to_pathway == "non-NRDR"


class TestGradReqNucMedNRDR:
    def test_qualifying_rotations(self):
        req = _find_grad_req("Nuclear Medicine (NRDR")
        assert req.qualifying_rotations == {"Mnuc", "Vnuc"}

    def test_required_weeks(self):
        req = _find_grad_req("Nuclear Medicine (NRDR")
        assert req.required_weeks == 48

    def test_no_partial_credit(self):
        req = _find_grad_req("Nuclear Medicine (NRDR")
        assert req.partial_credit_rotations == {}

    def test_applies_to_nrdr(self):
        req = _find_grad_req("Nuclear Medicine (NRDR")
        assert req.applies_to_pathway == "NRDR"


class TestGradReqESIR:
    def test_qualifying_rotations(self):
        req = _find_grad_req("ESIR")
        assert req.qualifying_rotations == {"Mir", "Zir", "Sir", "Vir"}

    def test_required_weeks(self):
        req = _find_grad_req("ESIR")
        assert req.required_weeks == 12


class TestGradReqESNR:
    def test_qualifying_rotations(self):
        req = _find_grad_req("ESNR")
        assert req.qualifying_rotations == {"Mucic", "Smr"}

    def test_required_weeks(self):
        req = _find_grad_req("ESNR")
        assert req.required_weeks == 24


# ── 2. NM Partial Credit Constants ──────────────────────────────


class TestNMPartialCredit:
    def test_eligible_rotations(self):
        assert NM_PARTIAL_CREDIT_ROTATIONS == {"Mai", "Mch", "Mch2", "Peds", "Mx"}

    def test_ratio(self):
        assert NM_PARTIAL_RATIO == 0.25

    def test_no_credit_rotations(self):
        assert NM_NO_CREDIT == {"Mc", "Mmr"}

    def test_no_overlap(self):
        assert NM_PARTIAL_CREDIT_ROTATIONS & NM_NO_CREDIT == set()


# ── 3. Hospital System Mapping ──────────────────────────────────


class TestHospitalSystemMapping:
    @pytest.mark.parametrize("code,expected", [
        ("Mai", HospitalSystem.UCSF),
        ("Mb", HospitalSystem.UCSF),
        ("Mch", HospitalSystem.UCSF),
        ("Mucic", HospitalSystem.UCSF),
        ("Mnuc", HospitalSystem.UCSF),
        ("Mnf", HospitalSystem.UCSF),
        ("Mir", HospitalSystem.UCSF),
        ("Pcbi", HospitalSystem.UCSF),
        ("Peds", HospitalSystem.UCSF),
        ("Zai", HospitalSystem.UCSF),
        ("Zir", HospitalSystem.UCSF),
        ("Ser", HospitalSystem.ZSFG),
        ("Smr", HospitalSystem.ZSFG),
        ("Sbi", HospitalSystem.ZSFG),
        ("Sir", HospitalSystem.ZSFG),
        ("Sx", HospitalSystem.ZSFG),
        ("Snf", HospitalSystem.ZSFG),
        ("Snf2", HospitalSystem.ZSFG),
        ("Vb", HospitalSystem.VA),
        ("Vir", HospitalSystem.VA),
    ])
    def test_rotation_to_system(self, code, expected):
        assert get_hospital_system(code) == expected

    def test_peds_is_ucsf(self):
        """Peds is hardcoded override — not prefix-based."""
        assert get_hospital_system("Peds") == HospitalSystem.UCSF

    def test_fse_is_ucsf(self):
        assert get_hospital_system("FSE-Abd") == HospitalSystem.UCSF
        assert get_hospital_system("FSE-Bre") == HospitalSystem.UCSF

    def test_non_matching_is_other(self):
        for code in ("Res", "CEP", "AIRP", "LC", "CORE", ""):
            assert get_hospital_system(code) == HospitalSystem.OTHER


# ── 4. FSE Staffing Mapping ─────────────────────────────────────


class TestFSEStaffingMap:
    @pytest.mark.parametrize("suffix,base", [
        ("Abd", "Mai"),
        ("Bre", "Pcbi"),
        ("Che", "Mch"),
        ("Car", "Mch"),
        ("Mus", "Mb"),
        ("Ped", "Peds"),
        ("Nuc", "Mnuc"),
        ("Neu", "Mucic"),
        ("Ult", "Mus"),
        ("IR", "Mir"),
        ("Int", "Mir"),
    ])
    def test_fse_suffix_to_base(self, suffix, base):
        assert FSE_STAFFING_MAP[suffix] == base
        assert fse_to_base_code(f"FSE-{suffix}") == base

    def test_non_fse_unchanged(self):
        assert fse_to_base_code("Mai") == "Mai"
        assert fse_to_base_code("Pcbi") == "Pcbi"


# ── 5. Staffing Minimums ────────────────────────────────────────


class TestStaffingMinimums:
    def test_moffitt_ai(self):
        codes, min_req = ROTATION_MINIMUMS["Moffitt AI"]
        assert codes == {"Mai", "Zai"}
        assert min_req == 3

    def test_zsfg_total(self):
        codes, min_req = ROTATION_MINIMUMS["ZSFG Total"]
        assert min_req == 8
        assert "Ser" in codes and "Smr" in codes and "Sbi" in codes

    def test_moffitt_nucs(self):
        codes, min_req = ROTATION_MINIMUMS["Moffitt Nucs"]
        assert codes == {"Mnuc"}
        assert min_req == 2


# ── 6. Staffing Maximums ────────────────────────────────────────


class TestStaffingMaximums:
    @pytest.mark.parametrize("label,codes,max_val", [
        ("Sx", {"Sx"}, 1),
        ("Snf", {"Snf"}, 1),
        ("Mnf", {"Mnf"}, 1),
        ("Snf2", {"Snf2"}, 1),
        ("PCMB Breast", {"Pcbi"}, 3),
        ("NucMed Total", {"Mnuc"}, 5),
        ("VA MSK", {"Vb"}, 1),
        ("VA IR", {"Vir"}, 1),
        ("Zir", {"Zir"}, 1),
        ("Ser", {"Ser"}, 2),
        ("Mai", {"Mai"}, 5),
        ("Mucic", {"Mucic"}, 6),
    ])
    def test_maximum_values(self, label, codes, max_val):
        assert label in ROTATION_MAXIMUMS
        actual_codes, actual_max = ROTATION_MAXIMUMS[label]
        assert actual_codes == codes
        assert actual_max == max_val


# ── 7. Rotation Year Eligibility ────────────────────────────────


class TestRotationYearEligibility:
    def test_vir_r2_only(self):
        assert _ROTATION_YEAR_ELIGIBILITY["Vir"] == {2}

    def test_sir_r2_only(self):
        assert _ROTATION_YEAR_ELIGIBILITY["Sir"] == {2}

    def test_zir_r3_r4(self):
        assert _ROTATION_YEAR_ELIGIBILITY["Zir"] == {3, 4}

    def test_zai_r2_only(self):
        assert _ROTATION_YEAR_ELIGIBILITY["Zai"] == {2}

    def test_mnct_r1_only(self):
        assert _ROTATION_YEAR_ELIGIBILITY["Mnct"] == {1}

    def test_vnuc_retired(self):
        assert _ROTATION_YEAR_ELIGIBILITY["Vnuc"] == set()

    def test_build_fill_excludes_wrong_year(self):
        """Vir should not appear in R3 fill candidates."""
        r3_candidates = build_fill_candidates(r_year=3)
        assert "Vir" not in r3_candidates
        assert "Sir" not in r3_candidates
        assert "Zai" not in r3_candidates

    def test_build_fill_includes_right_year(self):
        """Zir should appear in R3 fill candidates."""
        r3_candidates = build_fill_candidates(r_year=3)
        assert "Zir" in r3_candidates


# ── 8. NFRules Defaults ─────────────────────────────────────────


class TestNFRulesDefaults:
    def test_r2_mnf_weeks(self):
        rules = NFRules()
        assert rules.r2_mnf_weeks == 2

    def test_r3_max_nf(self):
        rules = NFRules()
        assert rules.r3_max_nf == 3

    def test_r3_limits(self):
        rules = NFRules()
        assert rules.r3_mnf_max == 2
        assert rules.r3_snf2_max == 2

    def test_r4_snf2_weeks(self):
        rules = NFRules()
        assert rules.r4_snf2_weeks == 2

    def test_r4_mnf_default_zero(self):
        rules = NFRules()
        assert rules.r4_mnf_weeks == 0

    def test_min_spacing(self):
        rules = NFRules()
        assert rules.min_spacing_weeks == 4

    def test_shift_eligibility_snf(self):
        rules = NFRules()
        assert rules.shift_eligibility["Snf"] == {2}

    def test_shift_eligibility_mnf(self):
        rules = NFRules()
        assert rules.shift_eligibility["Mnf"] == {2, 3}

    def test_shift_eligibility_snf2(self):
        rules = NFRules()
        assert rules.shift_eligibility["Snf2"] == {3, 4}

    def test_shift_eligibility_sx(self):
        rules = NFRules()
        assert rules.shift_eligibility["Sx"] == {2}

    def test_preferred_pull_rotations(self):
        rules = NFRules()
        assert rules.preferred_pull_rotations == {"Pcmb", "Mb", "Mucic", "Peds", "Mnuc", "Pcbi"}
