"""Phase 26 stage 4 (Task 4, decision L4): autopilot paths that drive a course through its pit lane, computed in the test session
from the built set's line 6 and the same session's runs (nothing stored). Paths are closed loops of (x, z) every PATH_STEP units
for autopilot.lua (`runner.write_centreline`). Modelled on the stage 4 recon's scratch paths (docs/spike/2026-11-phase26-stage4-
recon.md §7: a normal path splices the lane's polyline into line 6, a reverse path is a normal pit run's own trajectory read
backwards joined to line 6 read backwards)."""

from __future__ import annotations

import math

from vrtools.mame.runner import PIT_HANDLER

PATH_STEP = 10.0          # units between path points (autopilot.lua looks VR_AUTOPILOT_LOOKAHEAD points ahead, 6 by default)
LINE_SKIP = 3             # line 6 points left out past the lane's exit, so the path does not double back onto the road it leaves
EXIT_RUN = 4              # points carried on past the lane's exit along its last leg, so the lookahead stays in the lane to its end
ROAD_NEAR = 4.0           # a logged position this near line 6 is on the road (where the normal car left it and came back to it)
ROAD_MARGIN = 20          # logged frames kept beyond those places, so the joins to the road run along it


def resample(points, step: float = PATH_STEP, closed: bool = True) -> list[tuple[float, float]]:
    """Points every `step` units along the polyline `points` (closed: back to its first point; a last point nearer the first than
    half a step is dropped)."""
    pts = list(points) + ([points[0]] if closed else [])
    out, since = [tuple(pts[0])], 0.0                     # since: the length walked since the last point out
    for a, b in zip(pts, pts[1:]):
        length = math.dist(a, b)
        if length == 0:
            continue
        t = step - since
        while t <= length + 1e-9:
            out.append((a[0] + (b[0] - a[0]) * t / length, a[1] + (b[1] - a[1]) * t / length))
            t += step
        since = length - (t - step)
    if closed and len(out) > 1 and math.dist(out[-1], out[0]) < step / 2:
        out.pop()
    return out


def nearest(line, x: float, z: float) -> tuple[int, float]:
    """(index, distance) of the point of `line` nearest (x, z)."""
    k = min(range(len(line)), key=lambda i: (line[i][0] - x) ** 2 + (line[i][1] - z) ** 2)
    return k, math.dist(line[k], (x, z))


def _carry_on(a, b, k: int = EXIT_RUN, step: float = PATH_STEP) -> list[tuple[float, float]]:
    """k points on from b along a -> b, `step` apart."""
    m = math.dist(a, b) or 1.0
    return [(b[0] + (b[0] - a[0]) / m * step * j, b[1] + (b[1] - a[1]) / m * step * j) for j in range(1, k + 1)]


def normal_pit_path(line6, lane) -> list[tuple[float, float]]:
    """A lap through the pit lane in the normal direction: line 6 (the normal entry's road line 6, (x, z) in lap order) from
    LINE_SKIP points past the line point nearest the lane's exit round to the one nearest its mouth, then the lane's polyline
    (`collision.pit_lane_centres`, mouth to exit) and EXIT_RUN points carried on past the exit; resampled every PATH_STEP."""
    line = [(float(x), float(z)) for x, z in line6]
    n = len(line)
    mouth, exit_ = nearest(line, *lane[0])[0], nearest(line, *lane[-1])[0]
    road = [line[(exit_ + LINE_SKIP + k) % n] for k in range((mouth - exit_ - LINE_SKIP) % n + 1)]
    return resample(road + [tuple(p) for p in lane] + _carry_on(lane[-2], lane[-1]))


def green(trajectory) -> int:
    """The index in `trajectory` (pit_log.lua's frames, `runner.PitFrame`) of the green: the clock's first count. ValueError when
    the clock never counts."""
    i = next((i for i in range(1, len(trajectory)) if 0 < trajectory[i].clock < trajectory[i - 1].clock), None)
    if i is None:
        raise ValueError(f"no green: the clock never counts in {len(trajectory)} logged frames")
    return i


