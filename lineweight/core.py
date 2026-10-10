#!/usr/bin/env python3
"""Weighted linework without a tablet: a pressure model, and strokes expanded into filled outlines.

    python -m lineweight --out strokes.svg
    python -m lineweight --fit reference.png

**The problem.** A vector stroke has one width from end to end. Anything drawn with vector strokes therefore looks
diagrammatic next to anything drawn by hand, because a hand varies its pressure: thin at the start of a movement,
heavier through the middle, thin again as it lifts, lighter through a fast run and lighter still through a sharp
turn. An LLM asked to produce linework inherits exactly this problem, and cannot feel pressure to fix it.

So pressure is **modelled rather than measured**, from what is observable about a line: how fast it is going, how
sharply it turns, how near it is to either end, and a slow noise underneath. Those four effects are enough for
linework that reads as drawn rather than computed.

**What pressure does in a program that has it**, and therefore what this reproduces: it changes the width of the
stroke (the dominant effect), its opacity and flow, the spacing of the dabs, and a little colour jitter. Those are
the parameters of a brush, so a brush here is those numbers and two curves -- and nothing about any particular
application.

**Calibration, which is the interesting half.** The model's numbers should not be a matter of taste. `--fit` measures
a real drawing: the distribution of ink across its rows and columns, which is the appearance a brush's curves have to
reproduce. Draw a test sheet of strokes at known pressures in whatever tool you use, measure it, and fit the brush to
it. That is the only honest way to reverse-engineer a pressure setting from its results, since the hand that made
them is not available.

**The boundary.** This is not knowing how to press. It is arithmetic that produces lines with weight, taper and
hand-noise -- enough for vector linework, and no substitute for a person.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import re
from typing import NamedTuple

from . import curve, roles
from .curve import Cubic

# A brush is the same set of numbers a tablet tool exposes, and nothing more.
#
# **`taper_in` and `taper_out` are LENGTHS, in multiples of the brush's own width.** They used to be fractions of the
# stroke's total arc length, which was wrong in a way that only shows up when stroke lengths differ: a fraction makes
# the taper scale with the stroke, so the same brush produced a 6 px entry on a 40 px stroke and a 640 px entry on a
# 4000 px one, a hundredfold spread. A nib does not work that way -- its taper is a fixed distance it travels while
# pressure builds, and it is the same distance whether the stroke is long or short.
#
# The unit is the width multiple rather than pixels because that is the only calibration available, and the anchor is
# a **ratio**, which is scale-free. The measured one is a 丸ペン: **0.35 mm nib with 入り and 抜き set to 5.0 mm**
# (漫画の教科書シリーズ No.02, 萌えキャラの上手な描き方), i.e. a taper **14.3x the nib width**.
#
# **All four brushes use that single measured total, and differ only in how it splits between entry and exit**, which
# is carried over from their previous proportions. An earlier attempt at this scaled each brush's old *fraction* by the
# same factor instead, which gave the 22 px `wash` a 590 px entry -- longer than most strokes, so every wash was
# nothing but taper. Blindly rescaling numbers whose unit had just changed is the same mistake as hand-computing an
# offset, and it was caught by the existing tests rather than by reading it back.
#
# **Only the 14.3x ratio is measured. The split between 入り and 抜き is not.**
BRUSHES: dict[str, dict[str, float]] = {
    # name:            width  opacity taper_in taper_out spacing  speed   corner  noise  wobble
    'fine': {'width': 2.0, 'opacity': 1.0, 'taper_in': 6.0, 'taper_out': 8.3, 'spacing': 0.56,
             'speed': 0.35, 'corner': 0.40, 'noise': 0.06, 'wobble': 0.30, 'curve': 1.15},
    'ink': {'width': 6.5, 'opacity': 1.0, 'taper_in': 5.4, 'taper_out': 8.9, 'spacing': 0.56,
            'speed': 0.22, 'corner': 0.30, 'noise': 0.05, 'wobble': 0.26, 'curve': 0.85},
    'pencil': {'width': 4.0, 'opacity': 0.75, 'taper_in': 6.1, 'taper_out': 8.2, 'spacing': 0.56,
               'speed': 0.40, 'corner': 0.45, 'noise': 0.22, 'wobble': 0.38, 'curve': 1.00, 'grain': 0.35},
    # **Spacing is measured, not chosen.** Sweeping it per brush and counting how many separate runs of ink a
    # single straight stroke leaves shows all four staying continuous to 0.8 of a diameter and breaking at
    # 1.0, so every brush sits at 0.56 -- a measured value with the margin left in, rather than a number
    # that merely looked reasonable and had no effect until the raster compositor arrived.
    'wash': {'width': 22.0, 'opacity': 0.35, 'taper_in': 6.1, 'taper_out': 8.2, 'spacing': 0.56,
             'speed': 0.15, 'corner': 0.20, 'noise': 0.10, 'wobble': 0.14, 'curve': 0.70, 'grain': 0.45},
}

# **How far a fitted outline curve may sit from the exact offset, as a multiple of the brush width.**
#
# The obvious way to choose this is "small enough to be invisible", and that is the wrong criterion here, because it
# would be satisfied by a tolerance far larger than it needs to be. The binding constraint is the hand tremor: the
# sideways nudge the wobble model applies is about **0.045 of the width** (measured, and the smallest brush's is
# 0.024), and a tolerance at that scale would let the fit **smooth the hand out of the drawing** -- removing the exact
# thing this library exists to produce. So the tolerance is set below the smallest tremor rather than below the eye:
# 0.01 of the width, which is 17% of the ink brush's tremor.
#
# It is not free. At this tolerance a real spine fits to ~0.56 cubics per point, and a cubic costs six numbers against
# a line's two, so the path data grows to roughly 1.7x what the polyline cost. **An earlier note in TODO claimed curve
# fitting would shrink the file at the same time; that was wrong**, and the measurement is in the commit. The tremor is
# genuine high-frequency content and any faithful representation has to carry it.
OUTLINE_ERROR = 0.01

# How thin a taper is allowed to get at its very tip, as a fraction of full width. A 丸ペン's 抜き runs out to a point,
# but a rasterised stroke that reaches zero width has no pixels at its ends and reads as a broken line, so it stops
# short of the limit. This constant is **not calibrated** -- it is a floor that exists for a rendering reason.
TAPER_TIP = 0.25


def catmull(points: list[tuple[float, float]], samples: int) -> list[tuple[float, float]]:
    """A smooth path through the points. A hand does not draw polylines."""
    if len(points) < 2:
        return list(points)
    extended = [points[0]] + list(points) + [points[-1]]
    out: list[tuple[float, float]] = []
    for i in range(len(points) - 1):
        p0, p1, p2, p3 = extended[i], extended[i + 1], extended[i + 2], extended[i + 3]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


def pressures(path: list[tuple[float, float]], brush: dict[str, float], seed: int) -> list[float]:
    """**The hand model.** Four effects, each of which is a thing a real tablet records."""
    rng = random.Random(seed)
    n = len(path)
    if n < 2:
        return [1.0] * n
    lengths = [math.dist(path[i], path[i + 1]) for i in range(n - 1)]
    total = sum(lengths) or 1.0
    # Taper lengths, in pixels, resolved once: they are properties of the nib and the document's scale, not of where
    # along the stroke the hand happens to be.
    tin = brush['taper_in'] * brush['width']
    tout = brush['taper_out'] * brush['width']
    walked = 0.0
    out: list[float] = []
    noise_state = 0.0
    for i in range(n):
        # 1. speed: a fast stroke presses less. A long straight run reads as fast.
        speed = 0.0
        if 0 < i < n - 1:
            speed = min(1.0, (lengths[i - 1] + lengths[i]) / (2 * total / n) / 4.0)
        # 2. corner: a sharp turn slows the hand and lifts it, so the line thins
        corner = 0.0
        if 1 < i < n - 1:
            a = math.atan2(path[i][1] - path[i - 1][1], path[i][0] - path[i - 1][0])
            b = math.atan2(path[i + 1][1] - path[i][1], path[i + 1][0] - path[i][0])
            d = abs((b - a + math.pi) % (2 * math.pi) - math.pi)
            corner = min(1.0, d / (math.pi / 2))
        # 4. a slow drift, which is what makes a line look drawn rather than computed
        noise_state = noise_state * 0.86 + rng.uniform(-1, 1) * 0.14
        grain_state = rng.uniform(-1, 1)
        taper = 1.0
        # **Tapers are measured in distance travelled, not in fraction of the stroke.** A nib's entry is a fixed
        # length it spends building pressure, so one brush has to give the same taper on a short stroke and a long
        # one. As a fraction of arc length it did the opposite: 6 px of entry on a 40 px stroke, 640 px on a 4000 px
        # one. The two ends combine with `min` rather than if/elif, so a stroke shorter than its own tapers gets
        # both -- which is what a pen does when it never reaches full pressure.
        #
        # The `> 0` guards are not decoration: **a zero taper is a real brush setting**, and dividing by it is how
        # this function first broke. A brush that asks for no taper gets none.
        if tin > 0 and walked < tin:
            taper = min(taper, TAPER_TIP + (1.0 - TAPER_TIP) * (walked / tin))
        remaining = total - walked
        if tout > 0 and remaining < tout:
            # `walked` accumulates from floating-point lengths and can land a hair past `total` on the last sample,
            # which would put the tip of the taper below its own floor. Clamping here keeps the profile monotone.
            taper = min(taper, TAPER_TIP + (1.0 - TAPER_TIP) * (max(0.0, remaining) / tout))
        p = taper * (1.0 - brush['speed'] * speed) * (1.0 - brush['corner'] * corner)
        p *= 1.0 + brush['noise'] * noise_state + brush['noise'] * 0.55 * grain_state
        out.append(max(0.18, min(1.0, p)))
        walked += lengths[i] if i < len(lengths) else 0.0
    return out


def polygon_to_path(points: list[tuple[float, float]]) -> str:
    """A closed polygon as SVG path data. **The only place an outline's coordinates become text**, so that the text and
    the points cannot describe different shapes."""
    if not points:
        return ''
    return 'M %.2f %.2f ' % points[0] + ' '.join('L %.2f %.2f' % p for p in points[1:]) + ' Z'


# **Above this ratio, a vertex gets a round join instead of a displaced point.**
#
# The offset point at a vertex belongs at `half / cos(turn/2)` along the bisector of the two segment normals. As the
# turn approaches a reversal that goes to infinity, and the *direction* stops meaning anything before the length does:
# at 165 degrees the central difference between the neighbouring samples lies nearly **along the path** rather than
# across it, so the "offset" is displaced forward. That is what the chisel tip on a double-back stroke was -- measured
# on a hairpin, the right spine's apex point sat at x=252.44 with the path's own maximum at 250, and the stroke ended
# in a 4.88-unit straight segment coming to a **point** instead of a cap.
#
# A miter limit is the standard answer. It is stated as the ratio rather than as an angle because the ratio is what the
# geometry actually produces, and 4.0 puts the switch at a turn of 151 degrees -- so gentle corners and the right
# angles a drawing is full of keep exactly the outline they had, and only a genuine doubling-back changes.
MITER_LIMIT = 4.0

# How finely a round join is sampled. Over-fine on purpose: the arc is fitted to cubics afterwards with a tolerance of
# a hundredth of the brush width, and a semicircle of radius 3.25 needs about nine points to be within that, so this
# leaves margin rather than being tuned.
JOIN_STEPS = 12


def _unit(dx: float, dy: float) -> tuple[float, float] | None:
    length = math.hypot(dx, dy)
    return None if length == 0 else (dx / length, dy / length)


def _needs_round_join(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Whether the turn from direction `a` to direction `b` is sharp enough that a displaced point is meaningless."""
    cosine = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
    return math.sqrt(max(0.0, (1.0 + cosine) / 2.0)) < 1.0 / MITER_LIMIT


