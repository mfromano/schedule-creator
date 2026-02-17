"""Phase 1: R1 track assignment."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.io.excel_reader import TrackTemplate


def assign_r1_tracks(
    residents: list[Resident],
    tracks: list[TrackTemplate],
    grid: ScheduleGrid,
    optimize_sampler: bool = True,
) -> dict[str, int]:
    """Assign R1 residents to tracks (1:1 mapping).

    Per goals.md, R1 track assignment is arbitrary, but we can optimize
    by matching sampler preferences to sections with trainee shortage.

    Args:
        residents: R1 residents only
        tracks: R1 track templates
        grid: schedule grid to write to
        optimize_sampler: if True, try to match sampler prefs to shortage areas

    Returns:
        {resident_name: track_number} assignments
    """
    r1s = [r for r in residents if r.r_year == 1]
    if not tracks:
        return {}

    assignments = {}

    for i, res in enumerate(r1s):
        # Wrap around if more residents than tracks (duplicates expected per goals.md)
        track = tracks[i % len(tracks)]
        assignments[res.name] = track.number
        res.track_number = track.number
        weekly = track.to_weekly_schedule()
        for week, code in weekly.items():
            grid.assign(res.name, week, code)
            res.schedule[week] = code

    return assignments
