"""Phase 2: R2 track assignment (solver-optimized)."""

from __future__ import annotations

from collections import Counter

from schedule_maker.models.resident import Resident
from schedule_maker.models.schedule import ScheduleGrid
from schedule_maker.io.excel_reader import TrackTemplate
from schedule_maker.solver.track_matcher import solve_track_assignment, TrackAssignmentResult

# Rotations that are easiest to displace for Sx/Snf swaps (per goals.md)
_SWAPPABLE_ROTATIONS = {"Pcbi", "Mb", "Mucic", "Peds", "Mnuc", "Mai", "Mch"}
_SX_SNF_CODES = {"Sx", "Snf"}
_STANDARD_SX_PATTERN = ["Sx", "Snf", "Snf", "Sx"]


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

    # Deconflict Sx/Snf for residents sharing the same track
    deconflict_sx_snf(r2s, grid, tracks=tracks)

    return result


def _find_sx_snf_groups(
    schedule: dict[int, str],
    expand: bool = True,
) -> list[list[tuple[int, str]]]:
    """Find contiguous Sx/Snf groups in a resident's schedule.

    Args:
        schedule: week → rotation code mapping
        expand: if True, expand sub-4-week groups to 4 weeks with the standard
                [Sx, Snf, Snf, Sx] pattern (for same-track deconfliction).
                If False, preserve natural group sizes and patterns.

    Returns list of groups, each group is a list of (week, code) tuples.
    """
    sx_snf_weeks = sorted(w for w, c in schedule.items() if c in _SX_SNF_CODES)
    if not sx_snf_weeks:
        return []

    # Step 1: find contiguous Sx/Snf runs
    raw_groups: list[list[int]] = []
    current: list[int] = [sx_snf_weeks[0]]

    for w in sx_snf_weeks[1:]:
        if w == current[-1] + 1:
            current.append(w)
        else:
            raw_groups.append(current)
            current = [w]
    raw_groups.append(current)

    if not expand:
        # Preserve natural sizes and patterns from the schedule
        return [
            [(w, schedule[w]) for w in weeks]
            for weeks in raw_groups
        ]

    # Step 2: expand each group to 4 weeks with standard pattern
    used_weeks: set[int] = set()
    groups: list[list[tuple[int, str]]] = []

    for weeks in raw_groups:
        if len(weeks) >= 4:
            # Already full-size; use standard pattern
            start = weeks[0]
            group = [(start + i, _STANDARD_SX_PATTERN[i]) for i in range(4)]
        else:
            # Expand forward from first week (backward if near end of year)
            start = weeks[0]
            if start + 3 > 52:
                start = max(1, weeks[-1] - 3)
            # Avoid overlapping with already-claimed weeks
            while any(w in used_weeks for w in range(start, start + 4)) and start > 0:
                start -= 1
            group = [(start + i, _STANDARD_SX_PATTERN[i]) for i in range(4)]

        used_weeks.update(w for w, _ in group)
        groups.append(group)

    return groups


def _build_sx_snf_occupancy(
    residents: list[Resident],
    exclude: str | None = None,
) -> dict[str, set[int]]:
    """Build per-code occupancy: {"Sx": {weeks...}, "Snf": {weeks...}}.

    Max staffing is 1 per code per week, so Sx and Snf are independent.
    """
    occ: dict[str, set[int]] = {"Sx": set(), "Snf": set()}
    for r in residents:
        if r.r_year != 2 or r.name == exclude:
            continue
        for w, c in r.schedule.items():
            if c in occ:
                occ[c].add(w)
    return occ


def _find_target_for_group(
    source_pattern: list[str],
    source_weeks: list[int],
    resident: Resident,
    occ: dict[str, set[int]],
    grid: ScheduleGrid,
    placed_sx_snf_weeks: set[int],
    min_spacing: int = 4,
    free_sx: set[int] | None = None,
    free_snf: set[int] | None = None,
) -> int | None:
    """Find best target start week for an Sx/Snf group.

    Prioritizes weeks from free (unassigned) track positions, which are
    guaranteed conflict-free. Falls back to general per-code check.

    Returns the start week, or None if no valid target exists.
    """
    group_len = len(source_pattern)
    source_set = set(source_weeks)

    best_target: int | None = None
    best_score = -1

    for start in range(1, 53 - group_len + 1):
        target_weeks = list(range(start, start + group_len))

        # Target must not overlap with source weeks
        if source_set & set(target_weeks):
            continue

        # Per-code conflict check
        conflict = False
        for i, tw in enumerate(target_weeks):
            if tw in occ[source_pattern[i]]:
                conflict = True
                break
        if conflict:
            continue

        # Target weeks must not already be Sx/Snf for this resident
        if any(resident.schedule.get(w, "") in _SX_SNF_CODES for w in target_weeks):
            continue

        # Spacing from other placed groups
        if min_spacing > 0 and placed_sx_snf_weeks:
            min_dist = min(
                abs(tw - pw) for tw in target_weeks for pw in placed_sx_snf_weeks
            )
            if min_dist < min_spacing:
                continue

        # Score: prioritize free-track positions (bonus 100 per match),
        # then prefer swappable rotations at target
        score = 0
        if free_sx is not None and free_snf is not None:
            for i, tw in enumerate(target_weeks):
                pool = free_sx if source_pattern[i] == "Sx" else free_snf
                if tw in pool:
                    score += 100
        score += sum(
            1 for w in target_weeks
            if resident.schedule.get(w, "") in _SWAPPABLE_ROTATIONS
        )
        if score > best_score:
            best_score = score
            best_target = start

    return best_target