def _arc(cx: float, cy: float, radius: float, start: tuple[float, float],
         through: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    """Points along a round join from `start` to `end`, sweeping the way that passes through `through`.

    All three are unit directions. The sweep is measured as two signed angles rather than as a shortest arc, because
    at a reversal the two ends are 180 degrees apart and "the short way round" is ambiguous exactly where this matters.
    """
    def signed(u, v):
        return math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])
    total = signed(start, through) + signed(through, end)
    base = math.atan2(start[1], start[0])
    return [(cx + math.cos(base + total * (k / float(JOIN_STEPS))) * radius,
             cy + math.sin(base + total * (k / float(JOIN_STEPS))) * radius)
            for k in range(JOIN_STEPS + 1)]


def outline_points(path: list[tuple[float, float]], width: list[float]
                   ) -> list[tuple[float, float]]:
    """**A stroke with weight is a filled shape, not a stroke.** SVG cannot vary a stroke's width, so the width
    profile is turned into an outline: offset the path to both sides by half the local width and fill the result.

    This is the same operation Illustrator performs when a variable-width stroke is expanded, done here so that the
    output stays plain SVG with no dependence on any application.

    Returns points rather than a `d` string because a path string can only be painted, and this shape also has to be
    **handed to something else that will paint it** -- `audit.compare_fillers` gives these exact points to cairo. That
    is the reason for the split and it is load-bearing: if the referee had to recover the polygon by parsing the `d`
    string, it would be checking a rounded re-reading of the geometry rather than the geometry.

    **The halves can differ in length**, because a round join contributes several points to each. Only the
    concatenation is meaningful, and `outline_chain` splits it at `len(path)` -- which is the one place that has to
    know the structure, and the reason it cannot simply take every other point.
    """
    left, right = outline_spines(path, width)
    return left + list(reversed(right))


def outline_spines(path: list[tuple[float, float]], width: list[float]
                   ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """The two sides of a weighted stroke, each walked along the path.

    Separate from `outline_points` because **the two are not the same length once there are round joins**, so a caller
    that concatenates them and then splits at `len(path)` is splitting in the wrong place. `outline_chain` used to do
    exactly that, and it is the sort of break that produces a shape which is plausible and subtly wrong rather than an
    error.
    """
    if len(path) < 2:
        return [], []
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(path):
        prev = path[max(0, i - 1)]
        nxt = path[min(len(path) - 1, i + 1)]
        dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        half = max(0.35, width[i] / 2.0)
        incoming = _unit(x - prev[0], y - prev[1]) if i > 0 else None
        outgoing = _unit(nxt[0] - x, nxt[1] - y) if i < len(path) - 1 else None
        if incoming and outgoing and _needs_round_join(incoming, outgoing):
            near = (-incoming[1], incoming[0])
            far = (-outgoing[1], outgoing[0])
            left.extend(_arc(x, y, half, near, incoming, far))
            right.extend(_arc(x, y, half, (-near[0], -near[1]), incoming, (-far[0], -far[1])))
            continue
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))
    return left, right


def outline(path: list[tuple[float, float]], width: list[float], error: float = 0.0) -> str:
    """The filled shape a weighted stroke has, as path data -- **as curves, not as a polyline**.

    The expansion offsets a *sampled* centreline, so its boundary used to come out as one straight segment per sample:
    facets of `span_length / resolution`, which is 6.14 drawing units at the default and 65 pixels at 10x zoom, and
    visible as corners in an audit render. The deliverable of this project is a file an artist opens in Illustrator,
    and an artist's file is curves here -- see `curve.py` for why a polyline is the wrong representation rather than
    merely a rough one.
    """
    return outline_path(path, width, error)


def outline_error(width: list[float]) -> float:
    """The fit tolerance for a stroke with this width profile.

    **`max`, not `mean`, and not the extent of the geometry.** The tolerance is a fraction of the *full* stroke width,
    so taking the maximum is the conservative reading of a profile that tapers towards its tips; deriving it from the
    extent of the points instead would make the same stroke fit differently at different sizes and differently again
    depending on how the caller happened to scale it. One function, called from everywhere, so that `outline()` and
    `from_record()` cannot disagree about what shape a stroke is -- they did for one revision, which is how this came
    to be a function.
    """
    return OUTLINE_ERROR * (max(width) if width else 1.0)


def outline_chain(path: list[tuple[float, float]], width: list[float],
                  error: float = 0.0) -> list['Cubic']:
    """The closed boundary of a weighted stroke as a chain of cubics -- **the shape that actually ships**.

    Both spines are fitted, and the two end caps stay straight lines because that is what they are. The chain closes
    at the end (its last point is its first), so it is written with a trailing `Z`.

    `error` of zero or less means `outline_error(width)`. The tolerance has to stay **below the hand tremor** rather
    than below the eye, or the fit smooths the hand out of the drawing -- see `OUTLINE_ERROR`.
    """
    left, right = outline_spines(path, width)
    if not left:
        return []
    if error <= 0:
        error = outline_error(width)
    rightwards = list(reversed(right))          # the right spine, running back along the path
    chain = curve.fit_chain(left, error)
    chain.append(curve.line_segment(left[-1], rightwards[0]))
    chain.extend(curve.fit_chain(rightwards, error))
    return chain


def outline_path(path: list[tuple[float, float]], width: list[float], error: float = 0.0) -> str:
    """`outline_chain` as SVG path data, closed."""
    chain = outline_chain(path, width, error)
    if not chain:
        return ''
    return curve.chain_to_path(chain) + ' Z'


# **How far the hand travels between two draws of the wobble noise**, in brush widths.
#
# The tremor used to advance one step per *sample*, which made its wavelength a property of `resolution` and of how long
# each control-point span happened to be. Measured on one stroke, the reversal spacing along the spine halved every time
# `resolution` doubled -- 17.6 units at resolution 7 down to 1.1 at 112 -- which is 1.5 samples at every setting and
# therefore per-sample noise and nothing else; the amplitude stayed at 0.045 of the width throughout, so the hand got
# faster without getting shakier. Worse, `catmull` takes a fixed *count* of samples per span rather than a fixed
# spacing, so a stroke with one long span and one short one had sample spacing varying by **64x inside itself** and got
# two different hands.
#
# Driving the noise by arc length makes the tremor a function of the drawing instead of of the sampling. One brush
# width is the value that reproduces the old behaviour at the nominal case -- resolution 14 with the ~80-unit spans a
# face at working size produces, where the old spacing was 5.8 units and the fast wavelength measured 8.8. It is in
# width multiples because that is the unit the rest of the brush is already in.
TREMBLE_STEP = 1.0


def tremble(path: list[tuple[float, float]], amount: float, seed: int = 0,
            step: float = 0.0) -> list[tuple[float, float]]:
    """Nudges a path sideways the way a hand does, because a line that is exactly where it was aimed is a plot.

    **Two frequencies, and the difference between them is the whole effect.** A slow wander is the arm moving and a
    fast jitter is the wrist; a line with only the slow one looks drugged, one with only the fast one looks nervous,
    and both together look drawn. The nudge is perpendicular to the path, because a hand shakes across its direction
    of travel rather than along it. This is the opposite of what a drawing program's stabiliser does.

    **The amount is a fraction of the brush's width rather than a distance in pixels**, and that is a correction
    rather than a preference: half a pixel is invisible on a six-pixel ink line and enormous on a two-pixel pen, so
    an absolute number means something different on every brush. As a fraction, the same number means the same thing
    everywhere -- measured across the four brushes, a wobble of about a quarter of the width.

    **`step` is the distance the hand travels between two draws of the noise, and it is why this function has a
    length in it at all.** Both frequencies are in the coefficients below and the coefficients are per *step*, so the
    step is what fixes their wavelengths in the drawing; without one they were fixed in samples and the hand changed
    speed whenever `resolution` did. See `TREMBLE_STEP`.
    """
    if amount <= 0 or len(path) < 3:
        return list(path)
    step = float(step) if step > 0 else 1.0

    # Arc length along the path. This is the parameter the noise is a function of; the samples' own spacing is not
    # consulted, which is the point -- `catmull` spaces them unevenly and by span length.
    travelled = [0.0]
    for i in range(1, len(path)):
        travelled.append(travelled[-1] + math.dist(path[i - 1], path[i]))

    # Draw the two processes on a uniform grid in arc length first, then read them back wherever the samples landed.
    rng = random.Random(seed * 7919 + 13)
    slow, fast = [0.0], [0.0]
    for _ in range(int(travelled[-1] / step) + 2):
        slow.append(slow[-1] * 0.90 + rng.uniform(-1, 1) * 0.10)
        fast.append(fast[-1] * 0.45 + rng.uniform(-1, 1) * 0.55)

    out: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(path):
        u = travelled[i] / step
        k = min(int(u), len(slow) - 2)
        frac = u - k
        drift = slow[k] + (slow[k + 1] - slow[k]) * frac
        jitter = fast[k] + (fast[k + 1] - fast[k]) * frac
        prev = path[max(0, i - 1)]
        nxt = path[min(len(path) - 1, i + 1)]
        dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        offset = amount * (drift * 1.7 + jitter * 0.6)
        out.append((x + nx * offset, y + ny * offset))
    return out


def stroke(points: list[tuple[float, float]], brush_name: str, seed: int = 0,
           colour: str = '', resolution: int = 14) -> tuple[str, float]:
    """One stroke: path in, filled outline plus its mean opacity out."""
    return from_record(stroke_record(points, brush_name, seed, colour, resolution))



# -------------------------------------------------------------------------------------------------- path parsing
TOKEN_RE = re.compile(r'([MmLlHhVvCcSsQqTtAaZz])|(-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)')


def _sample_quad(p0, c, p1, samples):
    out = []
    for i in range(1, samples + 1):
        t = i / samples
        mt = 1 - t
        out.append((mt * mt * p0[0] + 2 * mt * t * c[0] + t * t * p1[0],
                    mt * mt * p0[1] + 2 * mt * t * c[1] + t * t * p1[1]))
    return out


def _sample_cubic(p0, c1, c2, p1, samples):
    out = []
    for i in range(1, samples + 1):
        t = i / samples
        mt = 1 - t
        a, b, cc, dd = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
        out.append((a * p0[0] + b * c1[0] + cc * c2[0] + dd * p1[0],
                    a * p0[1] + b * c1[1] + cc * c2[1] + dd * p1[1]))
    return out


