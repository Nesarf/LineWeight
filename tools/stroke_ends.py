"""How many places does this drawing stop?

**A quantity aimed at the thing that is actually wrong.** Every measurement tried so far was designed for a picture
that is one connected whole -- `taper_ratio` is the thinnest fifth of the runs over their mean, and on this drawing
that fifth is six finger bones, so it reports how thin the fingers were drawn rather than how the drawing behaves.
**What is wrong here is continuity**: a drawing is a line travelling, and this is a set of marks that stop and start.

**The count of stops is the direct measure of that**, and it needs no window, no threshold and no reference to a
corpus of illustrations. Before the chaining change the figure was thirty-three strokes and therefore sixty-six ends;
now it is thirteen chains and twenty-six. **Cutting it from sixty-six to twenty-six is what the change did**, and this
is the number that says so -- where `taper_ratio` said the opposite.

**What it cannot do is say how many is right**, and that is the gap it exposes: the number is comparable between two
versions of this drawing and not against anything else, because the material on hand is 180 design-sheet pages that
turn out to hold illustrations as well as linework, and 332 pixiv works tagged for cel shading. Neither is linework to
compare a line drawing against.

    python stroke_ends.py
"""
import json
import math
import pathlib
import statistics

PROJECT = pathlib.Path(r'E:\DaShaoHuo\cache\cel-drawing.json')


def main():
    d = json.loads(PROJECT.read_text(encoding='utf-8'))
    strokes = [m for m in d['marks'] if m.get('kind') == 'stroke']
    fills = [m for m in d['marks'] if m.get('kind') == 'fill']

    lengths = []
    for m in strokes:
        pts = [tuple(p) for p in m['geometry']['centre']]
        total = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        lengths.append((m.get('provenance', {}).get('note', '?'), total, len(pts)))

    print('  %d strokes and %d fills' % (len(strokes), len(fills)))
    print('  ends: %d  -- every stroke has exactly two, and a drawing that is one line has two as well' % (2 * len(strokes)))
    lengths.sort(key=lambda r: -r[1])
    total = sum(l for _, l, _ in lengths)
    print('  total path length %.0f px over %d strokes' % (total, len(lengths)))
    print()
    print('  the longest strokes:')
    for note, L, n in lengths[:6]:
        print('    %-34s %7.0f px over %3d points' % (note, L, n))
    print('  the shortest:')
    for note, L, n in lengths[-4:]:
        print('    %-34s %7.0f px over %3d points' % (note, L, n))
    print()
    print('  length: median %.0f px   mean %.0f   longest %.0f' % (
        statistics.median(l for _, l, _ in lengths), total / len(lengths), lengths[0][1]))
    print()
    print('  and the same count for the two versions:')
    print('    per bone  : 33 strokes, 66 ends')
    print('    per chain : %d strokes, %d ends' % (len(strokes), 2 * len(strokes)))
    print()
    print('  ** `taper_ratio` said this change made the drawing worse -- it fell from 0.3426 to 0.2393 -- and it said')
    print('     that because joining the limbs raised the mean width without touching the fingers, which are what that')
    print('     ratio is measuring here. **This** number moved the way the picture did: fewer places where the line')
    print('     stops. **')
    print()
    print('  ** What it cannot say is how many ends a finished drawing should have.** For that the comparison has to')
    print('     be against linework, and nothing on this machine is linework: the 180 design-sheet pages hold')
    print('     illustrations mixed in -- two opened at random are painted scenes -- and the 332 pixiv works were')
    print('     tagged for cel shading, not for lines. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
