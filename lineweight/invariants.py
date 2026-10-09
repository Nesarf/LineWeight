"""Pass invariants: what a pass claims about itself, and whether the rendering bears it out.

**A mechanism, not a rule book.** `DESIGN-PROJECT.md` originally listed four acceptance rules derived from one artist's
recorded process; the second video analysed contradicted three of them, so they were demoted. What is left is this:
a stage may carry any number of invariants, each of which is a small JSON-able predicate over measurements taken from
that stage's rendering, and the checker **reports** rather than refuses.

That distinction is the point, and it is deliberate:

  * a checker that **rejected** would have thrown out the second video's colour pass for having falling saturation,
    when the recording plainly shows a legitimate drawing being made;
  * a checker that **stays silent without an invariant** would let a stage claim nothing and pass anyway, which is
    how a mechanism like this becomes decoration.

So: `check()` returns findings, every stage's invariants are optional, and a stage with none is reported as having
none rather than as passing.

Measurements are taken the same way `analyse.py` takes them from video frames -- relative to the frame's own paper
level, over the pixels that are actually darker than paper -- so a number printed here and a number printed there
mean the same thing.
"""
from __future__ import annotations

from dataclasses import dataclass

# The paper is whatever the bulk of the untouched canvas is. The 90th percentile lands inside it and is insensitive
# to how much of the canvas is covered, which a fixed threshold is not: measured across two videos, the "paper" level
# ran from 233 to 255 within a single file.
PAPER_PERCENTILE = 90
DRAWN_MARGIN = 10.0

# How far below paper a pixel must sit to count as drawn content. The same band split `analyse.py` uses.
BAND_REF = 32
BAND_MID = 150

OPS = {'<': lambda a, b: a < b, '<=': lambda a, b: a <= b,
       '>': lambda a, b: a > b, '>=': lambda a, b: a >= b,
       '==': lambda a, b: a == b, '!=': lambda a, b: a != b}


@dataclass
class Finding:
    """One invariant, judged. `ok` is None when it could not be measured -- which is not the same as passing."""
    stage: str
    name: str
    ok: bool | None
    measured: float | None
    expected: str
    detail: str = ''
    advisory: bool = True

    def line(self) -> str:
        mark = {True: 'ok  ', False: 'FAIL', None: '?   '}[self.ok]
        value = 'not measurable' if self.measured is None else '%.4f' % self.measured
        tail = '  (advisory)' if self.advisory else ''
        return '  %-9s %-4s %-28s %s %s%s' % (self.stage, mark, self.name, value, self.expected, tail)


def measure_layer(layer, background: tuple[int, int, int] = (244, 241, 233)) -> dict:
    """Coverage, lightness, chroma and warmth of what a pass actually put on the canvas.

    Composited over the paper first, because a buffer holds premultiplied-looking straight alpha and a colour that is
    half transparent is not the colour anybody sees. Everything below is measured on what the eye would get.
    """
    w, h = layer.width, layer.height
    total = w * h
    lum = [0.0] * total
    chroma = [0.0] * total
    warmth = [0.0] * total
    covered = 0
    for i in range(total):
        index = i * 4
        a = layer.data[index + 3] / 255.0
        if a <= 0.004:
            r, g, b = background
        else:
            r = layer.data[index] * a + background[0] * (1 - a)
            g = layer.data[index + 1] * a + background[1] * (1 - a)
            b = layer.data[index + 2] * a + background[2] * (1 - a)
            covered += 1
        lum[i] = (r + g + b) / 3.0
        chroma[i] = max(r, g, b) - min(r, g, b)
        warmth[i] = r - b

    ordered = sorted(lum)
    paper = ordered[min(total - 1, int(PAPER_PERCENTILE / 100.0 * total))]
    drawn = [i for i in range(total) if lum[i] < paper - DRAWN_MARGIN]
    if not drawn:
        return {'coverage': covered / total, 'paper': paper, 'drawn': 0,
                'luminance': None, 'saturation': None, 'warmth': None,
                'band_ref': 0.0, 'band_dark': 0.0}

    n = len(drawn)
    return {
        'coverage': covered / total,
        'paper': paper,
        'drawn': n,
        'luminance': sum(lum[i] for i in drawn) / n,
        'saturation': sum(chroma[i] for i in drawn) / n,
        'warmth': sum(warmth[i] for i in drawn) / n,
        # how much of the canvas sits in the faint band a faded reference image would occupy, against how much is
        # genuinely dark. This split is what separates an underlay from the artist's own line.
        'band_ref': sum(1 for i in range(total) if paper - BAND_REF < lum[i] < paper - DRAWN_MARGIN) / total,
        'band_dark': sum(1 for i in range(total) if lum[i] <= paper - BAND_MID) / total,
    }