def _swap_group(
    resident: Resident,
    grid: ScheduleGrid,
    source_weeks: list[int],
    source_pattern: list[str],
    target_start: int,
    occ: dict[str, set[int]],
    placed_sx_snf_weeks: set[int],
) -> None:
    """Swap an Sx/Snf group to target weeks, moving displaced rotations back."""
    target_weeks = list(range(target_start, target_start + len(source_pattern)))

    displaced = [(w, resident.schedule.get(w, "")) for w in target_weeks]

    for i, tw in enumerate(target_weeks):
        resident.schedule[tw] = source_pattern[i]
        grid.assign(resident.name, tw, source_pattern[i])

    for i, sw in enumerate(source_weeks):
        resident.schedule[sw] = displaced[i][1]
        grid.assign(resident.name, sw, displaced[i][1])

    for i, sw in enumerate(source_weeks):
        occ[source_pattern[i]].discard(sw)
    for i, tw in enumerate(target_weeks):
        occ[source_pattern[i]].add(tw)
    placed_sx_snf_weeks.update(target_weeks)


def deconflict_sx_snf(
    r2s: list[Resident],
    grid: ScheduleGrid,
    tracks: list[TrackTemplate] | None = None,
) -> None:
    """Move Sx/Snf groups to resolve collisions across all R2 residents.

    Two passes:
    1. Same-track deconfliction: when two residents share a track, move the
       second resident's Sx/Snf groups to non-colliding weeks.
    2. Cross-track deconfliction: detect per-week Sx/Snf overcounting across
       all R2 residents and relocate colliding groups (prefer smaller groups).

    With 13 tracks designed so each week has exactly 1 Sx and 1 Snf, unassigned
    tracks' Sx/Snf positions are guaranteed conflict-free targets. These are
    used as a priority pool for group placement. Falls back to general search
    if the pool is exhausted.
    """
    # Build free-weeks pool: weeks where free tracks have Sx/Snf
    free_sx_weeks: set[int] = set()
    free_snf_weeks: set[int] = set()
    if tracks:
        assigned_tracks = {r.track_number for r in r2s if r.track_number is not None}
        track_map = {t.number: t for t in tracks}
        for tn in sorted(set(track_map) - assigned_tracks):
            weekly = track_map[tn].to_weekly_schedule()
            for w, c in weekly.items():
                if c == "Sx":
                    free_sx_weeks.add(w)
                elif c == "Snf":
                    free_snf_weeks.add(w)

    # --- Pass 1: Same-track deconfliction ---
    track_counts = Counter(r.track_number for r in r2s if r.track_number is not None)
    dup_tracks = {t for t, cnt in track_counts.items() if cnt > 1}

    if dup_tracks:
        to_shift: list[Resident] = []
        for track_num in sorted(dup_tracks):
            pair = [r for r in r2s if r.track_number == track_num]
            pair.sort(key=lambda r: r.name)
            to_shift.append(pair[1])

        for resident in to_shift:
            _relocate_resident_sx_snf(
                resident, r2s, grid, free_sx_weeks, free_snf_weeks,
                label_prefix="same-track",
            )

    # --- Pass 2: Cross-track deconfliction ---
    _deconflict_cross_track(r2s, grid, free_sx_weeks, free_snf_weeks)


