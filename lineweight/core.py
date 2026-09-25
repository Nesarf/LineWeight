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

# A brush is the same set of numbers a tablet tool exposes, and nothing more.
BRUSHES: dict[str, dict[str, float]] = {
    # name:            width  opacity taper_in taper_out spacing  speed   corner  noise  wobble
    'fine': {'width': 2.0, 'opacity': 1.0, 'taper_in': 0.10, 'taper_out': 0.14, 'spacing': 0.6,
             'speed': 0.35, 'corner': 0.40, 'noise': 0.06, 'wobble': 0.30, 'curve': 1.15},
    'ink': {'width': 6.5, 'opacity': 1.0, 'taper_in': 0.06, 'taper_out': 0.10, 'spacing': 0.5,
            'speed': 0.22, 'corner': 0.30, 'noise': 0.05, 'wobble': 0.26, 'curve': 0.85},
    'pencil': {'width': 4.0, 'opacity': 0.75, 'taper_in': 0.15, 'taper_out': 0.20, 'spacing': 0.8,
               'speed': 0.40, 'corner': 0.45, 'noise': 0.22, 'wobble': 0.38, 'curve': 1.00},
    'wash': {'width': 22.0, 'opacity': 0.35, 'taper_in': 0.30, 'taper_out': 0.40, 'spacing': 1.4,
             'speed': 0.15, 'corner': 0.20, 'noise': 0.10, 'wobble': 0.14, 'curve': 0.70},
}


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
    walked = 0.0
    out: list[float] = []
    noise_state = 0.0
    for i in range(n):
        # 1. how far along the stroke we are, for the tapers at both ends
        t = walked / total
        # 2. speed: a fast stroke presses less. A long straight run reads as fast.
        speed = 0.0
        if 0 < i < n - 1:
            speed = min(1.0, (lengths[i - 1] + lengths[i]) / (2 * total / n) / 4.0)
        # 3. corner: a sharp turn slows the hand and lifts it, so the line thins
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
        # **The taper tests are guarded, because a zero taper is a real brush setting.** `t` accumulates from
        # floating-point lengths and can land a hair above 1.0, so `t > 1.0 - 0` was true often enough to divide by
        # zero. A brush with no taper asked for no taper; the test has to agree.
        if brush['taper_in'] > 0 and t < brush['taper_in']:
            taper = 0.25 + 0.75 * (t / brush['taper_in'])
        elif brush['taper_out'] > 0 and t > 1.0 - brush['taper_out']:
            taper = 0.25 + 0.75 * ((1.0 - t) / brush['taper_out'])
        p = taper * (1.0 - brush['speed'] * speed) * (1.0 - brush['corner'] * corner)
        p *= 1.0 + brush['noise'] * noise_state + brush['noise'] * 0.55 * grain_state
        out.append(max(0.18, min(1.0, p)))
        walked += lengths[i] if i < len(lengths) else 0.0
    return out


def outline(path: list[tuple[float, float]], width: list[float]) -> str:
    """**A stroke with weight is a filled shape, not a stroke.** SVG cannot vary a stroke's width, so the width
    profile is turned into an outline: offset the path to both sides by half the local width and fill the result.

    This is the same operation Illustrator performs when a variable-width stroke is expanded, done here so that the
    output stays plain SVG with no dependence on any application.
    """
    if len(path) < 2:
        return ''
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(path):
        prev = path[max(0, i - 1)]
        nxt = path[min(len(path) - 1, i + 1)]
        dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        half = max(0.35, width[i] / 2.0)
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))
    pts = left + list(reversed(right))
    d = 'M %.2f %.2f ' % pts[0] + ' '.join('L %.2f %.2f' % p for p in pts[1:]) + ' Z'
    return d