# Derived quantities an invariant can name. Each takes (current, previous) and may return None when it cannot be
# computed -- a drift against a stage that was never measured is unknown, not zero.
MEASURES = {
    'coverage': lambda c, p: c['coverage'],
    'luminance': lambda c, p: c['luminance'],
    'saturation': lambda c, p: c['saturation'],
    'warmth': lambda c, p: c['warmth'],
    'band_ref': lambda c, p: c['band_ref'],
    'band_dark': lambda c, p: c['band_dark'],
    # |change| in lightness between this pass and the previous one, as a fraction of the previous value. This is the
    # gate that distinguishes "colouring" from "repainting the values": the measured figure across the whole of one
    # video was -4.85% while saturation more than doubled.
    'luminance_drift': lambda c, p: None if not p or c['luminance'] is None or not p.get('luminance')
    else abs(c['luminance'] - p['luminance']) / p['luminance'],
    # how much chroma grew. Above 1 means colour was added; at or below 1 means it was not.
    'saturation_ratio': lambda c, p: None if not p or c['saturation'] is None or not p.get('saturation')
    else c['saturation'] / p['saturation'],
    'paper': lambda c, p: c['paper'],
}


def check(stage: dict, current: dict, previous: dict | None = None, advisory: bool = True) -> list[Finding]:
    """Runs one stage's invariants against its measurements and returns findings. **Never raises, never refuses.**

    A stage with no invariants produces a single finding saying so, rather than an empty list -- an empty list reads
    like a pass, and a stage that claims nothing has not passed anything.
    """
    role = stage.get('role', '?')
    specs = stage.get('invariants') or []
    if not specs:
        return [Finding(role, '(no invariants declared)', None, None, '',
                        'this pass claims nothing about itself', advisory)]

    out: list[Finding] = []
    for spec in specs:
        name = spec.get('name', spec.get('measure', '?'))
        fn = MEASURES.get(spec.get('measure', ''))
        if fn is None:
            out.append(Finding(role, name, None, None, '', 'unknown measure %r' % spec.get('measure'), advisory))
            continue
        try:
            value = fn(current, previous)
        except Exception as exc:                                    # a measurement must not be able to kill a check
            out.append(Finding(role, name, None, None, '', 'measurement raised %s' % exc, advisory))
            continue
        if value is None:
            out.append(Finding(role, name, None, None, '', 'not measurable here', advisory))
            continue
        op = spec.get('op', '<')
        bound = spec.get('value')
        if op not in OPS or bound is None:
            out.append(Finding(role, name, None, value, '', 'bad invariant spec %r' % spec, advisory))
            continue
        ok = OPS[op](value, bound)
        out.append(Finding(role, name, bool(ok), value, '%s %s' % (op, bound), spec.get('note', ''), advisory))
    return out


def check_project(project, images: dict, advisory: bool = True) -> list[Finding]:
    """Checks every stage that was rendered, in order, so a drift has something to be measured against.

    `images` maps a stage role to its measurement dict, as `measure_layer` returns. Missing stages are skipped rather
    than guessed at.
    """
    findings: list[Finding] = []
    previous = None
    for stage in project.stages:
        role = stage['role']
        if role not in images:
            findings.append(Finding(role, '(not rendered)', None, None, '', 'no measurement supplied', advisory))
            continue
        findings.extend(check(stage, images[role], previous, advisory))
        previous = images[role]
    return findings


def format_findings(findings: list[Finding]) -> str:
    """A report a person reads. The `?` rows matter as much as the FAIL rows -- an unmeasurable invariant that looked
    like a pass is how a check quietly stops being one."""
    failed = [f for f in findings if f.ok is False]
    unknown = [f for f in findings if f.ok is None]
    lines = [f.line() for f in findings]
    lines.append('  %d invariant(s): %d failed, %d not measurable'
                 % (len(findings), len(failed), len(unknown)))
    return '\n'.join(lines)
