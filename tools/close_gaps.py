"""Join the ends that were one line: a short stroke wherever two strokes stop facing each other.

**Where the gaps come from, and it is not the drawing.** The ink of a pencil line is not continuous -- a light pass, a
JPEG's ringing, a place where the pen lifted and came back -- so the skeleton breaks and the trace faithfully records a
break. Measured on one reference, the traced line layer had hundreds of strokes for a few dozen lines. **A drawing does
not have those gaps**; they are an artefact of reading a line as a set of pixels.

**The rule for joining, and it is deliberately narrow.** Two ends are joined when they are within a few pixels of each
other and their directions, continued forward, point at one another. **Proximity alone is not enough**: in a crowded
corner every end is near every other, and joining on distance draws a net. Direction is what makes a join physical
rather than geometric.

    python tools/close_gaps.py --src lines.json --out joined.json --max-gap 5
"""
import argparse
import json
import math
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project


def ends_of(mark):
    """The two ends of a stroke, each with the direction it is travelling in as it leaves."""
    centre = (mark.get('geometry') or {}).get('centre') or []
    if len(centre) < 2:
        return []
    head = (float(centre[0][0]), float(centre[0][1]))
    next1 = (float(centre[1][0]), float(centre[1][1]))
    tail = (float(centre[-1][0]), float(centre[-1][1]))
    prev = (float(centre[-2][0]), float(centre[-2][1]))

    def unit(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        return (dx / n, dy / n)

    # **Outward at each end**: at the start the stroke travels from head to next, so outward is the reverse.
    return [(head, (-unit(head, next1)[0], -unit(head, next1)[1])),
            (tail, unit(prev, tail))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-gap', type=float, default=5.0, help='page pixels; beyond this two ends are two lines')
    ap.add_argument('--min-align', type=float, default=0.55,
                    help='how much the two directions must face each other, 1 is head on')
    ap.add_argument('--report', action='store_true')
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.src).read_text(encoding='utf-8'))
    marks = doc.get('marks', [])
    records = []
    for i, mark in enumerate(marks):
        if mark.get('kind') != 'stroke':
            continue
        for point, direction in ends_of(mark):
            records.append({'mark': i, 'point': point, 'dir': direction})

    pairs = []
    for a in range(len(records)):
        ra = records[a]
        for b in range(a + 1, len(records)):
            rb = records[b]
            if ra['mark'] == rb['mark']:
                continue
            dx = rb['point'][0] - ra['point'][0]
            dy = rb['point'][1] - ra['point'][1]
            gap = math.hypot(dx, dy)
            if gap > args.max_gap or gap < 1e-6:
                continue
            ux, uy = dx / gap, dy / gap
            # **Each end must be heading toward the other.** The score is the smaller of the two alignments, so an end
            # that points away vetoes the join however close it is.
            score = min(ra['dir'][0] * ux + ra['dir'][1] * uy,
                        -(rb['dir'][0] * ux + rb['dir'][1] * uy))
            if score < args.min_align:
                continue
            pairs.append((gap, score, a, b))

    pairs.sort(key=lambda t: (-t[1], t[0]))
    used = set()
    joined = 0
    new_marks = []
    for gap, score, a, b in pairs:
        if a in used or b in used:
            continue
        used.add(a)
        used.add(b)
        pa, pb = records[a]['point'], records[b]['point']
        length = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if length < 0.5:
            continue
        # **One short stroke, with a width of the two it joins.** A bridge drawn wider than its neighbours shows as a
        # lump at exactly the place the eye is looking for continuity.
        widths = [(marks[records[a]['mark']].get('geometry') or {}).get('width_profile') or [2.0],
                  (marks[records[b]['mark']].get('geometry') or {}).get('width_profile') or [2.0]]
        w = 0.5 * (float(widths[0][0]) + float(widths[1][0]))
        joined += 1
        new_marks.append({
            'kind': 'stroke',
            'stage': 'line',
            'layer': marks[records[a]['mark']].get('layer', 'ink'),
            'geometry': {
                'brush': 'fine',
                'control': [list(pa), list(pb)],
                'centre': [list(pa), list(pb)],
                'pressure': [1.0, 1.0],
                'seed': joined,
                'resolution': 2,
                'width_profile': [w, w, w],
                'alpha_profile': [],
            },
            'appearance': dict(marks[records[a]['mark']].get('appearance') or {}),
            'provenance': {'source': args.src, 'note': 'gap bridge', 'turn': 0},
            'state': 'live',
        })

    base = [max((m.get('id') or 'm0') for m in marks if m.get('id'))] if marks else [0]
    for k, mark in enumerate(new_marks):
        mark['id'] = 'g%04d' % (k + 1)
        mark['seq'] = len(marks) + k
    doc['marks'] = marks + new_marks
    pathlib.Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('  %d stroke ends, %d joined by bridges' % (len(records), joined))
    print('  written to %s' % args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