def stop_frames(trajectory) -> tuple[int, int]:
    """(trigger, release): the indices in `trajectory` (pit_log.lua's frames, `runner.PitFrame`) of the first frame from the green
    whose handler is PIT_HANDLER and of the first frame after it whose handler is not (before the green, Alpine's PIT START runs
    under the same handler). ValueError when no stop starts or none ends."""
    g = green(trajectory)
    t = next((i for i in range(g, len(trajectory)) if trajectory[i].handler == PIT_HANDLER), None)
    if t is None:
        raise ValueError(f"no stop: the handler is never {PIT_HANDLER:#x} from the green (frame {trajectory[g].frame})")
    r = next((i for i in range(t, len(trajectory)) if trajectory[i].handler != PIT_HANDLER), None)
    if r is None:
        raise ValueError(f"no release: the stop from frame {trajectory[t].frame} lasts to the end of the log")
    return t, r


def reverse_pit_path(trajectory, line6) -> list[tuple[float, float]]:
    """A lap through the pit lane in the reverse direction, from a normal pit run's trajectory (its pit_log.lua frames,
    `runner.PitFrame`, from the race on) and the normal entry's line 6: the normal car's way back to the road after the release
    (to ROAD_MARGIN frames past the first within ROAD_NEAR of line 6), read backwards, takes the reverse car from the road into the
    lane's normal exit and up the lane to the box; its approach (from ROAD_MARGIN frames before the last on line 6 before the
    trigger, through the pit autopilot's drive to the box), read backwards, takes it from the box out through the normal mouth.
    Line 6 read backwards joins the two ends round the lap. Resampled every PATH_STEP."""
    line = [(float(x), float(z)) for x, z in line6]
    n = len(line)
    t, r = stop_frames(trajectory)
    a = t
    while a > 0 and nearest(line, trajectory[a].x, trajectory[a].z)[1] > ROAD_NEAR:
        a -= 1
    a = max(0, a - ROAD_MARGIN)
    b = r
    while b < len(trajectory) - 1 and nearest(line, trajectory[b].x, trajectory[b].z)[1] > ROAD_NEAR:
        b += 1
    b = min(len(trajectory) - 1, b + ROAD_MARGIN)
    approach = [(f.x, f.z) for f in trajectory[a:r]]                   # the road, the lane to the trigger, the pit autopilot to the box
    pitout = [(f.x, f.z) for f in trajectory[r:b + 1]]                 # the box out through the exit to the road
    left, back = nearest(line, *approach[0])[0], nearest(line, *pitout[-1])[0]    # where the normal car left line 6 and came back
    rev = [line[(n - j) % n] for j in range(n)]                        # line 6 read backwards: rev[(n - k) % n] is line[k]
    ra, rb = (n - left) % n, (n - back) % n
    road = [rev[(ra + k) % n] for k in range((rb - ra) % n + 1)]       # from the normal mouth round to the normal exit
    return resample(road + pitout[::-1] + approach[::-1])


def pit_lane(rs, saturn_cue, plan, centreline) -> tuple[list[tuple[float, float]], object, list[list[tuple[float, float]]]]:
    """(the lane's polyline from its mouth, the Saturn course, the lane's tarmac slices as (x, z) polygons) of the converted
    course `plan` (`tencourse.CoursePlan`) as the build places it: `collision.pit_lane_centres` and `pit_lane_polygons` inside
    the course's placement (`tencourse.course_placement` on the original set `rs`, as `tencourse.convert_course` places it), on
    the conversion's `centreline` (`Converted.centreline`)."""
    from vrtools.arcade.tencourse import course_placement, load_saturn_course
    from vrtools.convert.collision import pit_lane_centres, pit_lane_polygons
    from vrtools.convert.geometry import placed
    sat = load_saturn_course(saturn_cue, plan.path)
    pl = course_placement(rs, sat, plan.template, min_coverage=plan.min_coverage, flag_start=plan.flag_start)
    with placed(pl.angle, pl.tx, pl.tz):
        return pit_lane_centres(sat, centreline), sat, [[(c[0], c[2]) for c in poly] for poly in pit_lane_polygons(sat)]
