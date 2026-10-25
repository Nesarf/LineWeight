"""One command for the whole procedure: a reference in, four stages out, and the number each stage promises.

**Why this exists as a separate file.** The four stages were written as four tools, and a procedure that needs four
correct command lines in the right order is a procedure nobody runs twice. This runs them, in order, and prints **the
number each stage is accepted by** -- the line count, the band count, the colour drift, the refinement's drift --
so that a bad run is visible in the summary rather than in the picture.

**The stages are the ones `DRAWING-PROCEDURE.md` names**, and the order is not negotiable:

    trace     the line layer, width read off the ink          acceptance: lines and their weights
    value     the value pass, bands from the histogram        acceptance: zero saturation
    colour    hue and saturation over a fixed value           acceptance: lightness drift under 5 per cent
    refine    the same value, uneven saturation               acceptance: saturation up, drift still under 5

    python tools/pipeline.py --reference "F:\\素材\\图\\16+\\Cache_7cef975685e2f0c2.png" --out-dir E:\\DaShaoHuo\\cache\\run1
"""
import argparse
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent


def run(label, argv, allow=(0,)):
    cmd = [sys.executable] + [str(a) for a in argv]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    lines = [l for l in (proc.stdout or '').splitlines() if l.strip()]
    tail = lines[-1].strip() if lines else '(no output)'
    print('  %-8s %s' % (label, tail))
    if proc.returncode not in allow:
        err = (proc.stderr or '').strip().splitlines()
        print('    %s' % (err[-1] if err else 'no message'))
        raise SystemExit('stage %s returned %d' % (label, proc.returncode))
    if proc.returncode == 2:
        print('    %s' % 'the stage reported a value over its own limit')
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--canvas-side', type=int, default=960)
    ap.add_argument('--bands', type=int, default=4)
    ap.add_argument('--hue', type=float, default=0.075)
    ap.add_argument('--sat', type=float, default=0.45)
    ap.add_argument('--gain', type=float, default=0.8)
    ap.add_argument('--lift', type=float, default=0.35)
    ap.add_argument('--no-render', action='store_true')
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = out / 'lines.json'
    value = out / 'value.json'
    colour = out / 'colour.json'
    refined = out / 'refined.json'
    png = out / 'final.png'

    print('  reference %s' % pathlib.Path(args.reference).name)
    run('trace', [HERE / 'copy_linework.py', '--src', args.reference, '--out', lines,
                  '--canvas-side', args.canvas_side])
    run('value', [HERE / 'value_pass.py', '--project', lines, '--reference', args.reference,
                  '--out', value, '--bands', args.bands])
    run('colour', [HERE / 'colourise.py', '--src', value, '--out', colour,
                   '--hue', args.hue, '--sat', args.sat], allow=(0, 2))
    run('refine', [HERE / 'refine.py', '--src', colour, '--out', refined,
                   '--gain', args.gain, '--lift', args.lift], allow=(0, 2))
    if not args.no_render:
        run('render', ['-m', 'lineweight', '--render', refined, '--out', png])
        print('  done     %s' % png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
