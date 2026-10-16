"""Which bones are the thinnest fifth of this drawing?

**The hypothesis this tests.** Against the pale band of the linework reference the drawing is 25 per cent low on
`taper_ratio`, and neither pose nor line width turned out to be the variable that fixes it -- thickening every line
raises the taper and the ink together, so the two targets have no point in common. That leaves how the picture is put
together:

> **This drawing is twenty limbs that do not join; a line drawing is one connected picture.** `taper_ratio` is the
> thinnest fifth of the runs the 2..16 pixel window admits, over their mean -- **and in a connected drawing those
> thinnest runs are the ends of strokes and the turns, while here they are the thinnest bones, which are fingers.**

**Two things have to be true for that to explain the gap**, and both are measured here rather than argued:

  * **the thinnest fifth is concentrated**, not spread across the drawing -- if every bone contributed, the ratio
    would be describing the drawing as a whole;
  * **the thick end falls outside the window.** The window admits 2 to 16 pixels, so a limb wider than sixteen is
    dropped from the sample entirely, and `taper_ratio` is then the ratio among the thin runs alone.

**The widths are read from the project file**, which is what the renderer actually used, rather than recomputed from
the table in the drawing tool.

    python thinnest_fifth.py
"""
import json
import pathlib
import statistics

PROJECT = pathlib.Path(r'E:\DaShaoHuo\cache\cel-drawing.json')
WINDOW = (2.0, 16.0)


def bone_of(note):
    return note.replace('bone ', '').strip() if note else '?'


def main():
    d = json.loads(PROJECT.read_text(encoding='utf-8'))
    strokes = [m for m in d['marks'] if m.get('kind') == 'stroke']
    print('  %d strokes in the project' % len(strokes))

    rows = []
    for m in strokes:
        prof = m.get('geometry', {}).get('width_profile') or []
        if not prof:
            continue
        rows.append({
            'bone': bone_of(m.get('provenance', {}).get('note') or m.get('note') or ''),
            'layer': m.get('layer', ''),
            'median': statistics.median(prof),
            'min': min(prof),
            'max': max(prof),
        })
    rows.sort(key=lambda r: r['median'])
    n = len(rows)
    print('  width range over all strokes: %.2f .. %.2f px' % (rows[0]['median'], rows[-1]['median']))
    print()

    fifth = max(1, n // 5)
    print('  the thinnest fifth (%d of %d strokes), by the width the renderer used:' % (fifth, n))
    for r in rows[:fifth]:
        print('    %-26s %-8s median %.2f px  (%s..%s)' % (r['bone'], r['layer'], r['median'], r['min'], r['max']))

    thin_names = {r['bone'] for r in rows[:fifth]}
    print()
    print('  and what they are:')
    finger_like = sum(1 for b in thin_names if 'Finger' in b or 'Toe' in b)
    print('    strokes whose name contains Finger or Toe : %d of %d' % (finger_like, len(thin_names)))
    for kw in ('Finger', 'Toe', 'Hand', 'Foot', 'Forearm', 'Calf'):
        k = sum(1 for r in rows[:fifth] if kw in r['bone'])
        if k:
            print('      %-10s %d' % (kw, k))

    # **And the window.** A run wider than sixteen pixels is not counted at all, so the thick limbs are absent from
    # the sample rather than present at their true width -- which changes what the ratio is a ratio of.
    print()
    print('  the 2..16 px window:')
    inside = [r for r in rows if WINDOW[0] <= r['median'] <= WINDOW[1]]
    over = [r for r in rows if r['median'] > WINDOW[1]]
    under = [r for r in rows if r['median'] < WINDOW[0]]
    print('    strokes whose median width is inside it : %d' % len(inside))
    print('    above it, so not counted at all         : %d  (%s)'
          % (len(over), ', '.join(r['bone'] for r in over[:6])))
    print('    below it                                : %d' % len(under))

    if inside:
        inside.sort(key=lambda r: r['median'])
        m = len(inside)
        lo = inside[:max(1, m // 5)]
        hi = inside[-max(1, m // 5):]
        print()
        print('  among the strokes the window actually admits:')
        print('    thinnest fifth median width %.2f px   (%s)'
              % (statistics.median(r['median'] for r in lo), ', '.join(r['bone'] for r in lo[:5])))
        print('    mean over all admitted       %.2f px' % statistics.mean(r['median'] for r in inside))
        print('    their ratio                  %.4f     (the reference band sits at 0.4543)'
              % (statistics.median(r['median'] for r in lo) / statistics.mean(r['median'] for r in inside)))
        print('    thickest fifth median width  %.2f px   (%s)'
              % (statistics.median(r['median'] for r in hi), ', '.join(r['bone'] for r in hi[:5])))
    print()
    print('  ** if the thinnest fifth is fingers and toes, then `taper_ratio` here is measuring how thin the fingers')
    print('     were drawn, and not how a drawing behaves. Those are two different questions, and the reference was')
    print('     measured on pictures where the answer is the second one. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
