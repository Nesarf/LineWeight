"""Build a linework reference set, at a recorded scale, from real line drawings.

**Why a second summary.** `tests/data/corpus_summary.json` carries the calibration targets this repository quotes --
an ink fraction of 0.15 and a taper ratio of 0.4213 among them -- and it is built from **929 records of which 645 are
paintings**. The `linework_*` keys pool only the 276 that were judged line drawings, and **that subset was measured at
a median of 656 by 566 pixels.**

**Which is the fact that was missing.** Every comparison made here has set a drawing against "the library" without
saying at what size that library was measured: a generated drawing at 800x600, design sheets at 1920x1357, recorded
line at 2160x3092, against a reference at 656x566. `taper_ratio` is not scale-free -- measured, a twofold change moves
it by 28 per cent -- so those comparisons were crossing scales, and the disagreements they produced were partly that
and not only the material.

**So this measures real line drawings and writes down the size it measured them at.** The material is the design
sheets on F, which are linework by construction rather than by a classifier's judgement, and the sample is stratified
across the three volumes rather than taken from the front of one.

    python build_linework_summary.py --per-volume 60
    python build_linework_summary.py --per-volume 0        # every page, which takes about an hour
"""
import argparse
import json
import pathlib
import statistics
import sys
import time

sys.path.insert(0, r'E:\lineweight')

from lineweight import ref

SHEETS = pathlib.Path(r'F:\素材\图\碧蓝档案官方设定资料')
OUT = pathlib.Path(r'E:\lineweight\tests\data\linework_summary.json')
CACHE = pathlib.Path(r'E:\DaShaoHuo\cache\tmp\linework-summary.json')


def pages(per_volume):
    out = []
    for vol in sorted(p for p in SHEETS.iterdir() if p.is_dir()):
        fs = sorted(vol.glob('*.jpg')) + sorted(vol.glob('*.png'))
        if per_volume and len(fs) > per_volume:
            step = len(fs) / per_volume
            fs = [fs[int(i * step)] for i in range(per_volume)]
        out.extend(fs)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-volume', type=int, default=60)
    args = ap.parse_args()

    fs = pages(args.per_volume)
    print('  %d pages' % len(fs))
    done, t0 = [], time.time()
    for i, f in enumerate(fs, 1):
        try:
            m = ref.measure(str(f))
        except Exception as exc:
            print('    %-28s %s' % (f.name, str(exc)[:60]))
            continue
        done.append(m)
        if i % 10 == 0 or i == len(fs):
            el = time.time() - t0
            print('    %4d/%d  %5.1fs  %4.1f pages/s  %s'
                  % (i, len(fs), el, i / el if el else 0, f.name), flush=True)
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps([m.__dict__ for m in done], default=str), encoding='utf-8')

    usable = [m for m in done if m.line_runs]
    print('  %d measured, %d with enough line runs' % (len(done), len(usable)))
    if not usable:
        return 1

    s = ref.summarise(done)
    widths = [m.width for m in usable]
    heights = [m.height for m in usable]
    s['corpora'] = [{
        'description': 'Blue Archive official design sheets, three volumes, read from a local collection',
        'images': len(done), 'usable': len(usable), 'shared': False, 'tag': 'design-sheets',
    }]
    s['linework_resolution'] = {
        'median_width': int(statistics.median(widths)),
        'median_height': int(statistics.median(heights)),
        'min_width': min(widths), 'max_width': max(widths),
        'note': ('The scale these were measured at, kept because `taper_ratio` is not scale-free: a twofold change '
                 'of canvas moves it by about 28 per cent, so a comparison with a reference measured at another size '
                 'is a comparison of two things.'),
    }
    # the spread, so a later reader can tell a tight set from a ragged one
    for key in ('ink_ratio', 'taper_ratio', 'width_median', 'width_p90'):
        vals = sorted(float(getattr(m, key)) for m in usable if getattr(m, key))
        if vals:
            n = len(vals)
            s['linework_' + key] = {
                'median': round(statistics.median(vals), 4),
                'p10': round(vals[int(0.1 * n)], 4), 'p90': round(vals[int(0.9 * n)], 4),
                'n': n,
            }
    vals = sorted(m.width_p90 / m.width_median for m in usable if m.width_median)
    s['linework_p90_over_median'] = {
        'median': round(statistics.median(vals), 4), 'n': len(vals),
        'p10': round(vals[int(0.1 * len(vals))], 4), 'p90': round(vals[int(0.9 * len(vals))], 4),
    }
    s['totals'] = {'records': len(done), 'linework': len(usable)}
    s['note'] = ('Real line drawings, measured so that a drawing can be calibrated against linework rather than '
                 'against a corpus that is 69 per cent paintings. Recorded with the resolution it was measured at, '
                 'because this quantity moves with the canvas.')

    OUT.write_text(json.dumps(s, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print('  written to %s' % OUT)
    print()
    print('  %-22s %10s %10s %10s' % ('key', 'median', 'p10', 'p90'))
    for key in ('ink_ratio', 'taper_ratio', 'width_median', 'width_p90', 'p90_over_median'):
        b = s.get('linework_' + key)
        if b:
            print('  %-22s %10.4f %10.4f %10.4f' % (key, b['median'], b.get('p10', 0), b.get('p90', 0)))
    print('  resolution %dx%d' % (s['linework_resolution']['median_width'],
                                  s['linework_resolution']['median_height']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