def tremble(path: list[tuple[float, float]], amount: float, seed: int) -> list[tuple[float, float]]:
    """Nudges a path sideways the way a hand does, because a line that is exactly where it was aimed is a plot.

    **Two frequencies, and the difference between them is the whole effect.** A slow wander is the arm moving and a
    fast jitter is the wrist; a line with only the slow one looks drugged, one with only the fast one looks nervous,
    and both together look drawn. The nudge is perpendicular to the path, because a hand shakes across its direction
    of travel rather than along it. This is the opposite of what a drawing program's stabiliser does.

    **The amount is a fraction of the brush's width rather than a distance in pixels**, and that is a correction
    rather than a preference: half a pixel is invisible on a six-pixel ink line and enormous on a two-pixel pen, so
    an absolute number means something different on every brush. As a fraction, the same number means the same thing
    everywhere -- measured across the four brushes, a wobble of about a quarter of the width.
    """
    if amount <= 0 or len(path) < 3:
        return list(path)
    rng = random.Random(seed * 7919 + 13)
    slow, fast = 0.0, 0.0
    out: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(path):
        slow = slow * 0.90 + rng.uniform(-1, 1) * 0.10
        fast = fast * 0.45 + rng.uniform(-1, 1) * 0.55
        prev = path[max(0, i - 1)]
        nxt = path[min(len(path) - 1, i + 1)]
        dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        offset = amount * (slow * 1.7 + fast * 0.6)
        out.append((x + nx * offset, y + ny * offset))
    return out


def stroke(points: list[tuple[float, float]], brush_name: str, seed: int = 0,
           colour: str = '#1A1620', resolution: int = 14) -> tuple[str, float]:
    """One stroke: path in, filled outline plus its mean opacity out."""
    return from_record(stroke_record(points, brush_name, seed, colour, resolution))



# -------------------------------------------------------------------------------------------------- path parsing
def parse_path(d: str, samples: int = 10) -> list[list[tuple[float, float]]]:
    """Turns a path string into polylines, which is what a stroke outline needs.

    **Only the commands the generator actually writes are handled**, and that is deliberate rather than lazy: `M`,
    `L`, `Q` and `Z` cover every shape in the shapes a caller supplies, and a parser for the whole of SVG would be a parser
    nobody here can check. An unknown command is skipped rather than guessed at.
    """
    import re
    tokens = re.findall(r'([MLQZmlqz])|(-?\d*\.?\d+)', d)
    polys: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    nums: list[float] = []
    command = ''
    for letter, number in tokens:
        if letter:
            if command == 'Q' and len(nums) >= 4:
                # a quadratic: sample it, so the curve becomes a polyline like everything else
                x0, y0 = current[-1]
                cx, cy, x1, y1 = nums[-4:]
                for i in range(1, samples + 1):
                    t = i / samples
                    mt = 1 - t
                    current.append((mt * mt * x0 + 2 * mt * t * cx + t * t * x1,
                                    mt * mt * y0 + 2 * mt * t * cy + t * t * y1))
            if letter in 'Mm' and current:
                polys.append(current)
                current = []
            if letter in 'Zz' and current:
                current.append(current[0])
                polys.append(current)
                current = []
            command, nums = letter.upper(), []
            continue
        nums.append(float(number))
        if command == 'L' and len(nums) >= 2:
            current.append((nums[0], nums[1]))
            nums = []
        elif command == 'M' and len(nums) >= 2:
            current = [(nums[0], nums[1])]
            nums = []
            command = 'L'
    if command == 'Q' and len(nums) >= 4 and current:
        x0, y0 = current[-1]
        cx, cy, x1, y1 = nums[-4:]
        for i in range(1, samples + 1):
            t = i / samples
            mt = 1 - t
            current.append((mt * mt * x0 + 2 * mt * t * cx + t * t * x1,
                            mt * mt * y0 + 2 * mt * t * cy + t * t * y1))
    if current:
        polys.append(current)
    return [p for p in polys if len(p) >= 2]


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

    def _replace(match: 're.Match[str]') -> str:
        d, rest = match.group(1), match.group(2)
        added: list[str] = []
        # the seam fix: a shape stroked with its own fill colour bleeds outward by half the stroke width and closes
        # the pale hairline that antialiasing leaves between two shapes that touch
        fill = re.search(r'fill="([^"]+)"', rest)
        if fill and fill.group(1) not in ('none', 'transparent'):
            added.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.3" stroke-linejoin="round"/>'
                         % (d, fill.group(1)))
        added.append(match.group(0))
        polys = parse_path(d)
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
            closed = math.dist(poly[0], poly[-1]) < 1.5
            brush_def = dict(BRUSHES[brush])
            brush_def['width'] = brush_def['width'] * scale
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

    return re.sub(r'<path d="([^"]+)"([^/>]*)/>', _replace, svg)


