"""Fitting smooth curves to a polyline, so that a stroke's outline is curves rather than samples.

**Why this is not a cosmetic concern.** The outline expansion offsets a *sampled* centreline, so its boundary comes out
as a polyline whose facets are `span_length / resolution` long -- 6.14 drawing units at the default, which is 65 pixels
at 10x zoom and visible as corners in an audit render. But the visible corner is the smaller half of the problem. The
deliverable of this project is a file an artist opens in Illustrator, SAI or Animate, and **an artist's file is curves
here**: 129 `L` commands is not *parameterization close to how artists would draw*, which is Metzger's criterion, and
it is also 116 numbers to describe a shape whose own record stores 58.

The representation is a **chain of cubic Béziers**, and a straight segment is stored as a cubic too -- with its control
points at the thirds -- so that there is one kind of segment everywhere and no tag to get wrong. The cost is a handful
of bytes on the two end caps.

**Nothing here knows about strokes.** It fits points; `core.outline()` decides which points. That keeps it testable
against its own stated property -- the maximum deviation from the input polyline -- rather than against a picture.
"""

from __future__ import annotations

import math
from typing import Sequence

Point = tuple[float, float]
Cubic = tuple[Point, Point, Point, Point]

# How close the least-squares fit has to be before it is accepted, as a fraction of the extent of the points it is
# fitting. Used by `fit_chain` when the caller has no opinion; `core` has one and passes it.
DEFAULT_ERROR = 0.0015


def chord_lengths(points: Sequence[Point]) -> list[float]:
    """Cumulative chord length, normalised to 0..1. The parameterisation the fit is solved against.

    Chord length rather than index: samples are not evenly spaced along the curve, so treating them as if they were
    would put the same weight on a 0.5-unit step and a 26-unit one. This project has already been bitten by exactly
    that -- the tremor's frequency was a property of the sample spacing -- and the same mistake here would bias the
    fit towards whichever part of the curve happened to be sampled most densely.
    """
    out = [0.0]
    for i in range(1, len(points)):
        out.append(out[-1] + math.dist(points[i - 1], points[i]))
    total = out[-1]
    if total <= 0:
        return [i / max(1, len(points) - 1) for i in range(len(points))]
    return [u / total for u in out]


def cubic_at(seg: Cubic, t: float) -> Point:
    """One point on a cubic Bézier."""
    mt = 1.0 - t
    a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
    return (a * seg[0][0] + b * seg[1][0] + c * seg[2][0] + d * seg[3][0],
            a * seg[0][1] + b * seg[1][1] + c * seg[2][1] + d * seg[3][1])


def line_segment(a: Point, b: Point) -> Cubic:
    """A straight line as a cubic, which is what keeps every segment the same shape."""
    return (a, (a[0] + (b[0] - a[0]) / 3.0, a[1] + (b[1] - a[1]) / 3.0),
            (a[0] + 2.0 * (b[0] - a[0]) / 3.0, a[1] + 2.0 * (b[1] - a[1]) / 3.0), b)


def _normalise(v: Point) -> Point:
    length = math.hypot(v[0], v[1])
    if length == 0:
        return (0.0, 0.0)
    return (v[0] / length, v[1] / length)


def _end_tangents(points: Sequence[Point]) -> tuple[Point, Point]:
    left = _normalise((points[1][0] - points[0][0], points[1][1] - points[0][1]))
    right = _normalise((points[-2][0] - points[-1][0], points[-2][1] - points[-1][1]))
    if left == (0.0, 0.0):
        left = _normalise((points[-1][0] - points[0][0], points[-1][1] - points[0][1]))
    if right == (0.0, 0.0):
        right = (-left[0], -left[1])
    return left, right


def _generate_bezier(points: Sequence[Point], u: Sequence[float], t0: Point, t1: Point) -> Cubic:
    """Least-squares fit of one cubic with the end points and end tangents pinned.

    Schneider's formulation (Graphics Gems, 1990). The two interior control points are the only free parameters and
    they enter linearly, so this is a 2x2 solve per call rather than an iteration.
    """
    n = len(points)
    first, last = points[0], points[-1]
    c00 = c01 = c11 = x0 = x1 = 0.0
    a = [[0.0, 0.0] for _ in range(n)]
    for i in range(n):
        mt = 1.0 - u[i]
        b0, b1, b2, b3 = mt ** 3, 3 * mt * mt * u[i], 3 * mt * u[i] * u[i], u[i] ** 3
        a[i][0] = b1 * t0[0]
        a[i][1] = b1 * t0[1]
        a2x, a2y = b2 * t1[0], b2 * t1[1]
        c00 += a[i][0] * a[i][0] + a[i][1] * a[i][1]
        c01 += a[i][0] * a2x + a[i][1] * a2y
        c11 += a2x * a2x + a2y * a2y
        tmp = (points[i][0] - (first[0] * (b0 + b1) + last[0] * (b2 + b3)),
               points[i][1] - (first[1] * (b0 + b1) + last[1] * (b2 + b3)))
        x0 += a[i][0] * tmp[0] + a[i][1] * tmp[1]
        x1 += a2x * tmp[0] + a2y * tmp[1]
    det = c00 * c11 - c01 * c01
    alpha0 = alpha1 = 0.0
    if det != 0.0:
        alpha0 = (x0 * c11 - c01 * x1) / det
        alpha1 = (c00 * x1 - x0 * c01) / det
    # A negative control-point distance means the solve has put the handles behind their own anchor, which makes a
    # loop; the fallback is the Wu/Barsky heuristic -- a third of the chord -- which is always sane.
    if alpha0 < 0.0 or alpha1 < 0.0:
        span = math.dist(first, last)
        alpha0 = alpha1 = span / 3.0
    return (first, (first[0] + t0[0] * alpha0, first[1] + t0[1] * alpha0),
            (last[0] + t1[0] * alpha1, last[1] + t1[1] * alpha1), last)