def _sample_arc(p0, rx, ry, rotation, large_arc, sweep, p1, samples):
    """An SVG elliptical arc, walked as an ellipse and sampled.

    **This is the one command that cannot be handled by interpolation**, because the spec defines it by its
    endpoints rather than its centre, and the two possible ellipses through those endpoints are chosen by two flags.
    Everything below is that conversion (F.6.5 of the SVG specification) done in full, including the degenerate
    cases: a zero radius is a straight line, and endpoints that coincide describe no arc at all.
    """
    if rx == 0 or ry == 0:
        return [p1]
    if abs(p0[0] - p1[0]) < 1e-12 and abs(p0[1] - p1[1]) < 1e-12:
        return []
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rotation % 360.0)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx2, dy2 = (p0[0] - p1[0]) / 2.0, (p0[1] - p1[1]) / 2.0
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2
    # scale the radii up if they are too small to span the endpoints, which the spec requires
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large_arc == sweep:
        factor = -factor
    cxp = factor * rx * y1p / ry
    cyp = -factor * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (p0[0] + p1[0]) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (p0[1] + p1[1]) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        norm = math.hypot(ux, uy) * math.hypot(vx, vy)
        if norm == 0:
            return 0.0
        value = max(-1.0, min(1.0, dot / norm))
        a = math.acos(value)
        return -a if (ux * vy - uy * vx) < 0 else a

    theta1 = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    out = []
    # at least two samples whatever the arc is, so a wide arc is never reduced to a single chord
    steps = max(2, int(samples * max(1.0, abs(delta) / (math.pi / 2))))
    for i in range(1, steps + 1):
        theta = theta1 + delta * i / steps
        ex, ey = rx * math.cos(theta), ry * math.sin(theta)
        out.append((cx + cos_p * ex - sin_p * ey, cy + sin_p * ex + cos_p * ey))
    return out


def parse_path(d: str, samples: int = 10) -> list[list[tuple[float, float]]]:
    """Turns a path string into polylines, which is what a stroke outline needs.

    **The whole command set, because dropping what a generator writes is the worst available behaviour.** This
    parser once handled only `M`, `L`, `Q` and `Z` and skipped the rest, with a test asserting the skip so it looked
    intentional. It was not a safe choice: a language model asked to draw writes cubics and arcs constantly, and every
    one of them was silently discarded -- a shape whose outline came partly from a curve lost that part and kept the
    rest, so the result looked like a drawing rather than like a failure. Rendering it was the only way to notice.

    Relative commands are honoured too, which is the quieter half of the same bug: `m` and `l` were uppercased and
    then read as absolute, so a perfectly ordinary path placed everything after its first move at the wrong
    coordinates. Curves are sampled rather than kept, because an outline has to be a polyline to be offset.
    """
    tokens = TOKEN_RE.findall(d)
    polys: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    nums: list[float] = []
    command = ''
    start: tuple[float, float] = (0.0, 0.0)   # the subpath's first point, for `Z` and for relative moves
    cursor: tuple[float, float] = (0.0, 0.0)
    last_control: tuple[float, float] | None = None

    def flush(close: bool = False) -> None:
        nonlocal current
        if close and len(current) >= 2:
            current = current + [current[0]]
        if len(current) >= 2:
            polys.append(current)
        current = []

    def relative() -> bool:
        return command.islower()

    for letter, number in tokens:
        if letter:
            command = letter
            nums = []
            if letter in 'Zz':
                flush(close=True)
                cursor = start
            continue
        nums.append(float(number))
        cmd = command.upper()
        upper = not relative()
        ox, oy = cursor if not upper else (0.0, 0.0)

        if cmd == 'M' and len(nums) >= 2:
            flush()
            cursor = (nums[0] + ox, nums[1] + oy)
            start = cursor
            current = [cursor]
            nums = []
            # subsequent pairs after a move are line-tos, as the spec says
            command = 'L' if upper else 'l'
        elif cmd == 'L' and len(nums) >= 2:
            cursor = (nums[0] + ox, nums[1] + oy)
            current.append(cursor)
            nums = []
            last_control = None
        elif cmd == 'H' and len(nums) >= 1:
            cursor = (nums[0] + ox, cursor[1])
            current.append(cursor)
            nums = []
            last_control = None
        elif cmd == 'V' and len(nums) >= 1:
            cursor = (cursor[0], nums[0] + oy)
            current.append(cursor)
            nums = []
            last_control = None
        elif cmd == 'C' and len(nums) >= 6:
            c1 = (nums[0] + ox, nums[1] + oy)
            c2 = (nums[2] + ox, nums[3] + oy)
            end = (nums[4] + ox, nums[5] + oy)
            if not current:
                current = [cursor]
            current.extend(_sample_cubic(cursor, c1, c2, end, samples))
            cursor, last_control = end, c2
            nums = []
        elif cmd == 'S' and len(nums) >= 4:
            # the first control is the reflection of the previous one about the cursor
            c1 = (2 * cursor[0] - last_control[0], 2 * cursor[1] - last_control[1]) if last_control else cursor
            c2 = (nums[0] + ox, nums[1] + oy)
            end = (nums[2] + ox, nums[3] + oy)
            if not current:
                current = [cursor]
            current.extend(_sample_cubic(cursor, c1, c2, end, samples))
            cursor, last_control = end, c2
            nums = []
        elif cmd == 'Q' and len(nums) >= 4:
            c1 = (nums[0] + ox, nums[1] + oy)
            end = (nums[2] + ox, nums[3] + oy)
            if not current:
                current = [cursor]
            current.extend(_sample_quad(cursor, c1, end, samples))
            cursor, last_control = end, c1
            nums = []
        elif cmd == 'T' and len(nums) >= 2:
            c1 = (2 * cursor[0] - last_control[0], 2 * cursor[1] - last_control[1]) if last_control else cursor
            end = (nums[0] + ox, nums[1] + oy)
            if not current:
                current = [cursor]
            current.extend(_sample_quad(cursor, c1, end, samples))
            cursor, last_control = end, c1
            nums = []
        elif cmd == 'A' and len(nums) >= 7:
            end = (nums[5] + ox, nums[6] + oy)
            if not current:
                current = [cursor]
            current.extend(_sample_arc(cursor, nums[0], nums[1], nums[2], int(nums[3]) != 0, int(nums[4]) != 0,
                                       end, samples))
            cursor, last_control = end, None
            nums = []
    flush()
    return [p for p in polys if len(p) >= 2]


TRANSFORM_ITEM_RE = re.compile(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)')
NUMBER_RE = re.compile(r'-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')


def _mat_mul(m: tuple[float, ...], n: tuple[float, ...]) -> tuple[float, ...]:
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def parse_transform(text: str) -> tuple[float, float, float, float, float, float]:
    """An SVG `transform` attribute as a 2x3 matrix `(a, b, c, d, e, f)`.

    **Without this, a weighted outline is drawn in the wrong place.** An outline is generated from the numbers in the
    path, and those numbers are in the path's own coordinates: a path inside `<g transform="translate(20,10)
    scale(2)">` is not where its digits say it is. Generate the contour from those digits, nest it back inside the
    same group, and the transform is applied to it a second time -- the contour lands displaced and wrongly sized,
    which reads as a bad drawing rather than as a bug. Transforms are composed in document order here, as SVG applies
    them, and the same matrix scales the brush so the line's weight stays proportional to the artwork.
    """
    matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for kind, body in TRANSFORM_ITEM_RE.findall(text or ''):
        parts = [float(v) for v in NUMBER_RE.findall(body)]
        if kind == 'matrix' and len(parts) >= 6:
            step = tuple(parts[:6])
        elif kind == 'translate':
            step = (1.0, 0.0, 0.0, 1.0, parts[0] if parts else 0.0, parts[1] if len(parts) > 1 else 0.0)
        elif kind == 'scale':
            sx = parts[0] if parts else 1.0
            sy = parts[1] if len(parts) > 1 else sx
            step = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif kind == 'rotate':
            angle = math.radians(parts[0] if parts else 0.0)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            rotation = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(parts) >= 3:
                # rotate about a point is translate-to-origin, rotate, translate-back
                cx, cy = parts[1], parts[2]
                step = _mat_mul((1.0, 0.0, 0.0, 1.0, cx, cy),
                                _mat_mul(rotation, (1.0, 0.0, 0.0, 1.0, -cx, -cy)))
            else:
                step = rotation
        elif kind == 'skewX':
            step = (1.0, 0.0, math.tan(math.radians(parts[0] if parts else 0.0)), 1.0, 0.0, 0.0)
        elif kind == 'skewY':
            step = (1.0, math.tan(math.radians(parts[0] if parts else 0.0)), 0.0, 1.0, 0.0, 0.0)
        else:
            continue
        matrix = _mat_mul(matrix, step)
    return matrix


def apply_transform(points: list[tuple[float, float]],
                    matrix: tuple[float, ...]) -> list[tuple[float, float]]:
    a, b, c, d, e, f = matrix
    return [(a * x + c * y + e, b * x + d * y + f) for x, y in points]


def transform_scale(matrix: tuple[float, ...]) -> float:
    """The uniform scale a transform applies, as the square root of its area factor.

    A brush's width is a length, so a transformed path needs its width scaled by the same amount, or the inked contour
    comes out too thin or too thick by exactly the factor the artwork was scaled.
    """
    a, b, c, d = matrix[0], matrix[1], matrix[2], matrix[3]
    determinant = abs(a * d - b * c)
    return math.sqrt(determinant) if determinant > 0 else 1.0


