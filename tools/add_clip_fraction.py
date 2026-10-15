"""Add the clip fraction to the summaries, and make `--fit` print both sides of it.

**Why this field.** `ref.measure` admits a run as a line only between 2 and 16 pixels, so `taper_ratio` -- the
thinnest fifth of the admitted runs over their mean -- is computed on a subset, and **which subset depends on the
canvas**: the same project rendered at 400x300 excludes 31 per cent of its runs and at 1920x1440 excludes 56, while the
measured median width falls from 5.0 to 3.0 because the wide runs are the ones being dropped.

Measured on real material: sixty design sheets exclude a median of 51.5 per cent. So **both sides of every taper
comparison made in this project have been clipped, by different amounts**, and the fraction is the thing that says
whether the two are comparable at all. It is derivable from what a measurement already carries -- `runs` and
`line_runs` -- and it was simply never printed.

    python add_clip_fraction.py
"""
import json
import pathlib
import statistics

REPO = pathlib.Path(r'E:\lineweight')
CACHE = pathlib.Path(r'E:\DaShaoHuo\cache\tmp\linework-summary.json')


def main():
    cache = json.loads(CACHE.read_text(encoding='utf-8'))
    usable = [r for r in cache if r.get('line_runs')]
    frac = sorted(100.0 * (r['runs'] - r['line_runs']) / r['runs'] for r in usable if r.get('runs'))
    n = len(frac)
    block = {
        'median': round(statistics.median(frac), 2),
        'p10': round(frac[n // 10], 2), 'p90': round(frac[9 * n // 10], 2), 'n': n,
        'meaning': ('the share of runs wider than 16 px or narrower than 2, which `taper_ratio` therefore does not '
                    'see. Both sides of a taper comparison are clipped by this much, and the ratio is only '
                    'comparable when the two fractions are close.'),
    }
    print('  from %d cached design sheets: excluded median %.1f%%  p10 %.1f  p90 %.1f'
          % (n, block['median'], block['p10'], block['p90']))

    for name in ('linework_summary.json', 'corpus_summary.json'):
        p = REPO / 'tests' / 'data' / name
        if not p.exists():
            print('  %s: not present' % name)
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        if name == 'linework_summary.json':
            d['linework_excluded'] = block
            note = 'measured here, from the same pages'
        else:
            # **The corpus images are not in this repository, so this number cannot be measured.** It is left absent
            # rather than estimated: a guessed clip fraction would be exactly the kind of plausible number this whole
            # line of work is about.
            d['linework_excluded'] = {
                'median': None, 'n': 0,
                'meaning': ('not recorded, and not guessable: the corpus images are not in this repository and this '
                            'fraction has to be measured from them. Until it is, a taper comparison against this '
                            'summary has one side unclipped-unknown.'),
            }
            note = 'left absent, deliberately'
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print('  %-26s %s' % (name, note))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
