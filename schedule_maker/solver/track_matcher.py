"""OR-Tools CP-SAT solver for track assignment (R2 optimization)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from schedule_maker.models.resident import Resident


@dataclass
class TrackAssignmentResult:
    """Result of a track assignment optimization."""
    assignments: dict[str, int]  # resident_name → track_number
    total_rank_penalty: int
    per_resident: dict[str, dict] = field(default_factory=dict)
    # per_resident[name] = {"track": N, "rank": R, "penalty": P}
    feasible: bool = True
    status: str = ""


def solve_track_assignment(
    residents: list[Resident],
    num_tracks: int,
    max_rank: int | None = None,
) -> TrackAssignmentResult:
    """Solve optimal 1:1 resident→track assignment minimizing total rank penalty.

    Uses OR-Tools CP-SAT for the assignment problem.

    Args:
        residents: list of residents with track_prefs.rankings populated
        num_tracks: number of available tracks (typically 15)
        max_rank: optional hard constraint on maximum allowed rank

    Returns:
        TrackAssignmentResult with optimal assignments
    """
    n = len(residents)

    model = cp_model.CpModel()

    # Decision variables: x[i][j] = 1 if resident i gets track j
    x = {}
    for i in range(n):
        for j in range(1, num_tracks + 1):
            x[i, j] = model.new_bool_var(f"x_{i}_{j}")

    # Constraint: each resident gets exactly one track
    for i in range(n):
        model.add(sum(x[i, j] for j in range(1, num_tracks + 1)) == 1)

    # Constraint: each track gets limited residents
    # If n > num_tracks, allow up to ceil(n/num_tracks) per track
    max_per_track = (n + num_tracks - 1) // num_tracks  # ceiling division
    for j in range(1, num_tracks + 1):
        model.add(sum(x[i, j] for i in range(n)) <= max_per_track)

    # Optional: max rank constraint
    if max_rank is not None:
        for i, res in enumerate(residents):
            if res.track_prefs and res.track_prefs.rankings:
                for j in range(1, num_tracks + 1):
                    rank = res.track_prefs.rankings.get(j, num_tracks)
                    if rank > max_rank:
                        model.add(x[i, j] == 0)

    # Objective: minimize total rank penalty
    # rank 1 = 0 penalty, rank 2 = 1, ..., rank N = N-1
    # Unranked tracks get max penalty
    penalties = []
    for i, res in enumerate(residents):
        for j in range(1, num_tracks + 1):
            if res.track_prefs and res.track_prefs.rankings:
                rank = res.track_prefs.rankings.get(j, num_tracks)
            else:
                rank = num_tracks  # no preference = worst rank
            penalty = rank - 1
            penalties.append(penalty * x[i, j])

    model.minimize(sum(penalties))

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    status = solver.solve(model)

    result = TrackAssignmentResult(
        assignments={},
        total_rank_penalty=0,
        feasible=status in (cp_model.OPTIMAL, cp_model.FEASIBLE),
        status=solver.status_name(status),
    )

    if result.feasible:
        for i, res in enumerate(residents):
            for j in range(1, num_tracks + 1):
                if solver.value(x[i, j]) == 1:
                    rank = (res.track_prefs.rankings.get(j, num_tracks)
                            if res.track_prefs and res.track_prefs.rankings
                            else num_tracks)
                    penalty = rank - 1
                    result.assignments[res.name] = j
                    result.total_rank_penalty += penalty
                    result.per_resident[res.name] = {
                        "track": j,
                        "rank": rank,
                        "penalty": penalty,
                    }
                    break

    return result