def _transform_path_data(d: str, matrix: tuple[float, ...]) -> str:
    """Rewrites path data with every coordinate moved through a transform.

    Used for the seam-fix copy of a shape, which is emitted outside the group it came from and therefore cannot
    inherit the transform that positioned it -- leave the numbers local and the hairline-closing stroke lands near the
    origin while the shape it belongs to is somewhere else entirely.

    **Absolute and relative commands need different arithmetic**, which is why this parses rather than rewrites
    numbers in place. An absolute point is mapped through the whole matrix; a relative offset is turned by the linear
    part alone, because the translation belongs to the cursor rather than to the offset. Handling only the absolute
    cases would be simpler and would silently misplace every relative path it was handed, which is the same class of
    quiet wrongness this file has been fixing all along.
    """
    a, b, c, dd, e, f = matrix
    # how many numbers each command consumes before the next group of the same command starts
    arity = {'M': 2, 'L': 2, 'T': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4, 'Q': 4, 'A': 7}
    tokens = re.findall(r'[A-Za-z]|-?(?:\d+\.\d+|\d+\.|\.\d+|\d+)(?:[eE][-+]?\d+)?', d)
    out: list[str] = []
    command = ''
    index = 0
    cursor = [0.0, 0.0]
    start = [0.0, 0.0]

    def map_absolute(x: float, y: float) -> tuple[float, float]:
        return a * x + c * y + e, b * x + dd * y + f

    def map_relative(x: float, y: float) -> tuple[float, float]:
        return a * x + c * y, b * x + dd * y

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            command = token
            index = 0
            out.append(token)
            i += 1
            continue
        kind = command.upper()
        if kind == 'Z':
            i += 1
            continue
        size = arity.get(kind, 2)
        group = tokens[i:i + size]
        try:
            values = [float(v) for v in group]
        except ValueError:
            out.extend(group)
            i += size
            continue
        relative = command.islower()
        mapped: list[float] = []
        if kind == 'H':
            x = values[0] + (cursor[0] if relative else 0.0)
            y = cursor[1]
            mx, my = map_absolute(x, y)
            mapped = [mx if not relative else mx - cursor[0]]
        elif kind == 'V':
            x = cursor[0]
            y = values[0] + (cursor[1] if relative else 0.0)
            mx, my = map_absolute(x, y)
            mapped = [my if not relative else my - cursor[1]]
        elif kind == 'A':
            # radii and flags are not coordinates; only the endpoint moves
            ex = values[5] + (cursor[0] if relative else 0.0)
            ey = values[6] + (cursor[1] if relative else 0.0)
            mx, my = map_absolute(ex, ey)
            if relative:
                mx, my = mx - cursor[0], my - cursor[1]
            mapped = values[:5] + [mx, my]
        else:
            pairs = [(values[k], values[k + 1]) for k in range(0, len(values) - 1, 2)]
            for px, py in pairs:
                if relative:
                    mx, my = map_relative(px, py)
                else:
                    mx, my = map_absolute(px, py)
                mapped.extend([mx, my])
        out.extend(_fmt_num(v) for v in mapped)
        # advance the cursor so a relative command knows where it starts from
        if kind in ('M', 'L', 'T'):
            if relative:
                cursor = [cursor[0] + values[-2], cursor[1] + values[-1]]
            else:
                cursor = [values[-2], values[-1]]
        elif kind == 'H':
            cursor = [values[0] + (cursor[0] if relative else 0.0), cursor[1]]
        elif kind == 'V':
            cursor = [cursor[0], values[0] + (cursor[1] if relative else 0.0)]
        elif kind in ('C', 'S', 'Q'):
            if relative:
                cursor = [cursor[0] + values[-2], cursor[1] + values[-1]]
            else:
                cursor = [values[-2], values[-1]]
        elif kind == 'A':
            cursor = [values[5] + (cursor[0] if relative else 0.0), values[6] + (cursor[1] if relative else 0.0)]
        if kind == 'M':
            start = list(cursor)
        index += size
        i += size
    return ' '.join(out)


def _fmt_num(value: float) -> str:
    return ('%.4f' % value).rstrip('0').rstrip('.') or '0'


def inked_svg(svg: str, min_extent: float = 46.0, brush: str = 'ink', colour: str = '#2A1E26',
              seed: int = 7, scale: float = 0.34) -> str:
    """**Draws a weighted contour around everything big enough to have one.**

    The whole-sheet pass rather than ninety edits: every filled path large enough to be part of a silhouette gets an
    outline with the pressure model behind it, and everything small -- eyes, mouths, ribbons, laces -- is left alone,
    because a heavy line around an eye is mud. Extent is the test rather than a list of names, so a shape added
    later is treated the same way without anybody remembering to add it.
    """
    # **A substitution, not a rebuild -- and that distinction cost a drawing its eyes.** The first version collected
    # the paths it matched into a new list and joined that list into the result, which silently discarded every
    # element the pattern did not match: the ellipses carrying an eye's whites, irises and catchlights all vanished,
    # and because what remained still suggested a face, the output went on looking plausible with no eyes in it.
    # `re.sub` keeps every character it does not match, which is the only safe way to transform a document by pattern.

    def _replace(match: 're.Match[str]', parent: tuple[float, ...]) -> str:
        body = match.group(1)
        found = re.search(r'\bd\s*=\s*(["\'])(.*?)\1', body, re.S)
        if not found:
            return match.group(0)
        d = found.group(2)
        rest = body[:found.start()] + body[found.end():]
        # **The transform belongs to the geometry, not to the outline's parent.** Generating a contour from the raw
        # numbers of a path inside `<g transform="...">` and nesting it back inside that group applies the transform
        # twice, so the contour is displaced and scaled away from the shape it is supposed to outline. It reads as a
        # bad drawing rather than as a bug, which is exactly why it is applied here instead.
        transform = re.search(r'transform\s*=\s*"([^"]*)"', rest)
        # the path's own transform is applied inside its ancestors', so the two compose in that order
        matrix = _mat_mul(parent, parse_transform(transform.group(1)) if transform else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
        brush_scale = transform_scale(matrix)
        polys = parse_path(d)
        added: list[str] = []
        # **The seam fix is emitted after the element and therefore in the caller's coordinate space.** It was
        # written with the path's own numbers, which is only correct while no transform is in play; inside a
        # transformed group those numbers are local, so the hairline-closing stroke landed near the origin instead of
        # over the seam it exists to close. Emitting it after the element also keeps it out of the transformed group,
        # so its coordinates have to be the transformed ones -- there is no group left to do the work.
        fill = re.search(r'fill\s*=\s*"([^"]+)"', rest)
        if fill and fill.group(1) not in ('none', 'transparent'):
            seam = _transform_path_data(d, matrix) if transform else d
            added.append(match.group(0))
            added.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.3" stroke-linejoin="round"/>'
                         % (seam, fill.group(1)))
        else:
            added.append(match.group(0))
        if not polys:
            return '\n  '.join(added)
        xs = [x for poly in polys for x, _ in poly]
        ys = [y for poly in polys for _, y in poly]
        if (max(xs) - min(xs)) < min_extent and (max(ys) - min(ys)) < min_extent:
            return '\n  '.join(added)
        # **A closed contour is one loop, so it is walked once and never tapered.** The first version walked it
        # forwards and then backwards to "close" it, which drew the line twice and scalloped every hair mass into
        # fish scales -- visible the moment it was rendered. A loop has no ends, so a taper has nothing to taper;
        # the weight comes from speed and corners instead.
        for i, poly in enumerate(polys):
            if len(poly) < 3:
                continue
            poly = apply_transform(poly, matrix)
            closed = math.dist(poly[0], poly[-1]) < 1.5
            brush_def = dict(BRUSHES[brush])
            # the width is a length, so it scales with the artwork or the line is too thin by the scale factor
            brush_def['width'] = brush_def['width'] * scale * brush_scale
            if closed:
                brush_def['taper_in'] = 0.0
                brush_def['taper_out'] = 0.0
            path = list(poly)
            ps = pressures(path, brush_def, seed + i)
            widths = [brush_def['width'] * p for p in ps]
            if closed:
                path = path + [path[0]]
                widths = widths + [widths[0]]
            od = outline(path, widths)
            if od:
                opacity = brush_def['opacity'] * (0.5 + 0.5 * (sum(ps) / len(ps)))
                added.append(f'<path d="{od}" fill="{colour}" opacity="{opacity:.2f}"/>')
        return '\n  '.join(added)

    # **`<path ...></path>` counts as much as `<path ... />`.** The pattern used to require the self-closing form, so
    # a document that spelled its paths the long way -- which is what most writers and most language models emit --
    # had every shape skipped in silence, and the page came back looking merely un-inked rather than broken.
    pattern = re.compile(r'<path\b((?:"[^"]*"|\'[^\']*\'|[^>])*?)/?>')

    # **Ancestor transforms have to be accumulated, because a path's own attributes are usually not where the
    # transform is.** A drawing puts `transform` on the `<g>` that groups its shapes, so looking only inside the
    # `<path>` finds nothing, generates the contour in local coordinates, and then hands it back to the group to be
    # transformed a second time -- the exact displacement this was meant to remove, and it survived a first fix
    # because that fix only handled a transform written on the path itself. The scan below keeps a stack: opening
    # `<g>` tags push their matrix, closing tags pop, and a group with no transform still pushes the identity so the
    # stack stays aligned with the nesting.
    pieces: list[str] = []
    cursor = 0
    close_re = re.compile(r'</g\s*>')
    open_re = re.compile(r'<g\b((?:"[^"]*"|\'[^\']*\'|[^>])*?)(/?)>')
    stack: list[tuple[float, ...]] = [(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)]

    def advance(upto: int) -> None:
        """Feed `svg[cursor:upto]` to the group stack, in document order.

        Kept separate from assembling the output on purpose: an earlier version advanced the cursor itself as it
        scanned, so the text between two matches was consumed by the stack walk and never reached the result -- which
        deleted every element the path pattern does not match, the most expensive defect this library has had.
        """
        chunk = svg[cursor:upto]
        pos = 0
        while pos < len(chunk):
            nxt_close = close_re.search(chunk, pos)
            nxt_open = open_re.search(chunk, pos)
            if nxt_close is None and nxt_open is None:
                break
            if nxt_open is not None and (nxt_close is None or nxt_open.start() < nxt_close.start()):
                attrs = nxt_open.group(1)
                if nxt_open.group(2) != '/':       # a self-closing group has no children to affect
                    inner = re.search(r'transform\s*=\s*"([^"]*)"', attrs)
                    matrix = parse_transform(inner.group(1)) if inner else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
                    stack.append(_mat_mul(stack[-1], matrix))
                pos = nxt_open.end()
            else:
                if len(stack) > 1:
                    stack.pop()
                pos = nxt_close.end()

    # **A commented-out path is not part of the drawing.** The pattern matches text, so it matched one inside an XML
    # comment and drew a contour for a shape the document explicitly does not show. Measured rather than assumed: a
    # document whose only `<path>` sat inside `<!-- -->` came back with one outline in it. The spans are collected once
    # and a match starting inside one is left alone.
    comment_spans = [(m.start(), m.end()) for m in re.finditer(r'<!--.*?-->', svg, re.S)]

    def in_comment(position: int) -> bool:
        return any(start <= position < end for start, end in comment_spans)

    for match in pattern.finditer(svg):
        if in_comment(match.start()):
            continue
        advance(match.start())
        pieces.append(svg[cursor:match.start()])
        pieces.append(_replace(match, stack[-1]))
        cursor = match.end()
    pieces.append(svg[cursor:])
    return ''.join(pieces)