def stroke_record(points: list[tuple[float, float]], brush_name: str, seed: int = 0,
                  colour: str = '#1A1620', resolution: int = 14) -> dict:
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
    path = tremble(path, brush.get('wobble', 0.0) * brush['width'], seed)
    ps = pressures(path, brush, seed)
    return {
        'brush': brush_name,
        'seed': seed,
        'colour': colour,
        'resolution': resolution,
        'control': [[round(x, 3), round(y, 3)] for x, y in points],
        'centre': [[round(x, 3), round(y, 3)] for x, y in path],
        'pressure': [round(p, 4) for p in ps],
    }


def from_record(record: dict) -> tuple[str, float]:
    """Rebuilds a stroke's outline from its record, which is what makes the record worth keeping."""
    brush = BRUSHES[record['brush']]
    path = [(float(x), float(y)) for x, y in record['centre']]
    ps = [float(p) for p in record['pressure']]
    # **The response curve is applied here, at expansion, rather than being baked into the record.** A record holds
    # what the pressure model produced; the curve is a decision about how the brush answers it -- under one it
    # reaches full width early and feels soft, over one it needs real pressure and feels like a pen. Because the
    # curve lives on this side, the same recorded stroke can be re-expanded with a different one, which is the
    # practical difference between keeping the line and keeping only its outline.
    gamma = float(brush.get('curve', 1.0))
    widths = [brush['width'] * (p ** gamma) for p in ps]
    d = outline(path, widths)
    mean_p = sum(ps) / len(ps) if ps else 1.0
    opacity = brush['opacity'] * (0.55 + 0.45 * mean_p)
    return d, opacity


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


def region_fill(polys: list[list[tuple[float, float]]], tolerance: float = 4.0) -> list[str]:
    """Path data for every region the strokes enclose once their gaps have been closed.

    Returned as `d` strings rather than as drawn elements, because what a caller does with a region -- fill it, clip
    to it, paint it black -- is the caller's decision. What this answers is the question a bucket answers: *is
    anything enclosed here*, given a drawing made by somebody whose lines do not always meet.
    """
    out: list[str] = []
    for loop in weld_endpoints(polys, tolerance):
        points = ['%.2f %.2f' % (x, y) for x, y in loop]
        out.append('M ' + ' L '.join(points) + ' Z')
    return out


def fit_report(image_path: str) -> int:
    """Measures a real illustration's linework, so the brushes above can be checked against art rather than taste.

    What is measurable from a flat image is the *appearance* of pressure: how the darkness of a line varies along
    it, and how its thickness is distributed. Both are reported as distributions, which is what a brush's curves
    would have to reproduce.
    """
    try:
        from PIL import Image
    except ImportError:
        print('pillow is needed for --fit')
        return 2
    image = Image.open(image_path).convert('L')
    w, h = image.size
    px = image.load()
    dark = [sum(1 for x in range(w) if px[x, y] < 128) for y in range(h)]
    ink_rows = [c for c in dark if c > 0]
    vertical = [sum(1 for y in range(h) if px[x, y] < 128) for x in range(w)]
    ink_cols = [c for c in vertical if c > 0]
    print('  %s  %dx%d' % (os.path.basename(image_path), w, h))
    if ink_rows:
        ink_rows.sort()
        print('  horizontal ink per row: min %d, median %d, p90 %d, max %d'
              % (ink_rows[0], ink_rows[len(ink_rows) // 2], ink_rows[int(len(ink_rows) * 0.9)], ink_rows[-1]))
    if ink_cols:
        ink_cols.sort()
        print('  vertical ink per column: median %d, p90 %d' % (ink_cols[len(ink_cols) // 2],
                                                               ink_cols[int(len(ink_cols) * 0.9)]))
    print('  a brush whose widths have the same spread is a brush that matches this drawing')
    return 0


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
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(parts))
    print('  %s' % out_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='strokes.svg')
    parser.add_argument('--fit', default='', help='measure an illustration\'s linework instead of drawing')
    args = parser.parse_args()
    if args.fit:
        return fit_report(args.fit)
    return demo(args.out)


if __name__ == '__main__':
    raise SystemExit(main())
