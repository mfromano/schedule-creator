"""Read data from the Schedule Creation .xlsm workbook."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from schedule_maker.models.resident import Resident, Pathway
from schedule_maker.models.rotation import RotationCode
from schedule_maker.models.schedule import Block


def _str(val) -> str:
    """Safely convert a cell value to string."""
    if val is None:
        return ""
    return str(val).strip()


def _float(val) -> float:
    """Safely convert a cell value to float."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _parse_pathway(esnr: str, esir: str, t32: str, nrdr: str) -> Pathway:
    """Parse pathway flags from 'x' markers in Historical tab."""
    p = Pathway.NONE
    if _str(esnr).lower() == "x":
        p |= Pathway.ESNR
    if _str(esir).lower() == "x":
        p |= Pathway.ESIR
    if _str(t32).lower() == "x":
        p |= Pathway.T32
    if _str(nrdr).lower() == "x":
        p |= Pathway.NRDR
    return p


@dataclass
class TrackTemplate:
    """A track template: ordered list of rotation codes per biweek."""
    number: int
    label: str  # e.g. "1A", "1B" → simplified to just track number
    # List of (block, biweek, rotation_code) tuples
    assignments: list[tuple[int, str, str]] = field(default_factory=list)

    def to_weekly_schedule(self) -> dict[int, str]:
        """Convert biweekly track to weekly schedule.

        Each block has 4 weeks. Biweek A = weeks 1-2, Biweek B = weeks 3-4.
        """
        schedule: dict[int, str] = {}
        for block, biweek, code in self.assignments:
            base_week = (block - 1) * 4 + 1
            if biweek == "A":
                schedule[base_week] = code
                schedule[base_week + 1] = code
            else:  # B
                schedule[base_week + 2] = code
                schedule[base_week + 3] = code
        return schedule