def _max_error(points: Sequence[Point], seg: Cubic, u: Sequence[float]) -> tuple[float, int]:
    """The worst distance from an input point to the fitted curve, and where it happens."""
    worst, split = 0.0, len(points) // 2
    for i in range(1, len(points) - 1):
        d = math.dist(points[i], cubic_at(seg, u[i]))
        if d >= worst:
            worst, split = d, i
    return worst, split


def _reparameterise(points: Sequence[Point], u: Sequence[float], seg: Cubic) -> list[float]:
    """Newton-Raphson on the distance from each point to the curve, which is what makes the fit tight.

    Without this the fit is as good as the chord-length guess and no better; with it the same number of segments
    reaches roughly an order of magnitude less error, which is the difference between a tolerance that is usable and
    one that forces a split.
    """
    out = []
    for i, p in enumerate(points):
        t = u[i]
        for _ in range(4):
            q = cubic_at(seg, t)
            # derivative of the cubic, for the Newton step
            mt = 1.0 - t
            dx = 3 * mt * mt * (seg[1][0] - seg[0][0]) + 6 * mt * t * (seg[2][0] - seg[1][0]) \
                + 3 * t * t * (seg[3][0] - seg[2][0])
            dy = 3 * mt * mt * (seg[1][1] - seg[0][1]) + 6 * mt * t * (seg[2][1] - seg[1][1]) \
                + 3 * t * t * (seg[3][1] - seg[2][1])
            ddx = 6 * mt * (seg[2][0] - 2 * seg[1][0] + seg[0][0]) + 6 * t * (seg[3][0] - 2 * seg[2][0] + seg[1][0])
            ddy = 6 * mt * (seg[2][1] - 2 * seg[1][1] + seg[0][1]) + 6 * t * (seg[3][1] - 2 * seg[2][1] + seg[1][1])
            numerator = (q[0] - p[0]) * dx + (q[1] - p[1]) * dy
            denominator = dx * dx + dy * dy + (q[0] - p[0]) * ddx + (q[1] - p[1]) * ddy
            if denominator == 0.0:
                break
            t -= numerator / denominator
        out.append(min(1.0, max(0.0, t)))
    return out


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def distance_to_polyline(p: Point, points: Sequence[Point]) -> float:
    if len(points) == 1:
        return math.dist(p, points[0])
    return min(_point_segment_distance(p, points[i], points[i + 1]) for i in range(len(points) - 1))


def _excursion(seg: Cubic, points: Sequence[Point], u: Sequence[float]) -> float:
    """How far the curve strays from the polyline **between** the input points.

    **This is the check whose absence let a fit bulge 50 units out of a shape while every measurement said zero.**
    `_max_error` asks whether each input point is near the curve; a cubic with its handles flung out past the anchors
    can satisfy that completely and still leave the hull entirely. The failure is not hypothetical or rare: expanding
    a closed 5-point square produced a segment from (378,102) to (301,179) with handles at (435,157) and (347,226),
    and `deviation` reported 0.0000 for it, because the bulging part lies between samples.

    Compared against the *local* input segment rather than the whole polyline, which is what makes it cheap enough to
    run on every candidate: parameter `t` and chord length agree closely enough that the corresponding segment is the
    one between `points[i]` and `points[i+1]`.
    """
    worst = 0.0
    for i in range(len(points) - 1):
        lo, hi = u[i], u[i + 1]
        if hi <= lo:
            continue
        for k in range(1, 4):
            t = lo + (hi - lo) * k / 4.0
            worst = max(worst, _point_segment_distance(cubic_at(seg, t), points[i], points[i + 1]))
    return worst