def stroke_record(points: list[tuple[float, float]], brush_name: str, seed: int = 0,
                  colour: str = '', resolution: int = 14, role: str = '',
                  width_profile: list[float] | None = None,
                  alpha_profile: list[float] | None = None) -> dict:
    """The stroke as **data** rather than as an expanded outline: centre line, pressure samples, brush, seed.

    **This is the difference between an exporter and a drawing tool.** Everything before this returned a filled
    outline -- the correct thing to render and useless to edit, because once a variable-width stroke has been turned
    into a polygon there is no way back to the line it came from or the hand that made it. A record keeps the
    decisions: which brush, which seed, which points, and what pressure the model produced at each of them. From that
    the outline can be regenerated at any resolution, the brush can be swapped, a point can be moved, and the whole
    thing can be written to a file and reopened tomorrow.

    Nothing about the rendering changes; `stroke()` now builds its outline from a record, so the two cannot drift
    apart, and a test asserts that a record round-trips to identical output.
    """
    brush = BRUSHES[brush_name]
    path = catmull(points, resolution)
    path = tremble(path, brush.get('wobble', 0.0) * brush['width'], seed,
                   TREMBLE_STEP * brush['width'])
    ps = pressures(path, brush, seed)
    return {
        'brush': brush_name,
        'seed': seed,
        # **Resolved here, once.** The default used to be a literal, which meant a role could never supply its ink:
        # `colour or role_ink(...)` never reached the second half. An explicit colour still wins, and a record with
        # neither a colour nor a role gets the historical default.
        # **The caller's colour, or nothing.** Not the role's -- see `mark_ink`: resolving the role's ink into the
        # record made the colour explicit, which is exactly what stops a later role assignment from changing it.
        'colour': colour,
        'resolution': resolution,
        # **What this line is *for*, not how wide it is.** Stored on the record rather than passed to the expander so
        # that the role survives into the project file and can be changed later without redrawing anything -- which is
        # the professional order of operations: get the form right first, decide the line hierarchy afterwards.
        'role': role,
        # **The four knobs pressure actually decomposes into, made explicit.** In a tablet application pressure moves
        # width (the dominant effect), opacity, dab spacing and a little colour jitter; a record that can only express
        # the first cannot be a substitute for the hand. Both of these are optional and absent means "derived", so a
        # record written before they existed expands exactly as it did.
        #
        # They sit *before* the role's multiplier rather than after it, so assigning a role still rescales a profile
        # that was supplied by measurement -- otherwise the second pass would not reach the strokes that need it most.
        'width_profile': [float(w) for w in width_profile] if width_profile else [],
        'alpha_profile': [float(a) for a in alpha_profile] if alpha_profile else [],
        'control': [[round(x, 3), round(y, 3)] for x, y in points],
        'centre': [[round(x, 3), round(y, 3)] for x, y in path],
        'pressure': [round(p, 4) for p in ps],
    }


# **Where 強弱 stops being visible.** A stroke whose thinnest fifth is within 5% of its own mean has, in effect, one
# width -- and the sentence this library exists to answer is the artist's: 「私は髪を描くたび線画に強弱を付けることを
# 忘れがち」 (DSマイル, CGイラストテクニック vol.10) -- *I tend to forget to add width variation to the line art every
# time I draw hair*. Forgetting is the named, recurring failure, and a uniform line is what forgetting looks like.
#
# The number is not tuned, it is placed in a gap that was measured. A flat profile scores **1.000**; across 160
# generated strokes of every brush the model's flattest scores **0.910** and its median 0.555; and the pooled corpus
# puts a whole drawing's thinnest fifth against its mean at 0.421 with a p90 of 0.507. So 0.95 is above everything
# this library produces and below uniform, and `test_lineweight.py` asserts the first half of that as a promise.
UNIFORM_FLOOR = 0.95


def stroke_variation(record: dict) -> float:
    """A stroke's own 強弱 (width variation): **its thinnest fifth against its mean.** Low is strong variation.

    Per stroke and along its own length, which is the point. `ref.measure_taper` records why the whole-drawing
    statistic cannot answer this question -- a taper occupies a few percent of a stroke, so a drawing-level ratio is
    dominated by differences *between* strokes and barely moves when the ends change. The same objection applies here
    in reverse: an even line among varied ones is invisible to any pooled number and obvious to this one.
    """
    widths = stroke_widths(record)
    if not widths:
        return 1.0
    ordered = sorted(widths)
    k = max(1, len(ordered) // 5)
    mean = sum(ordered) / len(ordered)
    return (sum(ordered[:k]) / k) / mean if mean > 0 else 1.0


def is_uniform(record: dict, floor: float = UNIFORM_FLOOR) -> bool:
    """Whether a stroke has, in effect, one width."""
    return stroke_variation(record) >= floor


def mark_ink(mark: dict) -> str:
    """The ink a mark is drawn in: its own if the caller chose one, the role's otherwise.

    **An absent colour is not a missing value, it is the answer "the role decides".** The drawing convention's order
    of work is form first and line hierarchy afterwards -- アンミ: get the shape right, then add the width variation --
    so a role has to be assignable to a stroke that was drawn before anyone knew what it was for, and that only works
    if changing the role can still change the ink. Resolving the role's ink at creation looked right and quietly made
    re-assignment a no-op for colour.
    """
    return (mark.get('appearance', {}).get('colour')
            or roles.ink(mark.get('geometry', {}).get('role', '')))


def stroke_widths(record: dict) -> list[float]:
    """The width the brush reaches at each recorded pressure sample.

    **The response curve is applied here, at expansion, rather than being baked into the record.** A record holds what
    the pressure model produced; the curve is a decision about how the brush answers it -- under one it reaches full
    width early and feels soft, over one it needs real pressure and feels like a pen. Because the curve lives on this
    side, the same recorded stroke can be re-expanded with a different one, which is the practical difference between
    keeping the line and keeping only its outline.
    """
    brush = BRUSHES[record['brush']]
    gamma = float(brush.get('curve', 1.0))
    # **The role multiplies the profile rather than replacing it**, so naming a line's role never removes the pressure
    # variation -- which is the whole point of this library, and the thing the drawing convention says artists forget
    # to add to hair. An empty role is 1.0 and changes nothing.
    scale = roles.width_scale(record.get('role', ''))
    supplied = record.get('width_profile')
    if supplied:
        # A measured or hand-authored profile, used as given. This is the field that lets the model be *fitted* --
        # `ref.py` measures a width distribution out of real artwork, and without somewhere to put it the measurement
        # has nowhere to land except the brush table, which is per-brush and therefore cannot be per-stroke.
        return [scale * float(w) for w in supplied]
    return [brush['width'] * scale * (float(p) ** gamma) for p in record['pressure']]


def outline_polygon(record: dict) -> list[tuple[float, float]]:
    """The shape a record expands to, as **points** -- the exact offset, before any fitting.

    Kept alongside the fitted chain because the two answer different questions. This is the ground truth the fit is
    measured against, and it is what `audit.compare_fillers` gives both rasterisers, since a comparison of *fillers*
    has to be on identical geometry. **It is not the shape that ships** -- `outline_chain_of` is.
    """
    return outline_points([(float(x), float(y)) for x, y in record['centre']], stroke_widths(record))


def outline_chain_of(record: dict) -> list[Cubic]:
    """**The shape that ships.** The fitted, closed boundary of a record's stroke."""
    return outline_chain([(float(x), float(y)) for x, y in record['centre']], stroke_widths(record))


def from_record(record: dict) -> tuple[str, float]:
    """Rebuilds a stroke's outline from its record, which is what makes the record worth keeping."""
    brush = BRUSHES[record['brush']]
    ps = [float(p) for p in record['pressure']]
    chain = outline_chain_of(record)
    d = (curve.chain_to_path(chain) + ' Z') if chain else ''
    return d, record_opacity(record)


def record_opacity(record: dict) -> float:
    """The one opacity a *vector* export can carry for a stroke.

    **A profile, reduced to its mean, because that is all SVG has.** A filled path takes one `fill-opacity`; there is
    no way to vary it along a curve, any more than there is a way to vary the width -- which is why the width becomes
    an outline and this cannot become anything. So a record with an `alpha_profile` exports at its mean here, and the
    profile itself survives only in the raster and PSD paths, where each dab is placed individually.

    Stated rather than silent: a caller who wrote a fade into a record and got a flat export back would otherwise have
    no way to tell that from a fade that was too subtle to see. `collapses_alpha` is the detectable form.
    """
    brush = BRUSHES[record['brush']]
    profile = record.get('alpha_profile')
    if profile:
        # **The brush's opacity is the medium and still applies**, exactly as it does per dab in `raster.stroke_layer`.
        # The first version of this returned the bare mean of the profile, so a wash with a full profile exported at
        # 1.0 while it rendered at 0.35 -- two renderers of one record disagreeing, which is the failure this project
        # keeps meeting and a test caught within the minute.
        return brush['opacity'] * (sum(float(a) for a in profile) / len(profile))
    ps = [float(p) for p in record['pressure']]
    mean_p = sum(ps) / len(ps) if ps else 1.0
    return brush['opacity'] * (0.55 + 0.45 * mean_p)


def collapses_alpha(record: dict) -> bool:
    """Whether a vector export of this record loses something. True when the alpha varies along the stroke."""
    profile = record.get('alpha_profile')
    if not profile:
        return False
    return max(profile) - min(profile) > 1e-6


def save_strokes(records: list[dict], path: str) -> None:
    """A drawing is a list of records; this is how it survives the process that made it."""
    import json
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump({'version': 1, 'strokes': records}, handle, ensure_ascii=False, indent=1)
        handle.write('\n')


def load_strokes(path: str) -> list[dict]:
    import json
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)['strokes']


def weld_endpoints(polys: list[list[tuple[float, float]]], tolerance: float = 4.0
                   ) -> list[list[tuple[float, float]]]:
    """Joins polylines whose ends are within [tolerance] of each other, and closes the loops that result.

    **This is gap closing, which is the thing a bucket fill needs and does not have.** An exact fill stops at the
    first pixel of daylight: draw four strokes that almost meet and nothing is enclosed, so nothing fills. Every
    drawing program solves this by closing gaps as it fills, and the vector equivalent is to weld the ends before
    deciding what counts as a region -- two loose ends four pixels apart are one corner, not a hole.
    """
    remaining = [list(poly) for poly in polys if len(poly) >= 2]
    loops: list[list[tuple[float, float]]] = []
    while remaining:
        chain = remaining.pop(0)
        joined = True
        while joined and remaining:
            joined = False
            for index, other in enumerate(remaining):
                for reverse_chain, reverse_other in ((False, False), (False, True), (True, False), (True, True)):
                    a = chain[::-1] if reverse_chain else chain
                    b = other[::-1] if reverse_other else other
                    if math.dist(a[-1], b[0]) <= tolerance:
                        chain = a + b[1:]
                        remaining.pop(index)
                        joined = True
                        break
                if joined:
                    break
        if len(chain) >= 3 and math.dist(chain[0], chain[-1]) <= tolerance:
            if chain[0] != chain[-1]:
                chain = chain + [chain[0]]
            loops.append(chain)
    return loops


class Region(NamedTuple):
    """An enclosed area: the polygon it came from, and the path data that draws it.

    **Both, not just the `d` string.** A bare `d` string can be painted and nothing else -- it cannot be moved,
    re-styled, re-ordered or deleted by anything that only has a string. The polygon is what a `fill` mark stores so
    that the patch of colour stays a thing with an identity, which is the whole requirement; the `d` is kept alongside
    it because that is what a renderer wants and re-serialising it on every frame would be silly.
    """
    points: list[tuple[float, float]]
    d: str


