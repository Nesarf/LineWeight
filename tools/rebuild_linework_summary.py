"""Rebuild the linework summary with its mixture made explicit.

**What was wrong with the first one.** `build_linework_summary.py` measured every page in the folder and reported a
median per quantity. The folder holds illustrations as well as design sheets -- two pages opened at random are a
painted scene of two characters reading and another of four around a campfire -- and `taper_ratio` is not the same
quantity on the two kinds of picture. So the published median of 0.3893 is the median of a mixture:

    pale   (ink < 0.05)   n  15   taper median 0.4543
    middle                n 113   taper median 0.3987
    dark   (ink > 0.40)   n  52   taper median 0.3521

**A spread of 29 per cent between the halves**, and a number that describes neither. The previous note in this project
recorded the ink spread from 0.058 to 0.856 and read it as the collection being uneven; it is uneven, and the reading
stopped one step short of noticing that the median came out of it.

**This rebuilds from the cached measurements**, which carry every field the summary needs, so it costs seconds rather
than the fifteen minutes a re-measurement would. The cache is checked against the published file first -- a derived
artefact has to be reconciled with its authority before it replaces it.

    python rebuild_linework_summary.py
"""
import json
import pathlib
import statistics

CACHE = pathlib.Path(r'E:\DaShaoHuo\cache\tmp\linework-summary.json')
OUT = pathlib.Path(r'E:\lineweight\tests\data\linework_summary.json')

#: **The cut is a choice and is named as one.** An ink fraction below 0.05 leaves fifteen pages and those are line
#: drawings by eye; below 0.20 leaves 98 and starts including light washes. Rather than pick one and imply the rest
#: are not linework, the summary carries three bands and the median of each, so a caller can see the mixture instead
#: of a single number standing in for it.
BANDS = (('pale', 0.0, 0.05), ('middle', 0.05, 0.40), ('dark', 0.40, 1.01))


def main():
    cached = json.loads(CACHE.read_text(encoding='utf-8'))
    published = json.loads(OUT.read_text(encoding='utf-8'))
    rows = [r for r in cached if r.get('line_runs')]

    # **Reconciled against the file it is about to replace.** The cache was written every ten pages during a run that
    # finished, so the two should hold the same record count; if they do not, the cache is a partial view and
    # rebuilding from it would quietly replace the authority with less than it had.
    published_n = published.get('linework_taper_ratio', {}).get('n')
    print('  cache holds %d usable records, the published summary reports n = %s' % (len(rows), published_n))
    if published_n is not None and published_n != len(rows):
        raise SystemExit('  the cache and the summary disagree about how many pages there were; not rebuilding')
    print('  they agree, so the cache is a complete view of that run')

    def band_of(ink):
        for name, lo, hi in BANDS:
            if lo <= ink < hi:
                return name
        return BANDS[-1][0]

    for name, lo, hi in BANDS:
        g = [r for r in rows if band_of(float(r['ink_ratio'])) == name]
        if not g:
            continue
        t = sorted(float(r['taper_ratio']) for r in g)
        i = sorted(float(r['ink_ratio']) for r in g)
        w = sorted(float(r['width_median']) for r in g)
        print('    %-8s ink %4.2f-%4.2f  n %3d   ink median %.4f   taper median %.4f   width median %.1f'
              % (name, lo, hi, len(g), statistics.median(i), statistics.median(t), statistics.median(w)))

    out = dict(published)
    out['linework_bands'] = {}
    for name, lo, hi in BANDS:
        g = [r for r in rows if band_of(float(r['ink_ratio'])) == name]
        if not g:
            continue
        out['linework_bands'][name] = {
            'ink_from': lo, 'ink_to': hi, 'n': len(g),
            'ink_ratio': round(statistics.median(float(r['ink_ratio']) for r in g), 5),
            'taper_ratio': round(statistics.median(float(r['taper_ratio']) for r in g), 4),
            'width_median': round(statistics.median(float(r['width_median']) for r in g), 2),
        }
    out['mixture_note'] = (
        'This collection holds illustrations as well as design sheets, and `taper_ratio` is not the same quantity on '
        'the two. The headline medians above are therefore medians of a mixture and describe neither kind: the pale '
        'third has a taper of 0.4543 against the dark third\'s 0.3521, 29 per cent apart. `linework_bands` carries the '
        'median of each band so that a caller can compare against the kind of picture it is actually drawing, and the '
        'cut points are a stated choice rather than a measured boundary -- the classifiers tried earlier in this '
        'project both failed, so no band here should be read as "this is linework and that is not".')
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print()
    print('  written to %s, now carrying a band for each kind of page' % OUT.name)
    print()
    print('  ** what this does not do is fix the comparisons already made against the mixture. Their records are in')
    print('     TODO.md and the numbers there are the mixture\'s; this changes what future ones use. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
