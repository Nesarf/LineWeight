"""The whole picture from one painted reference, in one command.

**What this replaces.** Reaching the last picture took seven commands in a fixed order, each with its own file in the
middle: trace the structure, build a value layer, tint each region from the reference, fit a gradient inside each
region, split the fills from the strokes, blur the first, multiply the second back. **A pipeline nobody can remember is
a pipeline nobody runs**, and this work has already lost a day to two runs of the same tool disagreeing about their own
settings.

    python tools/paint.py --reference "F:\\...\\illust.jpg" --out-dir E:\\DaShaoHuo\\cache\\paint1

Each stage reports the number it is accepted by, so a bad run is visible in the summary instead of in the picture.
"""
import argparse
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent


def run(label, argv, allow=(0,)):
    proc = subprocess.run([sys.executable] + [str(a) for a in argv], capture_output=True, text=True, cwd=str(ROOT))
    lines = [l.strip() for l in (proc.stdout or '').splitlines() if l.strip()]
    for line in lines[-3:]:
        print('  %-8s %s' % (label, line))
    if proc.returncode not in allow:
        err = (proc.stderr or '').strip().splitlines()
        print('    %s' % (err[-1] if err else 'no message'))
        raise SystemExit('stage %s returned %d' % (label, proc.returncode))
    if proc.returncode == 2:
        print('    %s' % 'the stage reported a value outside its own limit')
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--canvas-side', type=float, default=2880)
    ap.add_argument('--bands', type=int, default=4)
    ap.add_argument('--sat-scale', type=float, default=0.75)
    ap.add_argument('--sigma', type=float, default=5.0)
    ap.add_argument('--keep', type=float, default=0.45)
    ap.add_argument('--no-render', action='store_true')
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = out / 'lines.json'
    value = out / 'value.json'
    tinted = out / 'tinted.json'
    grads = out / 'gradients.json'
    final = out / 'final.png'

    print('  reference %s' % pathlib.Path(args.reference).name)
    run('structure', [HERE / 'edge_line.py', '--src', args.reference, '--out', lines,
                      '--canvas-side', args.canvas_side])
    run('value', [HERE / 'value_pass.py', '--project', lines, '--reference', args.reference,
                  '--out', value, '--bands', args.bands])
    run('tint', [HERE / 'tint_from_reference.py', '--src', value, '--reference', args.reference,
                 '--out', tinted, '--sat-scale', args.sat_scale])
    run('gradient', [HERE / 'gradient_fill.py', '--src', tinted, '--reference', args.reference,
                     '--out', grads])
    if not args.no_render:
        run('compose', [HERE / 'compose_soft.py', '--src', grads, '--out', final,
                        '--sigma', args.sigma, '--keep', args.keep])
        print('  done     %s' % final)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