def region_fill(polys: list[list[tuple[float, float]]], tolerance: float = 4.0) -> list[Region]:
    """Every region the strokes enclose once their gaps have been closed.

    This answers the question a bucket answers: *is anything enclosed here*, given a drawing made by somebody whose
    lines do not always meet. It returns geometry and says nothing about how the region should be painted -- that is
    the caller's decision, and in a project it becomes a `fill` mark's appearance.
    """
    out: list[Region] = []
    for loop in weld_endpoints(polys, tolerance):
        points = ['%.2f %.2f' % (x, y) for x, y in loop]
        out.append(Region(points=list(loop), d='M ' + ' L '.join(points) + ' Z'))
    return out


def fit_report(image_path: str) -> int:
    """Measure one drawing the same way the reference library is measured.

    **This used to be a second, separate measurement.** It loaded the image, counted dark pixels per row and column,
    and printed two percentiles -- sharing no code with `ref.py`, and disagreeing with it in the ways two independent
    implementations always do: it needed Pillow where `ref.py` decodes PNG by hand, it had its own ink threshold
    constant, and it could not be pooled with anything. A drawing measured by `--fit` and a drawing measured into the
    library were not comparable numbers, which defeats the point of having a library.

    Now there is one measurement. What `--fit` prints are the quantities the library records, so a sheet drawn by hand
    can be read against the numbers in `tests/data/corpus_summary.json` directly.
    """
    from .ref import ImageError, measure

    try:
        result = measure(image_path)
    except (ImageError, FileNotFoundError) as exc:
        print('  cannot measure %s: %s' % (image_path, exc))
        return 2
    print('  %s  %dx%d' % (os.path.basename(image_path), result.width, result.height))
    if result.note:
        print('  %s' % result.note)
    print('  ink fraction      %.4f      (linework in the library sits at 0.15)' % result.ink_ratio)
    print('  mean darkness     %.1f' % result.darkness)
    print('  line-like runs    %d of %d runs' % (result.line_runs, result.runs))
    if result.line_runs:
        print('  width             median %.1f  p90 %.1f  max %d'
              % (result.width_median, result.width_p90, result.width_max))
        print('  taper ratio       %.4f      (linework in the library sits at 0.42)' % result.taper_ratio)
        spread = result.width_p90 / result.width_median if result.width_median else 0.0
        print('  p90/median        %.3f      (linework in the library sits at 2.75)' % spread)
        print('  the last two are ratios inside this drawing, so they are comparable with the library at any size')
    return 0


def fit_directory(root: str) -> int:
    """Measure a folder of drawings and print the pooled distribution, against the library's targets.

    The point of pooling is that one drawing's distribution is noisy and a folder's is not; the point of printing the
    targets beside it is that "does this brush match the artwork" stops being a judgement.
    """
    import json

    from .ref import ImageError, scan, summarise

    if not os.path.isdir(root):
        print('  not a directory: %s' % root)
        return 2
    measurements = scan(root)
    summary = summarise(measurements)
    print('  %s' % root)
    print('  %d images, %d measurable, %d skipped' % (summary['images'], summary['usable'], summary['skipped']))
    if not summary.get('runs'):
        print('  nothing measurable in this folder')
        return 1
    targets = _library_targets()
    print('  %-14s %10s %10s' % ('', 'this folder', 'library'))
    for key, label in (('ink_ratio', 'ink fraction'), ('width_median', 'width median'),
                       ('width_p90', 'width p90'), ('taper_ratio', 'taper ratio')):
        reference = targets.get(key)
        print('  %-14s %10.4f %10s'
              % (label, summary[key], '%.4f' % reference if isinstance(reference, (int, float)) else '-'))
    print('  the library column comes from %d pooled line drawings; the checked-in summary is'
          % targets.get('images', 0))
    print('  tests/data/corpus_summary.json, so both sides can be re-derived.')
    return 0


def _library_targets() -> dict:
    """The pooled linework distribution, from the checked-in summary when it is there."""
    import json

    targets: dict = {}
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'tests', 'data', 'corpus_summary.json')
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return targets
    for key in ('ink_ratio', 'width_median', 'width_p90', 'taper_ratio'):
        block = data.get('linework_' + key)
        if isinstance(block, dict) and isinstance(block.get('median'), (int, float)):
            targets[key] = block['median']
    targets['images'] = data.get('totals', {}).get('linework', 0)
    spread = data.get('linework_p90_over_median', {}).get('median')
    if isinstance(spread, (int, float)):
        targets['p90_over_median'] = spread
    return targets


def demo(out_path: str) -> int:
    """Four brushes, the same four strokes: the sheet that says whether the model does anything at all."""
    strokes = [
        [(40, 40), (140, 30), (240, 60), (340, 40)],
        [(40, 110), (120, 150), (200, 90), (300, 130), (360, 100)],
        [(40, 200), (200, 190), (200, 260), (360, 250)],
        [(40, 320), (110, 280), (190, 340), (270, 290), (360, 330)],
    ]
    width, height = 400, 380 + len(BRUSHES) * 0
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width * 2}" height="{height * len(BRUSHES) // 1}" '
             f'viewBox="0 0 {width * 2} {height * len(BRUSHES)}">',
             f'<rect width="100%" height="100%" fill="#F4F1E9"/>']
    for row, name in enumerate(BRUSHES):
        y = row * height
        parts.append(f'<text x="12" y="{y + 22}" font-family="monospace" font-size="14" fill="#4C463C">{name}</text>')
        for i, points in enumerate(strokes):
            shifted = [(x, yy + y + 20) for x, yy in points]
            d, opacity = stroke(shifted, name, seed=row * 31 + i, colour='#1A1620')
            if d:
                parts.append(f'<path d="{d}" fill="#1A1620" opacity="{opacity:.2f}"/>')
            shifted2 = [(x + width, yy + y + 20) for x, yy in points]
            d2, o2 = stroke(shifted2, name, seed=row * 31 + i + 7, colour='#6E1E2E')
            if d2:
                parts.append(f'<path d="{d2}" fill="#6E1E2E" opacity="{o2:.2f}"/>')
    parts.append('</svg>')
    # **`os.path.dirname('strokes.svg')` is the empty string**, and `makedirs('')` raises -- so the plain invocation
    # in the README, `--out strokes.svg`, crashed before it wrote anything. Only make a directory that was named.
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(parts))
    print('  %s' % out_path)
    return 0


def demo_document() -> 'Document':
    """The demo sheet as a document: four brushes' worth of expanded outlines, plus a construction line.

    Shared by every destination so that "does Illustrator receive the same drawing SAI does" is answerable by
    construction rather than by keeping two copies of the same four strokes in step.
    """
    from .doc import Appearance, Path, from_strokes

    strokes = [
        ([(40, 40), (140, 30), (240, 60), (340, 40)], 'ink'),
        ([(40, 110), (120, 150), (200, 90), (300, 130), (360, 100)], 'pencil'),
        ([(40, 200), (200, 190), (200, 260), (360, 250)], 'fine'),
        ([(40, 320), (110, 280), (190, 340), (270, 290), (360, 330)], 'wash'),
    ]
    expanded = []
    for i, (points, name) in enumerate(strokes):
        d, opacity = stroke(points, name, seed=13 + i, colour='#1A1620')
        coords = re.findall(r'(-?\d+\.?\d*) (-?\d+\.?\d*)', d)
        if not coords:
            continue
        expanded.append({'outline': [(float(a), float(b)) for a, b in coords], 'colour': '#1A1620',
                         'opacity': opacity, 'layer': 'LINE', 'name': '%s-%d' % (name, i)})
    document = from_strokes(expanded, layer='LINE')
    # a stroked construction line, so every destination is exercised with both kinds of geometry
    document.layer('DETAIL').add(Path(points=[(40, 380), (360, 380)],
                                      appearance=Appearance(filled=False, stroke='#6E1E2E',
                                                            stroke_width=2.5, opacity=0.8),
                                      closed=False, name='rule'))
    # **The canvas is grown after the last shape is added, not before.** `from_strokes` sizes the page to the strokes
    # it was given, and the rule below them landed outside it -- a shape that exists in every destination's data and
    # is visible in none of them, because no format complains about geometry off the page.
    from .doc import resize_to_fit
    return resize_to_fit(document)


def to_psd(out_path: str, scale: float = 1.0) -> int:
    """The demo sheet as a layered PSD, which is how a drawing reaches SAI -- it has no scripting interface at all."""
    from .psd import layers_from_document, read_psd_header, save_psd

    document = demo_document()
    layers = layers_from_document(document, scale=scale)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    save_psd(layers, out_path)
    head = read_psd_header(out_path)
    print('  %s  %s' % (out_path, ', '.join('%s=%s' % (k, head[k])
                                            for k in ('layers', 'width', 'height', 'mode', 'depth'))))
    print('      layers: %s' % ', '.join(head['names']))
    print('      %d bytes, merged image data %s'
          % (head['bytes'], 'present' if head['merged_bytes_present'] else 'MISSING'))
    return 0


def to_xfl(out_path: str, launch: bool = False) -> int:
    """The demo sheet as XFL, the one form Animate opens without a click.

    Animate has no scriptable entry point on this machine -- verified every way tried -- so the drawing is written as
    Animate's own project format and handed over as a folder.

    **The folder is the deliverable, and it is not zipped.** This used to pack it into a `.xfl` archive, which was
    wrong in a way that cost rounds: Animate must be pointed at the marker file *inside* the folder, and a zip has no
    such file to point at. The runner resolves a folder to its marker; nothing here should undo that.
    """
    from .xfl import write_xfl

    document = demo_document()
    # **The folder name is the project name, and it does not need the extension stripped or added.** The marker file
    # inside is named after the folder, and Animate is pointed at that marker -- so a caller who asks for `drawing.xfl`
    # gets a folder `drawing.xfl` holding a marker `drawing.xfl`. Stripping the extension here made the folder and its
    # marker disagree, which reads as "the file is not there" when a later step goes looking for it.
    folder = out_path
    parent = os.path.dirname(folder)
    if parent:
        os.makedirs(parent, exist_ok=True)
    write_xfl(document, folder)
    marker = os.path.join(folder, os.path.basename(folder))
    print('  %s  (%s)' % (folder, ', '.join('%s=%d' % (k, v) for k, v in document.counts().items())))
    if not launch:
        print('  open it with:  Animate.exe "%s"   (the marker file, not the folder)' % marker)
        return 0
    from .run import open_in_animate
    result = open_in_animate(folder)
    print('  %s' % result.describe())
    return 0 if result.ok else 1