def _fit(points: Sequence[Point], t0: Point, t1: Point, error: float, depth: int = 0) -> list[Cubic]:
    if len(points) == 2:
        return [line_segment(points[0], points[1])]
    u = chord_lengths(points)
    seg = _generate_bezier(points, u, t0, t1)
    worst, split = _max_error(points, seg, u)
    if worst < error and _excursion(seg, points, u) < error:
        return [seg]
    # Try harder before giving up on this span: the first fit is only as good as the chord-length guess.
    if worst < error * 4.0:
        for _ in range(4):
            u = _reparameterise(points, u, seg)
            seg = _generate_bezier(points, u, t0, t1)
            worst, split = _max_error(points, seg, u)
            if worst < error and _excursion(seg, points, u) < error:
                return [seg]
    if split <= 0 or split >= len(points) - 1 or depth > 12:
        # **Give up honestly rather than return a fit that breaks the promise.** Every polyline is exactly
        # representable by its own segments, so this path cannot exceed the tolerance -- whereas returning `seg` here
        # would mean `fit_chain` sometimes violated the one property it exists to have, which is the failure mode this
        # project keeps finding in its own checks. It is reachable: a 3-unit-wide, 30-unit-tall zigzag fails to
        # converge by splitting and measured 17.9 units of deviation against a requested 0.2 before this branch
        # existed.
        return [line_segment(points[i], points[i + 1]) for i in range(len(points) - 1)]
    middle = _normalise((points[split - 1][0] - points[split + 1][0],
                         points[split - 1][1] - points[split + 1][1]))
    if middle == (0.0, 0.0):
        middle = t0
    left = _fit(points[:split + 1], t0, middle, error, depth + 1)
    right = _fit(points[split:], (-middle[0], -middle[1]), t1, error, depth + 1)
    return left + right


def fit_chain(points: Sequence[Point], error: float = 0.0) -> list[Cubic]:
    """A chain of cubics through `points`, each within `error` of it.

    `error` of zero or less means `DEFAULT_ERROR` times the extent of the points, so that a caller who only wants
    "smooth" does not have to know the drawing's scale.
    """
    points = [(float(x), float(y)) for x, y in points]
    if len(points) < 2:
        return []
    if len(points) == 2:
        return [line_segment(points[0], points[1])]
    if error <= 0:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        error = DEFAULT_ERROR * max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    t0, t1 = _end_tangents(points)
    return _fit(points, t0, t1, error)


def distance_to_chain(p: Point, chain: Sequence[Cubic], coarse: int = 16, refine: int = 30) -> float:
    """Distance from a point to the nearest point **on** the chain, not to the nearest sample of it.

    **The distinction is the whole function and the first version got it wrong.** Sampling each segment into a dense
    polyline and taking the nearest vertex is much easier to write, and it reports the distance to the *sampling*, so
    its floor is the sample spacing: a straight line fitted with one cubic -- which for a straight line is exact --
    measured 5.0 units of "error" on a 245-unit span, and a circle measured 5.05. Correct code, reported as broken,
    by a verification helper that could not have passed. Same shape of mistake as the audit's first zoom test.

    A coarse scan brackets the nearest point, then a ternary search refines it on the interval; the distance function
    along one cubic is well behaved once bracketed.
    """
    best = float('inf')
    for seg in chain:
        def d(t: float) -> float:
            return math.dist(p, cubic_at(seg, t))
        values = [d(k / coarse) for k in range(coarse + 1)]
        k = min(range(len(values)), key=lambda i: values[i])
        lo, hi = max(0.0, (k - 1) / coarse), min(1.0, (k + 1) / coarse)
        for _ in range(refine):
            m1 = lo + (hi - lo) / 3.0
            m2 = hi - (hi - lo) / 3.0
            if d(m1) < d(m2):
                hi = m2
            else:
                lo = m1
        best = min(best, d((lo + hi) / 2.0))
    return best


def deviation(points: Sequence[Point], chain: Sequence[Cubic], samples: int = 16,
              **kwargs) -> float:
    """**Both directions.** The largest distance in either direction between the polyline and the curve.

    This is what `fit_chain` promises, and it is asserted directly rather than inferred from a picture. **It is
    two-sided because one side is not a bound.** The first version asked only whether every input point was near the
    curve, and a fit that bulged 50 units out of a closed square satisfied that completely -- the hull lies between
    samples, where no input point can see it. A promise about a curve has to constrain the curve, not just its
    relationship to the points it was fitted through.
    """
    if not chain:
        return float('inf')
    forward = max(distance_to_chain(p, chain, **kwargs) for p in points)
    backward = 0.0
    for seg in chain:
        for k in range(samples + 1):
            backward = max(backward, distance_to_polyline(cubic_at(seg, k / samples), points))
    return max(forward, backward)


def chain_to_path(chain: Sequence[Cubic], precision: int = 2) -> str:
    """The chain as SVG path data, **without** the closing `Z` -- the caller decides whether the subpath closes."""
    if not chain:
        return ''
    fmt = '%%.%df' % precision
    parts = ['M ' + (fmt + ' ' + fmt) % chain[0][0]]
    for seg in chain:
        parts.append('C ' + ' '.join((fmt + ' ' + fmt) % p for p in seg[1:]))
    return ' '.join(parts)


def sample(chain: Sequence[Cubic], per_segment: int = 16) -> list[Point]:
    """The chain as a dense polyline, for a renderer that cannot take curves."""
    out: list[Point] = []
    for seg in chain:
        for k in range(per_segment):
            out.append(cubic_at(seg, k / per_segment))
    if chain:
        out.append(chain[-1][3])
    return out
