"""Is the thing I called a linework reference actually linework, or a mixture?

**The question, and why it is being asked now.** `build_linework_summary.py` measured 180 pages of the Blue Archive
design-sheet collection and wrote `tests/data/linework_summary.json`, which `--fit --against linework` then compares
drawings against. It applied **no filter at all** -- whatever was in the folder was measured. And the folder turns out
to hold illustrations as well as design sheets: two pages opened at random are a full painted scene of two characters
reading and another of four characters around a campfire.

**Which matters because `taper_ratio` is not the same quantity on the two kinds of picture.** A line drawing is lines;
a painted illustration has masses, and the runs its 2..16 pixel window admits come from somewhere else. An earlier
note in this project recorded the spread -- an ink fraction from 0.058 to 0.856 across the set -- and read it as the
collection being uneven. **It is uneven, and the number that came out of it is the median of a mixture.**

    python check_linework_mixture.py
"""
import json
import pathlib
import statistics

CACHE = pathlib.Path(r'E:\DaShaoHuo\cache\tmp\linework-summary.json')


def main():
    rows = [r for r in json.loads(CACHE.read_text(encoding='utf-8')) if r.get('line_runs')]
    ink = sorted(float(r['ink_ratio']) for r in rows)
    taper = sorted(float(r['taper_ratio']) for r in rows)
    n = len(ink)
    print('  the 180 pages the linework reference was built from:')
    print('    ink_ratio  p10 %.4f   median %.4f   p90 %.4f   max %.4f'
          % (ink[n // 10], ink[n // 2], ink[9 * n // 10], ink[-1]))
    print('    taper      p10 %.4f   median %.4f   p90 %.4f'
          % (taper[n // 10], taper[n // 2], taper[9 * n // 10]))

    print()
    print('  how many look like linework rather than a painting, by how little of the page is ink:')
    for cut in (0.02, 0.05, 0.10, 0.20):
        k = sum(1 for x in ink if x < cut)
        print('    ink below %.2f : %3d of %d  (%2.0f%%)' % (cut, k, n, 100.0 * k / n))

    lo = [float(r['taper_ratio']) for r in rows if float(r['ink_ratio']) < 0.05]
    mid = [float(r['taper_ratio']) for r in rows if 0.05 <= float(r['ink_ratio']) <= 0.40]
    hi = [float(r['taper_ratio']) for r in rows if float(r['ink_ratio']) > 0.40]
    print()
    print('  and the taper of each group, which is the number the reference reports:')
    for label, g in (('pale  (ink < 0.05)', lo), ('middle', mid), ('dark  (ink > 0.40)', hi)):
        if g:
            print('    %-20s n %3d   taper median %.4f' % (label, len(g), statistics.median(g)))
    print()
    print('  ** if those medians differ, the published reference is the median of a mixture and says nothing')
    print('     about either half. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
