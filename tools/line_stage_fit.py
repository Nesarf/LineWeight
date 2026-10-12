"""Do real drawings, at their line stage, sit in the same distribution as the library's corpus?

**The question left open by `--fit`.** Two real design sheets pooled to a taper ratio of 0.5801 against the library's
0.4213, and nothing said whether that is a difference between two kinds of material -- illustrations against design
sheets -- or a sign that `taper_ratio` is sensitive to something else. The frames on G are **37,729 of a real artist
drawing**, which is a third kind of material, and this measures them the same way.

**Which frames, and why not all of them.** The last frame of a video is a finished painting -- `fracture`'s is a night
sky with an aurora and no linework in it at all -- and `ref.measure` measures the widths of lines. **Measuring a
painting with it measures nothing.** So the frames are chosen from the per-frame record already computed: a frame is
in the line stage when **little of the canvas is filled dark**, which is `band_dark` low, and when there is enough ink
to measure at all. That is a selection made from a measurement rather than from a guess at a frame number.

    python line_stage_fit.py [--per-video 30]
"""
import argparse
import json
import pathlib
import statistics
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import ref

ANALYSIS = pathlib.Path(r'G:\lineweight-video\videos')
FRAMES = pathlib.Path(r'G:\lineweight-video\frames')
LIB = pathlib.Path(r'E:\lineweight\tests\data\corpus_summary.json')


def line_stage_frames(vid, want):
    """Up to `want` frames spread across the video's line stage, from the record rather than by guessing."""
    a = json.loads((ANALYSIS / vid / 'analysis.json').read_text(encoding='utf-8'))
    pf = a.get('per_frame') or []
    if not pf:
        return []
    # **The dark band is the discriminator.** Solid fill drives it up and a line drawing keeps it near zero; `ink`
    # alone cannot tell the two apart, which is the fault the corpus classification ran into and never got past.
    dark = sorted(r.get('band_dark', 0.0) for r in pf)
    cut = dark[int(0.35 * len(dark))]
    # **the records themselves, not pairs** -- the first version kept `enumerate`'s tuple and then indexed it
    scored = [r for r in pf if r.get('band_dark', 1.0) <= cut and r.get('ink', 0.0) > 0.004]
    if not scored:
        return []
    step = max(1, len(scored) // want)
    return [r['n'] for r in scored[::step][:want]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-video', type=int, default=30)
    args = ap.parse_args()

    library = json.loads(LIB.read_text(encoding='utf-8'))
    keys = ('ink_ratio', 'width_median', 'width_p90', 'taper_ratio')
    lib = {k: library.get('linework_' + k, {}).get('median') for k in keys}
    print('library (linework): ' + '  '.join('%s %.4f' % (k, lib[k]) for k in keys if lib[k] is not None))
    print()

    pooled = []
    print('%-24s %5s %10s %8s %8s %8s %8s' %
          ('video', 'n', 'taper', 'ink', 'w med', 'w p90', 'px'))
    for d in sorted(ANALYSIS.iterdir()):
        vid = d.name
        if vid.endswith('-restream') or not (FRAMES / vid).is_dir():
            continue
        picks = line_stage_frames(vid, args.per_video)
        rows = []
        for n in picks:
            p = FRAMES / vid / ('%06d.png' % n)
            if not p.exists():
                continue
            try:
                m = ref.measure(str(p))
            except Exception as exc:
                print('    %s frame %d: %s' % (vid, n, str(exc)[:60]))
                continue
            if m.line_runs:
                rows.append(m)
        if not rows:
            print('%-24s %5d   nothing measurable' % (vid, 0))
            continue
        t = statistics.median(r.taper_ratio for r in rows)
        i = statistics.median(r.ink_ratio for r in rows)
        wm = statistics.median(r.width_median for r in rows)
        wp = statistics.median(r.width_p90 for r in rows)
        px = statistics.median(r.width * r.height for r in rows)
        pooled += rows
        print('%-24s %5d %10.4f %8.4f %8.1f %8.1f %8.0f' % (vid, len(rows), t, i, wm, wp, px))

    if not pooled:
        print('\n  nothing measured')
        return 1
    print()
    t = statistics.median(r.taper_ratio for r in pooled)
    i = statistics.median(r.ink_ratio for r in pooled)
    wm = statistics.median(r.width_median for r in pooled)
    wp = statistics.median(r.width_p90 for r in pooled)
    print('  pooled over %d frames of real drawing, at their line stage' % len(pooled))
    print('    taper ratio   %.4f      library %.4f      ratio %.2f'
          % (t, lib['taper_ratio'] or 0, t / lib['taper_ratio'] if lib['taper_ratio'] else 0))
    print('    ink fraction  %.4f      library %.4f      (both scale-dependent)' % (i, lib['ink_ratio'] or 0))
    print('    width median  %.1f       library %.1f' % (wm, lib['width_median'] or 0))
    print('    width p90     %.1f       library %.1f' % (wp, lib['width_p90'] or 0))
    print()
    print('  ** only the taper row is a comparison. The canvases here are 1080x1524 to 3378x2160 and the library\'s')
    print('     are whatever its corpus is, so the widths are lengths at two different scales. **')


if __name__ == '__main__':
    raise SystemExit(main())