def render_report(project_path: str, stage: str = '', upto: str = '', out: str = 'render.png',
                  scale: float = 1.0, paper: str = '') -> int:
    """Renders a project file to an image, optionally one pass at a time.

    **This is an export, not the product.** What lineweight makes is the project file; an image is one reading of it,
    and the reason to take that reading per pass is that acceptance is per pass -- "is the linework right", "is the
    value structure there" and "is the colour sitting on top of it" are three different questions about three different
    states of the same drawing, and answering them from the finished picture is guesswork.

    The imports are inside the function on purpose: `raster` imports `core`, so `core` importing `raster` at module
    level would be a cycle. Every other command here that crosses a module boundary does the same thing.
    """
    from .project import load_project
    from .raster import render_marks, save_png

    project = load_project(project_path)
    if stage and upto:
        raise SystemExit('--render: give --stage or --upto, not both')
    if stage:
        marks, label = project.in_stage(stage), 'stage %s' % stage
    elif upto:
        marks, label = project.upto(upto), 'up to and including %s' % upto
    else:
        marks, label = project.live(), 'every live mark'

    width = int(project.width * scale)
    height = int(project.height * scale)
    # **The surface is chosen here and only here.** `check_report` renders the same marks and deliberately does not
    # take a paper: the invariants judge the drawing's stages, and which sheet it is previewed on must not move a
    # measurement.
    from .raster import PAPERS
    if paper and paper not in PAPERS:
        raise SystemExit('--paper: unknown surface %r; known are %s' % (paper, ', '.join(sorted(PAPERS))))
    layer = render_marks([m.to_dict() for m in marks], width, height, scale,
                         paper=PAPERS[paper] if paper else None)
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    save_png(layer, out)

    covered = sum(1 for i in range(0, width * height * 4, 4) if layer.data[i + 3] > 0)
    print('  %s' % out)
    print('  %s: %d of %d marks, %d x %d, %d px covered (%.1f%%)'
          % (label, len(marks), len(project.marks), width, height, covered, 100.0 * covered / (width * height)))
    return 0


def audit_report(project_path: str, out: str = 'audit.png', stage: str = '', upto: str = '',
                 pixels: int = 1400, zoom: str = '') -> int:
    """Draws a project with **cairo** instead of with `raster.py`, one colour per mark.

    Two things this is for, and neither is a nicer picture. First, an independent rasteriser of the same geometry: if
    cairo's version and `--render`'s version differ, one of them is wrong and until now nothing could say which.
    Second, the Metzger Figure 5 view -- every mark its own colour, zoomed in -- where a stroke that merged into its
    neighbour, crossed itself into a pinhole, or lost half its area stops being invisible.

    `--zoom cx,cy,span` looks at one place instead of the whole canvas, because the whole canvas is exactly where
    these faults are too small to see.
    """
    from .audit import View, render, save, stroke_colours
    from .project import load_project

    project = load_project(project_path)
    if stage and upto:
        raise SystemExit('--audit: give --stage or --upto, not both')
    if stage:
        marks, label = project.in_stage(stage), 'stage %s' % stage
    elif upto:
        marks, label = project.upto(upto), 'up to and including %s' % upto
    else:
        marks, label = project.live(), 'every live mark'
    marks = [m.to_dict() for m in marks]

    view = View.whole(int(project.width), int(project.height), pixels)
    if zoom:
        try:
            cx, cy, span = (float(v) for v in zoom.split(','))
        except ValueError:
            raise SystemExit('--zoom wants cx,cy,span -- got %r' % (zoom,))
        view = View.around(cx, cy, span, pixels)

    surface = render(marks, view, colours=stroke_colours(len(marks)))
    save(surface, out)
    print('  %s' % out)
    print('  %s: %d marks, view %g,%g %gx%g -> %dx%d px, one colour per mark'
          % (label, len(marks), view.x, view.y, view.w, view.h, *view.size()))
    return 0


def judge_report(project_path: str, scale: float = 1.0) -> int:
    """Runs both referees and prints the numbers, including the one that says whether to believe them.

    **The point is that these numbers can come out wrong.** `--render` and `--check` are this library marking its own
    homework; this is cairo, which has never heard of this library, being asked the same question.
    """
    from .audit import compare_fillers, compare_stroker, mark_polygon
    from .project import load_project

    project = load_project(project_path)
    width = int(project.width * scale)
    height = int(project.height * scale)
    marks = [m.to_dict() for m in project.live()]

    polygons = [mark_polygon(m) for m in marks]
    print('  A. filler  -- the same points, two rasterisers')
    # `(x,)` and not `x`: `Agreement` is a NamedTuple, and `'%s' % named_tuple` is read as *the argument tuple* and
    # unpacks into "not all arguments converted" rather than calling its `__str__`. The one place a tuple is a trap.
    print('     %s' % (compare_fillers(polygons, (width, height)),))

    print('  B. offsetter -- outline() against cairo\'s stroker, at each mark\'s mean width')
    print('     **read `turn` with the number**: agreement is expected while the path is smooth, and a')
    print('     disagreement at a reversal is the known invalid-loop problem, not a regression.')
    worst = 0
    strokes = 0
    for mark in marks:
        if mark['kind'] != 'stroke':
            continue
        strokes += 1
        centre = [(float(x), float(y)) for x, y in mark['geometry']['centre']]
        widths = stroke_widths(mark['geometry'])
        mean = sum(widths) / len(widths) if widths else 1.0
        report = compare_stroker(centre, mean, (width, height))
        if report.agreement.gross:
            worst += 1
        print('     %-8s turn %6.1f deg  width %5.2f  %s'
              % (mark['id'], report.turn, report.width, report.agreement))
    print('  %d of %d strokes disagree structurally' % (worst, strokes))
    return 0


def check_report(project_path: str, scale: float = 1.0) -> int:
    """Renders each pass and runs that pass's invariants against the result, then reports.

    **Measured on the cumulative state, not on the pass alone.** The numbers these invariants were derived from were
    taken from whole frames of a recording -- the canvas as it stood -- so `upto` is the matching reading. Measuring
    the colour pass in isolation would mean measuring an image with no linework and no value structure in it, which is
    not a state the drawing was ever in.

    **Reports; it does not refuse.** A drawing that fails an invariant is still a drawing, and the invariants are
    advisory because the evidence behind them is one artist's process. What it must not do is stay silent: a pass with
    no invariants is reported as claiming nothing, and an invariant that could not be measured is reported as
    unmeasurable rather than as a pass.
    """
    from .invariants import check_project, format_findings, measure_layer
    from .project import load_project
    from .raster import render_marks

    project = load_project(project_path)
    width, height = int(project.width * scale), int(project.height * scale)
    images = {}
    for stage in project.stages:
        role = stage['role']
        marks = project.upto(role)
        if not marks:
            continue
        layer = render_marks([m.to_dict() for m in marks], width, height, scale)
        images[role] = measure_layer(layer)

    print('  %s: %d stage(s) rendered, %d mark(s)' % (project_path, len(images), len(project.marks)))
    print(format_findings(check_project(project, images)))
    return 0


def log_report(project_path: str, rewind_to: int = -1) -> int:
    """Prints what has been done to a project, and optionally rewinds to an earlier step.

    **The log is the part of the file a person reads.** The marks say what the drawing is; the log says how it got
    there, which is what "that change was wrong" needs in order to point at something. Supersede reasons ride along
    with it, because a mark that was taken out and a mark that was never drawn are different things and the file
    should not make them look the same.
    """
    from .project import save_project, load_project

    project = load_project(project_path)
    if rewind_to > 0:
        undone = project.rewind(rewind_to)
        save_project(project, project_path)
        print('  rewound %d step(s): %s'
              % (len(undone), ', '.join(e.get('op', '?') for e in undone)))

    if not project.log:
        print('  (nothing has been changed since the project was built)')
        return 0

    live = sum(1 for m in project.marks if m.state == 'live')
    print('  %s: %d mark(s), %d live, %d log entr(ies)'
          % (project_path, len(project.marks), live, len(project.log)))
    for entry in project.log:
        ids = ', '.join(entry.get('ids', [])) or '-'
        extra = ''
        if entry['op'] == 'revise':
            extra = ' [%s]' % ', '.join(entry.get('changed', []))
        elif entry['op'] == 'supersede' and entry.get('reason'):
            extra = ' -- %s' % entry['reason']
        elif entry['op'] == 'remove':
            mark = entry.get('mark', {})
            extra = ' (%s, %s)' % (mark.get('kind', '?'), mark.get('stage', '?'))
        print('  %4d  %-10s %-14s%s' % (entry.get('at', -1), entry['op'], ids, extra))
    return 0


