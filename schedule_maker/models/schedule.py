"""Schedule grid and block definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class Block:
    """A 4-week scheduling block."""
    number: int          # 1-13
    start_date: date
    end_date: date

    @property
    def weeks(self) -> list[tuple[date, date]]:
        """Return (monday, friday) pairs for each week in the block."""
        result = []
        current = self.start_date
        # Find first Monday on or after start
        while current.weekday() != 0:  # 0 = Monday
            current += timedelta(days=1)
        while current <= self.end_date:
            friday = current + timedelta(days=4)
            result.append((current, min(friday, self.end_date)))
            current += timedelta(days=7)
        return result

    @property
    def num_weeks(self) -> int:
        return len(self.weeks)


def compute_blocks(academic_year_start: int) -> list[Block]:
    """Compute 13 blocks for the academic year starting July 1 of the given year.

    Logic from goals.md:
    - If July 1 is Mon: NF starts last Sunday in June, Block 1 = 4 weeks
    - If July 1 is Tue/Wed: NF starts last Sunday in June, Block 1 = few days less than 4 weeks
    - If July 1 is Thu/Fri: NF starts first Sunday in July, Block 1 = few days more than 4 weeks
    - If July 1 is Sat/Sun: NF starts first Sunday in July, Block 1 = 4 weeks

    In practice, blocks start on Sundays and we use the dates from the spreadsheet.
    This function computes approximate 4-week blocks aligned to Sundays.
    """
    july1 = date(academic_year_start, 7, 1)
    dow = july1.weekday()  # 0=Mon, 6=Sun

    # Determine NF/block start date (a Sunday)
    if dow <= 2:  # Mon, Tue, Wed → last Sunday in June
        days_since_sunday = (dow + 1) % 7
        start = july1 - timedelta(days=days_since_sunday)
    else:  # Thu, Fri, Sat, Sun → first Sunday in July (or July 1 if Sunday)
        if dow == 6:  # Sunday
            start = july1
        else:
            days_to_sunday = 6 - dow
            start = july1 + timedelta(days=days_to_sunday)

    june30_next = date(academic_year_start + 1, 6, 30)

    blocks = []
    current = start
    for i in range(1, 14):
        block_start = current
        if i < 13:
            block_end = block_start + timedelta(days=27)  # 4 weeks = 28 days - 1
            current = block_end + timedelta(days=1)
        else:
            # Block 13 extends to June 30
            block_end = june30_next
        blocks.append(Block(number=i, start_date=block_start, end_date=block_end))

    return blocks


@dataclass
class ScheduleGrid:
    """The master schedule grid: residents × weeks.

    Stores rotation assignments as a dict of (resident_name, week_number) → rotation_code.
    Week numbers are 1-based (week 1 = first week of Block 1).
    """
    blocks: list[Block] = field(default_factory=list)
    # (resident_name, week_number) → rotation_code
    assignments: dict[tuple[str, int], str] = field(default_factory=dict)
    # Night float overlay: (resident_name, week_number) → NF code
    nf_assignments: dict[tuple[str, int], str] = field(default_factory=dict)

    @property
    def total_weeks(self) -> int:
        if not self.blocks:
            return 52
        return sum(b.num_weeks for b in self.blocks)

    def assign(self, resident_name: str, week: int, code: str) -> None:
        self.assignments[(resident_name, week)] = code

    def assign_nf(self, resident_name: str, week: int, code: str) -> None:
        self.nf_assignments[(resident_name, week)] = code

    def get(self, resident_name: str, week: int) -> str:
        """Get effective assignment (NF overrides base)."""
        nf = self.nf_assignments.get((resident_name, week))
        if nf:
            return nf
        return self.assignments.get((resident_name, week), "")

    def get_base(self, resident_name: str, week: int) -> str:
        """Get base schedule assignment (ignoring NF)."""
        return self.assignments.get((resident_name, week), "")

    def get_week_assignments(self, week: int) -> dict[str, str]:
        """Get all resident assignments for a given week."""
        result = {}
        for (name, w), code in self.assignments.items():
            if w == week:
                result[name] = code
        # Apply NF overlay
        for (name, w), code in self.nf_assignments.items():
            if w == week:
                result[name] = code
        return result

    def get_resident_schedule(self, resident_name: str) -> dict[int, str]:
        """Get full schedule for one resident."""
        result = {}
        for (name, w), code in self.assignments.items():
            if name == resident_name:
                result[w] = code
        for (name, w), code in self.nf_assignments.items():
            if name == resident_name:
                result[w] = code
        return result

    def week_to_block(self, week: int) -> int:
        """Convert week number to block number."""
        return (week - 1) // 4 + 1

    def block_to_weeks(self, block: int) -> range:
        """Convert block number to week range."""
        start = (block - 1) * 4 + 1
        return range(start, start + 4)

    def count_rotation_weeks(self, resident_name: str, code: str) -> int:
        """Count weeks a resident is assigned to a specific rotation."""
        count = 0
        for (name, w), c in self.assignments.items():
            if name == resident_name and c == code:
                count += 1
        return count

    def get_section_staffing(self, week: int, rotation_codes: set[str] | None = None) -> int:
        """Count residents assigned to given rotation codes in a week."""
        assignments = self.get_week_assignments(week)
        if rotation_codes is None:
            return len(assignments)
        return sum(1 for code in assignments.values() if code in rotation_codes)