def _relocate_resident_sx_snf(
    resident: Resident,
    r2s: list[Resident],
    grid: ScheduleGrid,
    free_sx_weeks: set[int],
    free_snf_weeks: set[int],
    label_prefix: str = "",
) -> None:
    """Relocate all Sx/Snf groups for a single resident to non-colliding weeks."""
    occ = _build_sx_snf_occupancy(r2s, exclude=resident.name)
    groups = _find_sx_snf_groups(resident.schedule)
    if not groups:
        return

    # Strip ALL weeks covered by expanded groups, saving original content
    stripped: dict[int, str] = {}
    for group in groups:
        for w, _pattern_code in group:
            stripped[w] = resident.schedule.get(w, "")
            resident.schedule[w] = ""
            grid.assign(resident.name, w, "")

    groups.sort(key=lambda g: len(g), reverse=True)
    placed: set[int] = set()

    for spacing in (4, 0):
        remaining = []
        for group in groups:
            source_weeks = [w for w, _ in group]
            source_pattern = [c for _, c in group]

            target = _find_target_for_group(
                source_pattern, source_weeks, resident, occ,
                grid, placed, min_spacing=spacing,
                free_sx=free_sx_weeks, free_snf=free_snf_weeks,
            )
            if target is not None:
                _swap_group(
                    resident, grid, source_weeks, source_pattern,
                    target, occ, placed,
                )
                target_weeks = list(range(target, target + len(source_pattern)))
                for i, tw in enumerate(target_weeks):
                    if source_pattern[i] == "Sx":
                        free_sx_weeks.discard(tw)
                    else:
                        free_snf_weeks.discard(tw)
                label = " (relaxed)" if spacing == 0 else ""
                print(
                    f"  Deconflicted [{label_prefix}] {resident.name} track "
                    f"{resident.track_number}: moved {source_pattern} "
                    f"from weeks {source_weeks} → {target_weeks}{label}"
                )
            else:
                remaining.append(group)
        groups = remaining

    # Restore any groups that couldn't be placed
    for group in groups:
        source_weeks = [w for w, _ in group]
        for w, _c in group:
            original = stripped.get(w, "")
            resident.schedule[w] = original
            grid.assign(resident.name, w, original)
        print(
            f"WARNING: Could not deconflict Sx/Snf group at weeks "
            f"{source_weeks} for {resident.name}"
        )


def _deconflict_cross_track(
    r2s: list[Resident],
    grid: ScheduleGrid,
    free_sx_weeks: set[int],
    free_snf_weeks: set[int],
) -> None:
    """Detect and resolve per-week Sx/Snf overcounting across all R2 residents.

    For any week where a code (Sx or Snf) has count > 1, identify the colliding
    residents and relocate the one with the smaller Sx/Snf group. Uses
    expand=False so 2-week partial-A groups are moved as-is rather than
    being inflated to 4-week blocks.
    """
    failed_pairs: set[tuple[str, int]] = set()  # (resident_name, group_start_week)
    max_iterations = 50  # safety limit

    for iteration in range(max_iterations):
        # Build per-week, per-code occupancy
        week_code_residents: dict[str, dict[int, list[Resident]]] = {
            "Sx": {}, "Snf": {},
        }
        for r in r2s:
            for w, c in r.schedule.items():
                if c in week_code_residents:
                    week_code_residents[c].setdefault(w, []).append(r)

        # Find first collision
        collision_found = False
        for code in ("Sx", "Snf"):
            for week, residents_at_week in sorted(week_code_residents[code].items()):
                if len(residents_at_week) <= 1:
                    continue

                # Build candidate list: residents with groups containing this week,
                # sorted by group size (prefer smaller = easier to move)
                candidates: list[tuple[Resident, list[tuple[int, str]]]] = []
                for r in residents_at_week:
                    groups = _find_sx_snf_groups(r.schedule, expand=False)
                    for g in groups:
                        g_weeks = {w for w, _ in g}
                        if week in g_weeks:
                            start_w = g[0][0]
                            if (r.name, start_w) not in failed_pairs:
                                candidates.append((r, g))

                # Sort by group size ascending (smaller first)
                candidates.sort(key=lambda x: len(x[1]))

                for resident, group in candidates:
                    source_weeks = [w for w, _ in group]
                    source_pattern = [c for _, c in group]

                    occ = _build_sx_snf_occupancy(r2s, exclude=resident.name)
                    # Get other placed Sx/Snf weeks for this resident (excluding this group)
                    group_week_set = set(source_weeks)
                    placed = {
                        w for w, c in resident.schedule.items()
                        if c in _SX_SNF_CODES and w not in group_week_set
                    }

                    target = _find_target_for_group(
                        source_pattern, source_weeks, resident, occ,
                        grid, placed, min_spacing=4,
                        free_sx=free_sx_weeks, free_snf=free_snf_weeks,
                    )
                    if target is None:
                        target = _find_target_for_group(
                            source_pattern, source_weeks, resident, occ,
                            grid, placed, min_spacing=0,
                            free_sx=free_sx_weeks, free_snf=free_snf_weeks,
                        )

                    if target is not None:
                        _swap_group(
                            resident, grid, source_weeks, source_pattern,
                            target, occ, placed,
                        )
                        target_weeks = list(range(target, target + len(source_pattern)))
                        for i, tw in enumerate(target_weeks):
                            if source_pattern[i] == "Sx":
                                free_sx_weeks.discard(tw)
                            else:
                                free_snf_weeks.discard(tw)
                        print(
                            f"  Deconflicted [cross-track] {resident.name} track "
                            f"{resident.track_number}: moved {source_pattern} "
                            f"from weeks {source_weeks} → {target_weeks}"
                        )
                        collision_found = True
                        break
                    else:
                        failed_pairs.add((resident.name, source_weeks[0]))

                if collision_found:
                    break
            if collision_found:
                break

        if not collision_found:
            break


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