def bridge(out_path: str, svg_out: str = '', report: str = '', run: bool = False, ai_out: str = '') -> int:
    """The demo sheet, carried into Illustrator as a real document instead of as SVG.

    This is the entry point that answers "can a lineweight drawing be worked on in a drawing application": the
    pressure model expands each stroke into a filled outline, the outlines are gathered into a layered document, and
    the document is written as an ExtendScript that Illustrator runs natively. With `run`, Illustrator is launched and
    the result is exported back to SVG, so the check is the application's own output rather than this side's belief.
    """
    from .app import jsx_document

    document = demo_document()
    script = out_path if out_path.lower().endswith('.jsx') else out_path + '.jsx'
    jsx = jsx_document(document, export_svg=svg_out or None, export_ai=ai_out or None,
                       report=report or None,
                       done=(script[:-4] + '.done') if run else None)
    with open(script, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(jsx)
    print('  %s  (%s)' % (script, ', '.join('%s=%d' % (k, v) for k, v in document.counts().items())))
    if not run:
        print('  run it with:  Illustrator.exe "%s"' % script)
        return 0

    from .run import run_jsx
    result = run_jsx(jsx, script, report_path=report or None, sentinel_path=script[:-4] + '.done')
    print('  %s' % result.describe())
    if result.report:
        for line in result.report.strip().splitlines():
            print('      %s' % line)
    if svg_out and os.path.exists(svg_out):
        with open(svg_out, encoding='iso-8859-1') as handle:
            body = handle.read()
        groups = re.findall(r'<g id="([^"]*)"', body)
        shapes = re.findall(r'<(polygon|path|line)\b', body)
        print('  exported: %d shapes in groups %s' % (len(shapes), groups))
    return 0 if result.ok else 1


def assign_roles(project_path: str, spec: str, note: str = '') -> int:
    """The second pass from the command line: **`--assign-role m0001=silhouette,m0007=detail`.**

    Form first, line hierarchy afterwards -- and the point of doing it here rather than at drawing time is that the
    geometry is already settled. Nothing is redrawn: the role reaches the expansion through `stroke_widths`, so the
    same record produces a different outline and the same empty `appearance` produces a different ink. That is what
    makes the hierarchy something a caller can revise after seeing the drawing, which is the whole order of work the
    convention describes.

    The file is saved in place, because a second pass that has to be re-applied is not a pass.
    """
    from .project import load_project, save_project

    project = load_project(project_path)
    assignments = {}
    for item in spec.split(','):
        item = item.strip()
        if not item:
            continue
        if '=' not in item:
            raise SystemExit('--assign-role wants id=role pairs, e.g. m0001=silhouette; got %r' % item)
        mark_id, role = item.split('=', 1)
        assignments[mark_id.strip()] = role.strip()
    if not assignments:
        raise SystemExit('--assign-role got nothing to assign')
    project.next_turn(note or 'assign %d line roles' % len(assignments))
    project.assign_roles(assignments, note=note)
    save_project(project, project_path)
    for mark_id, role in assignments.items():
        mark = project.by_id(mark_id)
        widths = stroke_widths(mark.geometry)
        print('  %-8s -> %-11s mean width %5.2f  ink %s'
              % (mark_id, role or '(cleared)', sum(widths) / len(widths), mark_ink(mark.to_dict())))
    return 0


def uniformity_report(project_path: str) -> int:
    """**The failure this library exists to prevent, made visible.**

    Flat linework is what "forgetting the 強弱" looks like, and it is named as a recurring failure by an illustrator
    the convention quotes. The model does not produce it -- 160 measured strokes, flattest 0.910 against a uniform
    1.000 -- but the *project file* can, because a project file is the product and a caller writing one by hand can
    supply a pressure profile with no variation in it at all. So the check belongs on the document, not on the
    generator's confidence in itself.

    Reports rather than refuses, and says which strokes and how flat, because "this line is too even" is a correction
    an artist makes rather than an error a program rejects.
    """
    from .project import load_project

    project = load_project(project_path)
    strokes = [m.to_dict() for m in project.live() if m.kind == 'stroke']
    if not strokes:
        print('  no strokes in this project')
        return 0

    measured = [(mark, stroke_variation(mark['geometry'])) for mark in strokes]
    ordered = sorted(v for _, v in measured)
    flat = [item for item in measured if item[1] >= UNIFORM_FLOOR]

    print('  %d strokes, 強弱 = thinnest fifth over the mean (low is strong variation)' % len(strokes))
    print('    flattest %.3f   median %.3f   strongest %.3f'
          % (ordered[-1], ordered[len(ordered) // 2], ordered[0]))
    print('    uniform is 1.000, the floor is %.2f; the corpus puts a whole drawing at 0.421' % UNIFORM_FLOOR)
    print()
    if not flat:
        print('  no uniform strokes: every line has width variation.')
        return 0
    print('  %d stroke(s) with no variation in them:' % len(flat))
    print('    %-8s %-10s %-6s %7s   %s' % ('id', 'stage', 'role', 'strong', 'what to do'))
    for mark, value in sorted(flat, key=lambda item: -item[1]):
        print('    %-8s %-10s %-6s %7.3f   the profile has one width in it'
              % (mark['id'], mark['stage'], mark['geometry'].get('role', '') or '-', value))
    return 0


def roles_report(project_path: str) -> int:
    """**The role model checking itself against the drawing it was applied to.**

    Naming a line's role is a claim about it, and a claim that nothing examines is a comment. Three of the drawing
    convention's five-item checklist are answerable from this library's own measurements, and two of them are answered
    here:

      * *is there a difference between outer and inner line width?* -- the per-role width distributions side by side
      * *at reduced scale, is the focal point not buried under line?* -- whether the heavy end has run away, which is
        what the corpus ratios are for

    The ratios are printed next to the corpus reference rather than as a verdict, because **the library already
    reaches p90/median 2.67 with no roles at all** and the reference is 2.75: role multipliers add on top of a spread
    that is already at target, so a drawing that puts everything in `silhouette` will overshoot and this is where that
    shows. See `roles.py`.
    """
    from .project import load_project

    project = load_project(project_path)
    marks = [m.to_dict() for m in project.live()]
    strokes = [m for m in marks if m['kind'] == 'stroke']
    if not strokes:
        print('  no strokes in this project')
        return 0

    by_role: dict[str, list[float]] = {}
    everything: list[float] = []
    inks: dict[str, set] = {}
    for mark in strokes:
        name = mark['geometry'].get('role', '')
        widths = stroke_widths(mark['geometry'])
        by_role.setdefault(name, []).extend(widths)
        everything.extend(widths)
        inks.setdefault(name, set()).add(mark_ink(mark))

    def ratio(values, fraction):
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]

    median = ratio(everything, 0.5)
    p90 = ratio(everything, 0.9)
    print('  %d strokes, %d width samples' % (len(strokes), len(everything)))
    print('  %-12s %5s  %7s %7s %7s   %s' % ('role', 'n', 'median', 'p90', 'max', 'ink'))
    for name in sorted(by_role, key=lambda r: (r == '', r)):
        values = by_role[name]
        label = name or '(none)'
        ink = sorted(inks[name])[0] if inks.get(name) else ''
        note = roles.ink_verdict(ink) if ink else ''
        print('  %-12s %5d  %7.2f %7.2f %7.2f   %s  %s'
              % (label, len(values), median_of(values), ratio(values, 0.9), max(values), ink, note))

    print()
    print('  this drawing:  p90/median %.2f   max/median %.2f' % (p90 / median, max(everything) / median))
    print('  corpus (276 line drawings, three collections):  %.2f   %.2f'
          % (roles.WIDTH_P90_OVER_MEDIAN, roles.WIDTH_MAX_OVER_MEDIAN))
    print()
    outer = [v for r, vs in by_role.items() if r in ('silhouette', 'shadow') for v in vs]
    inner = [v for r, vs in by_role.items() if r in ('contour', 'detail') for v in vs]
    if outer and inner:
        print('  outer/inner median width: %.2f  (%.2f vs %.2f)'
              % (median_of(outer) / median_of(inner), median_of(outer), median_of(inner)))
        print('  the convention requires a difference that survives reduction; the corpus puts the')
        print('  heavy-to-typical ratio at %.2f, so anything far above that is spending naturalness.' % (
            roles.WIDTH_P90_OVER_MEDIAN))
    else:
        print('  outer/inner comparison needs both kinds present: silhouette or shadow, and contour or detail')
    print()
    for name in sorted(r for r in by_role if r):
        print('  %-12s %s' % (name, roles.trade(name)))
    if '' in by_role:
        print('  %-12s %s' % ('(none)', roles.trade('')))
    return 0


def median_of(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='strokes.svg')
    parser.add_argument('--fit', default='', metavar='IMAGE',
                        help="measure one drawing's linework, on the same scale as the reference library")
    parser.add_argument('--fit-dir', default='', metavar='DIR',
                        help='measure a folder of drawings and pool them against the library')
    parser.add_argument('--bridge', default='', metavar='JSX',
                        help='write the demo sheet as a script for Illustrator')
    parser.add_argument('--svg-out', default='', help='with --bridge: ask Illustrator to export SVG here')
    parser.add_argument('--report', default='', help='with --bridge: where Illustrator writes its report')
    parser.add_argument('--run', action='store_true',
                        help='with --bridge: launch Illustrator; with --xfl: launch Animate')
    parser.add_argument('--psd', default='', metavar='PSD', help='write the demo sheet as a layered PSD for SAI')
    parser.add_argument('--scale', type=float, default=1.0, help='with --psd: pixels per drawing unit')
    parser.add_argument('--paper', default='', metavar='NAME',
                        help='with --render: the surface to draw on, e.g. smooth, drawing, rough, canvas')
    parser.add_argument('--check-body', default='', metavar='FILE',
                        help='validate a proposed body: a JSON object of joint -> parent, against the rig')
    parser.add_argument('--check-layers', default='', metavar='FILE',
                        help='validate a proposed layer stack: a JSON list of {name, tier, part, casts_for}')
    parser.add_argument('--xfl', default='', metavar='XFL', help='write the demo sheet as XFL for Animate')
    parser.add_argument('--render', default='', metavar='PROJECT',
                        help='render a project file to an image; combine with --stage or --upto')
    parser.add_argument('--check', default='', metavar='PROJECT',
                        help='render each pass of a project and report its invariants')
    parser.add_argument('--log', default='', metavar='PROJECT',
                        help='print what has been done to a project, with reasons')
    parser.add_argument('--rewind', type=int, default=-1, metavar='N',
                        help='with --log: undo the last N operations, and save')
    parser.add_argument('--stage', default='', metavar='ROLE',
                        help='with --render: only this pass, e.g. line, value, colour, refine')
    parser.add_argument('--upto', default='', metavar='ROLE',
                        help='with --render: every pass up to and including this one -- the drawing as it stood then')
    parser.add_argument('--audit', default='', metavar='PROJECT',
                        help='draw a project with cairo instead of raster.py, one colour per mark')
    parser.add_argument('--judge', default='', metavar='PROJECT',
                        help='run the independent referees on a project and print the numbers')
    parser.add_argument('--pixels', type=int, default=1400,
                        help='with --audit: pixels across the longer side of the view')
    parser.add_argument('--zoom', default='', metavar='CX,CY,SPAN',
                        help='with --audit: look at one place instead of the whole canvas')
    parser.add_argument('--assign-role', default='', metavar='SPEC',
                        help='with --roles PROJECT: id=role pairs, assigned to strokes that are already drawn')
    parser.add_argument('--uniform', default='', metavar='PROJECT',
                        help='report strokes whose width profile has no variation in it')
    parser.add_argument('--roles', default='', metavar='PROJECT',
                        help="report a project's line roles, their widths, their inks and the trade each makes")
    args = parser.parse_args()
    if args.fit:
        return fit_report(args.fit)
    if args.fit_dir:
        return fit_directory(args.fit_dir)
    if args.bridge:
        return bridge(args.bridge, svg_out=args.svg_out, report=args.report, run=args.run)
    if args.psd:
        return to_psd(args.psd, scale=args.scale)
    if args.xfl:
        return to_xfl(args.xfl, launch=args.run)
    if args.render:
        return render_report(args.render, stage=args.stage, upto=args.upto, out=args.out, scale=args.scale,
                             paper=args.paper)
    if args.check:
        return check_report(args.check, scale=args.scale)
    if args.log:
        return log_report(args.log, rewind_to=args.rewind)
    if args.check_body:
        # **The check exists so a generator can be held to it.** A described body either has the rig's topology or
        # it does not, and "three arms" is a fact about a parent map rather than about a picture.
        import json
        from .body import structural_errors, arity_errors, JOINT_PARENT
        joints = json.load(open(args.check_body, encoding='utf-8'))
        problems = structural_errors(joints) + arity_errors(list(joints.items()))
        if not problems:
            print('%s: the body matches the rig -- %d joints, two arms, two legs, one spine'
                  % (args.check_body, len(joints)))
            return 0
        print('%s: %d problem(s)' % (args.check_body, len(problems)))
        for p in problems:
            print('   ' + p)
        return 1

    if args.check_layers:
        import json
        from .layers import Stack, layer_errors
        raw = json.load(open(args.check_layers, encoding='utf-8'))
        stack = Stack()
        for row in raw:
            stack.add(row['name'], row['tier'], row.get('part', ''), row.get('casts_for', ''))
        problems = layer_errors(stack)
        if not problems:
            print('%s: the layer stack is ordered like the rig -- %d layers' % (args.check_layers, len(stack.layers)))
            return 0
        print('%s: %d problem(s)' % (args.check_layers, len(problems)))
        for p in problems:
            print('   ' + p)
        return 1

    if args.audit:
        return audit_report(args.audit, out=args.out, stage=args.stage, upto=args.upto,
                            pixels=args.pixels, zoom=args.zoom)
    if args.judge:
        return judge_report(args.judge, scale=args.scale)
    if args.assign_role:
        if not args.roles:
            raise SystemExit('--assign-role needs a project: give --roles PROJECT')
        return assign_roles(args.roles, args.assign_role)
    if args.uniform:
        return uniformity_report(args.uniform)
    if args.roles:
        return roles_report(args.roles)
    return demo(args.out)


if __name__ == '__main__':
    raise SystemExit(main())
