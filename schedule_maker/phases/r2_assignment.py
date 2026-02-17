"""Phase 2: R2 track assignment (solver-optimized)."""

from __future__ import annotations

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.io.excel_reader import TrackTemplate
from schedule_maker.solver.track_matcher import solve_track_assignment, TrackAssignmentResult


def assign_r2_tracks(
    residents: list[Resident],
    tracks: list[TrackTemplate],
    grid: ScheduleGrid,
    max_rank: int | None = None,
) -> TrackAssignmentResult:
    """Assign R2 residents to tracks using OR-Tools solver.

    Minimizes total rank penalty based on resident preferences.

    Args:
        residents: R2 residents only
        tracks: R2 track templates
        grid: schedule grid to write to
        max_rank: optional hard limit on worst allowed rank

    Returns:
        TrackAssignmentResult with assignments and metrics
    """
    r2s = [r for r in residents if r.r_year == 2]

    result = solve_track_assignment(
        residents=r2s,
        num_tracks=len(tracks),
        max_rank=max_rank,
    )

    if not result.feasible:
        print(f"WARNING: R2 track assignment infeasible (status: {result.status})")
        return result

    # Apply assignments
    track_map = {t.number: t for t in tracks}
    for name, track_num in result.assignments.items():
        res = next(r for r in r2s if r.name == name)
        track = track_map[track_num]
        res.track_number = track_num
        weekly = track.to_weekly_schedule()
        for week, code in weekly.items():
            grid.assign(res.name, week, code)
            res.schedule[week] = code

    return result


def print_r2_assignment_matrix(
    residents: list[Resident],
    num_tracks: int,
) -> str:
    """Generate the track ranking matrix described in goals.md.

    Shows # people ranking each track at each position.
    """
    r2s = [r for r in residents if r.r_year == 2]
    lines = []
    header = f"{'Track':<10}" + "".join(f"{'Rank ' + str(i):<10}" for i in range(1, num_tracks + 1))
    lines.append(header)
    lines.append("-" * len(header))

    for track_num in range(1, num_tracks + 1):
        counts = []
        for rank in range(1, num_tracks + 1):
            count = sum(
                1 for r in r2s
                if r.track_prefs and r.track_prefs.rankings.get(track_num) == rank
            )
            counts.append(count)
        row = f"Track {track_num:<4}" + "".join(f"{c:<10}" for c in counts)
        lines.append(row)

    return "\n".join(lines)