class ExcelReader:
    """Reads all scheduling data from the Schedule Creation .xlsm file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._wb = openpyxl.load_workbook(
            str(self.path), read_only=True, data_only=True, keep_vba=True
        )

    def close(self):
        self._wb.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── Overview ──────────────────────────────────────────────

    def read_academic_year(self) -> int:
        """Read target academic year from Overview tab cell B5."""
        ws = self._wb["Overview"]
        val = ws["B5"].value
        if val is None:
            val = ws["B6"].value  # some versions use B6
        return int(val) if val else 2026

    # ── Key (Rotation Codes) ─────────────────────────────────

    def read_rotation_codes(self) -> list[RotationCode]:
        """Parse the Key tab into RotationCode objects."""
        ws = self._wb["Key"]
        codes = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            code_val = _str(row[0]) if row[0] else None
            if not code_val:
                continue
            section = _str(row[1]) if len(row) > 1 else ""
            label = _str(row[2]) if len(row) > 2 else ""

            rc = RotationCode(
                code=code_val,
                section=section,
                label=label,
            )
            # Parse PGY eligibility (columns D-G or similar)
            if len(row) > 3:
                for i, pgy in enumerate([1, 2, 3, 4], start=3):
                    if len(row) > i and _str(row[i]).lower() in ("x", "yes", "true", "1"):
                        rc.pgy_eligible.add(pgy)
                        if pgy == 1:
                            rc.r1_eligible = True
                        elif pgy == 2:
                            rc.r2_eligible = True
                        elif pgy == 3:
                            rc.r3_eligible = True
                        elif pgy == 4:
                            rc.r4_eligible = True
            codes.append(rc)
        return codes

    # ── Historical (Roster + History) ────────────────────────

    def _detect_historical_layout(self) -> dict:
        """Auto-detect the Historical tab column layout.

        Two known layouts:
          Layout A (2025-2026): A=Current PGY, B=Future PGY, C=Resident, D+=history
          Layout B (2026-2027): A=Current PGY, B=Resident, C+=ESNR/ESIR/T32/NRDR, G+=history

        Returns dict with 'pgy_col', 'name_col', 'has_future_pgy', 'history_start_col',
        and pathway column indices.
        """
        ws = self._wb["Historical"]
        headers = []
        for row in ws.iter_rows(min_row=2, max_row=2, max_col=10, values_only=True):
            headers = [_str(v) for v in row]
            break

        if len(headers) > 1 and "future" in headers[1].lower():
            # Layout A: A=Current PGY, B=Future PGY, C=Resident
            return {
                "has_future_pgy": True,
                "pgy_col": 1,      # Future PGY in column B
                "name_col": 2,     # Resident in column C
                "history_start_col": 3,
                "pathway_cols": None,  # No pathway columns in this layout
            }
        else:
            # Layout B: A=Current PGY, B=Resident, C=ESNR, D=ESIR, E=T32, F=NRDR
            return {
                "has_future_pgy": False,
                "pgy_col": 0,      # Current PGY in column A (will increment by 1)
                "name_col": 1,     # Resident in column B
                "history_start_col": 6,  # Block data starts after pathway cols
                "pathway_cols": {"esnr": 2, "esir": 3, "t32": 4, "nrdr": 5},
            }

    def read_roster(self) -> list[Resident]:
        """Parse the Historical tab to get all residents with PGY.

        Supports two layouts:
          Layout A: Has 'Future PGY' column — use directly.
          Layout B: Only 'Current PGY' — increment by 1 to get target year PGY.

        Target year PGY: PGY-2=R1, PGY-3=R2, PGY-4=R3, PGY-5=R4.
        PGY-1 (interns) and PGY-6+ (graduated) are skipped.
        """
        ws = self._wb["Historical"]
        layout = self._detect_historical_layout()
        residents = []

        max_col = max(layout["name_col"] + 1, 7)
        for row in ws.iter_rows(min_row=3, max_col=max_col, values_only=True):
            raw_pgy = row[layout["pgy_col"]]
            name = _str(row[layout["name_col"]])
            if not name or not raw_pgy:
                continue
            try:
                pgy_int = int(raw_pgy)
            except (ValueError, TypeError):
                continue

            # If no Future PGY column, increment current PGY by 1
            if not layout["has_future_pgy"]:
                pgy_int += 1

            r_year = pgy_int - 1  # PGY-2=R1, PGY-3=R2, etc.
            if r_year < 1 or r_year > 4:
                continue  # Skip interns (PGY-1) and graduated (PGY-6+)

            # Parse name ("Last, First" format)
            parts = name.split(",", 1)
            last = parts[0].strip()
            first = parts[1].strip() if len(parts) > 1 else ""

            res = Resident(
                name=name,
                first_name=first,
                last_name=last,
                pgy=pgy_int,
                r_year=r_year,
            )

            # Parse pathway flags if present in this layout
            if layout["pathway_cols"]:
                pw = layout["pathway_cols"]
                res.pathway = _parse_pathway(
                    _str(row[pw["esnr"]]) if len(row) > pw["esnr"] else "",
                    _str(row[pw["esir"]]) if len(row) > pw["esir"] else "",
                    _str(row[pw["t32"]]) if len(row) > pw["t32"] else "",
                    _str(row[pw["nrdr"]]) if len(row) > pw["nrdr"] else "",
                )

            residents.append(res)

        return residents

    def read_historical_assignments(self, residents: list[Resident]) -> None:
        """Read 4 years of weekly rotation history from Historical tab.

        Updates residents' history dict in-place with cumulative weeks per rotation.
        Auto-detects layout to find the correct name and history start columns.
        """
        ws = self._wb["Historical"]
        layout = self._detect_historical_layout()
        name_col = layout["name_col"]
        history_start = layout["history_start_col"]
        name_to_resident = {r.name: r for r in residents}

        for row in ws.iter_rows(min_row=3, values_only=True):
            name = _str(row[name_col]) if len(row) > name_col else ""
            if name not in name_to_resident:
                continue

            res = name_to_resident[name]
            for col_idx in range(history_start, len(row)):
                code = _str(row[col_idx])
                if code and code not in ("", "0"):
                    res.history[code] = res.history.get(code, 0) + 1

    # ── Historical Tabulation ────────────────────────────────

    def read_historical_tabulation(self, residents: list[Resident]) -> None:
        """Read cumulative rotation weeks from Historical Tabulation tab.

        This is a pre-computed summary that may be more accurate than
        raw weekly counting. Updates resident history in-place.
        """
        ws = self._wb["Historical Tabulation"]

        # Read header row to identify rotation columns
        headers = []
        for cell in ws[1]:
            headers.append(_str(cell.value))

        # Find resident rows and map columns
        for row in ws.iter_rows(min_row=2, values_only=True):
            name = _str(row[1]) if len(row) > 1 else ""
            matching = [r for r in residents if r.name == name]
            if not matching:
                continue
            res = matching[0]

            # Tabulation columns contain section totals
            for i, header in enumerate(headers):
                if i < 2 or not header:
                    continue
                val = _float(row[i]) if len(row) > i else 0
                if val > 0:
                    res.history[header] = val

    # ── Transfers ────────────────────────────────────────────

    def read_transfers(self) -> dict[str, dict[str, float]]:
        """Read transfer credit weeks from Transfers tab.

        Returns {name: {credit_type: weeks}}.
        """
        ws = self._wb["Transfers"]
        transfers = {}
        headers = []
        for row in ws.iter_rows(max_row=1, values_only=True):
            headers = [_str(v) for v in row]
            break

        for row in ws.iter_rows(min_row=2, values_only=True):
            name = _str(row[0])
            if not name:
                continue
            credits = {}
            for i in range(1, len(headers)):
                if len(row) > i and row[i]:
                    credits[headers[i]] = _float(row[i])
            transfers[name] = credits

        return transfers

    # ── R1/R2 Tracks ─────────────────────────────────────────

    def _read_tracks(self, tab_name: str) -> list[TrackTemplate]:
        """Read track templates from R1 Tracks or R2 Tracks tab.

        The track grid uses a rotation formula with stride 2:
          position = ((track_num - 1) + (block - 1) * 2) % seq_len + 1

        The base rotation sequence is in column C (rows 7+).
        The formula-populated track columns (G+) are often only partially
        cached by openpyxl, so we derive all 13 blocks from the base
        sequence directly.
        """
        ws = self._wb[tab_name]

        # --- Determine track count from header labels ---
        header_row = list(ws.iter_rows(min_row=6, max_row=6, values_only=False))[0]
        track_numbers = set()
        for i, cell in enumerate(header_row):
            if i < 6:
                continue
            val = _str(cell.value)
            if not val:
                continue
            if val[-1] in ("A", "B") and val[:-1].isdigit():
                track_numbers.add(int(val[:-1]))
            # Stop at the first non-track label (e.g. "MISSING", "Section")
            elif not val.isdigit():
                break

        if not track_numbers:
            return []
        track_count = max(track_numbers)

        # --- Read base rotation sequence from column C ---
        # Each position has A and B biweek codes
        base_seq: dict[int, dict[str, str]] = {}  # {position: {"A": code, "B": code}}
        for row in ws.iter_rows(min_row=7, max_row=60, max_col=3, values_only=True):
            pos = row[0]
            biweek = _str(row[1])
            code = _str(row[2])
            if pos is None or biweek not in ("A", "B") or not code:
                continue
            try:
                pos_int = int(pos)
            except (ValueError, TypeError):
                continue
            if pos_int not in base_seq:
                base_seq[pos_int] = {}
            base_seq[pos_int][biweek] = code

        if not base_seq:
            return []

        seq_len = max(base_seq.keys())
        num_blocks = 13
        stride = 2

        # --- Derive each track's schedule for all 13 blocks ---
        tracks = [TrackTemplate(number=i + 1, label=f"Track {i + 1}")
                  for i in range(track_count)]

        for tnum in range(1, track_count + 1):
            for block in range(1, num_blocks + 1):
                pos = ((tnum - 1) + (block - 1) * stride) % seq_len + 1
                codes = base_seq.get(pos, {})
                for biweek in ("A", "B"):
                    code = codes.get(biweek, "")
                    if code:
                        tracks[tnum - 1].assignments.append((block, biweek, code))

        return tracks

    def read_r1_tracks(self) -> list[TrackTemplate]:
        return self._read_tracks("R1 Tracks")

    def read_r2_tracks(self) -> list[TrackTemplate]:
        return self._read_tracks("R2 Tracks")

    # ── R3-4 Recs ────────────────────────────────────────────

    def read_r34_recs(self, residents: list[Resident]) -> None:
        """Read R3-4 Recs tab and populate residents' recommended_blocks, deficient_sections, and pathways.

        Row 2 = headers: A=R#, B=Name, C=ESNR, D=ESIR, E=T32, F=NRDR,
                         G=FSE/Top Sections, H=Deficient Sections,
                         I=Vnuc, J=Smr, K=Ser, L=Sbi, M=Mnuc, N=Pcbi,
                         O=Mch, P=Mai, Q=Mus, R=Mb, S=Mucic, T=Peds,
                         U=Zir, V=Mir, W=Total
        """
        ws = self._wb["R3-4 Recs"]
        name_to_resident = {r.name: r for r in residents}

        # Column mapping (0-indexed from row 2 headers)
        rec_cols = {
            8: "Vnuc", 9: "Smr", 10: "Ser", 11: "Sbi", 12: "Mnuc",
            13: "Pcbi", 14: "Mch", 15: "Mai", 16: "Mus", 17: "Mb",
            18: "Mucic", 19: "Peds", 20: "Zir", 21: "Mir",
        }

        for row in ws.iter_rows(min_row=3, values_only=True):
            name = _str(row[1]) if len(row) > 1 else ""
            if name not in name_to_resident:
                continue

            res = name_to_resident[name]

            # Parse pathway flags from columns C-F
            res.pathway = _parse_pathway(
                _str(row[2]) if len(row) > 2 else "",  # C = ESNR
                _str(row[3]) if len(row) > 3 else "",  # D = ESIR
                _str(row[4]) if len(row) > 4 else "",  # E = T32
                _str(row[5]) if len(row) > 5 else "",  # F = NRDR
            )

            res.deficient_sections = [
                s.strip() for s in _str(row[7]).split(",") if s.strip()
            ] if len(row) > 7 and row[7] else []

            for col_idx, rotation in rec_cols.items():
                if len(row) > col_idx and row[col_idx]:
                    val = _float(row[col_idx])
                    if val > 0:
                        res.recommended_blocks[rotation] = val

    # ── Preferences tab ──────────────────────────────────────

    def read_preferences_tab(self, residents: list[Resident]) -> None:
        """Read the Preferences tab from the .xlsm (manually entered data).

        Headers at row 2: R#, Name, ESNR, ESIR, T32, NRDR, then section exposures,
        then per-class preference columns, then No Call/Vac/Acad/Leave (col AA = index 26).
        """
        ws = self._wb["Preferences"]
        name_to_resident = {r.name: r for r in residents}

        for row in ws.iter_rows(min_row=3, values_only=True):
            name = _str(row[1]) if len(row) > 1 else ""
            if name not in name_to_resident:
                continue

            res = name_to_resident[name]

            # No Call/Vac/Acad/Leave is in column AA (index 26)
            if len(row) > 26 and row[26]:
                raw = _str(row[26])
                # These are comma-separated MM/DD dates
                res.no_call.raw_dates = []
                for part in raw.split(","):
                    part = part.strip()
                    if part:
                        # Store as raw strings; will parse with dateutil later
                        pass  # handled by prefs_parser

    # ── Base Schedule structure ───────────────────────────────

    def read_base_schedule_structure(self) -> dict:
        """Read the Base Schedule tab structure (dates, resident rows, staffing rows).

        Returns metadata about the grid layout.
        """
        ws = self._wb["Base Schedule"]

        # Row 1-5: headers with block IDs, biweek labels, dates
        # Read date row (row 4 or 5) to get weekly dates
        dates = {}
        for row in ws.iter_rows(min_row=4, max_row=5, values_only=False):
            for cell in row:
                if hasattr(cell, "column") and cell.value and hasattr(cell.value, "year"):
                    dates[cell.column] = cell.value

        # Read resident name/PGY from rows 6+
        resident_rows = {}
        for row_idx, row in enumerate(
            ws.iter_rows(min_row=6, max_row=100, max_col=3, values_only=True),
            start=6,
        ):
            pgy = row[0] if row else None
            name = _str(row[1]) if len(row) > 1 and row[1] else ""
            if name and pgy:
                resident_rows[name] = row_idx

        # Read staffing constraint rows (101-151)
        staffing_rows = {}
        for row_idx, row in enumerate(
            ws.iter_rows(min_row=101, max_row=151, max_col=3, values_only=True),
            start=101,
        ):
            label = _str(row[0]) if row else ""
            if not label and len(row) > 1:
                label = _str(row[1])
            if label:
                staffing_rows[label] = row_idx

        return {
            "dates": dates,
            "resident_rows": resident_rows,
            "staffing_rows": staffing_rows,
        }

    def read_base_schedule_staffing(self) -> list[dict]:
        """Read staffing constraint rows from Base Schedule (rows 101-151)."""
        ws = self._wb["Base Schedule"]
        constraints = []

        for row in ws.iter_rows(min_row=101, max_row=151, values_only=True):
            label = _str(row[0]) or _str(row[1]) if len(row) > 1 else ""
            if not label:
                continue
            # Weekly staffing counts (columns D onwards = index 3+)
            weekly = [_float(row[i]) if len(row) > i else 0 for i in range(3, min(len(row), 55))]
            constraints.append({"label": label, "weekly": weekly})

        return constraints

    # ── NF recs ──────────────────────────────────────────────

    def read_nf_recs(self) -> dict:
        """Read NF recommendation census from NF recs tab."""
        ws = self._wb["NF recs"]
        recs = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            pgy = _str(row[0]) if row[0] else ""
            if not pgy:
                continue
            recs[pgy] = {
                "values": [_float(row[i]) if len(row) > i else 0 for i in range(1, 8)]
            }
        return recs

    # ── Night Float tab structure ────────────────────────────

    def read_night_float_structure(self) -> dict:
        """Read Night Float tab structure (similar to Base Schedule)."""
        ws = self._wb["Night Float"]

        resident_rows = {}
        for row_idx, row in enumerate(
            ws.iter_rows(min_row=6, max_row=100, max_col=3, values_only=True),
            start=6,
        ):
            name = _str(row[1]) if len(row) > 1 and row[1] else ""
            if name:
                resident_rows[name] = row_idx

        return {"resident_rows": resident_rows}
