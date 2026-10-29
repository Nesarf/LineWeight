"""The whole picture from one painted reference, in one command.

**What this replaces.** Reaching a picture took seven commands in a fixed order, each with its own file in the middle:
trace the structure, cut the colour areas, fit a gradient inside each, split the fills from the strokes, blur the first,
multiply the second back. **A pipeline nobody can remember is a pipeline nobody runs**, and this work has already lost a
day to two runs of the same tool disagreeing about their own settings.

**Two ways to get the line layer, and the picture decides which.**

`boundary` cuts the reference into colour areas once, takes the joins between them as the line candidate, and keeps only
the joins a much coarser cut also sees. It is the default because it survives a reference the gradient route cannot
handle: a starfield is a field of point highlights, so the gradient is noise everywhere and the skeleton walk has no end
-- measured on the third reference, twenty minutes with no output.

`gradient` is the older route: Canny on tone, colour used as a veto, then the same walk and join. It found structure the
boundary route misses on a painted picture with clear contours, so it is kept rather than deleted.

**The cut happens once.** The fills pass writes its areas beside its project, and the line pass reads them, so a line
lands on exactly the boundary it describes instead of on a second cut that missed by a pixel.

    python tools/paint.py --reference "F:\\...\\illust.jpg" --out-dir E:\\DaShaoHuo\\cache\\run

Each stage reports the number it is accepted by, so a bad run is visible in the summary instead of in the picture.
"""
import argparse
import json
import pathlib
import subprocess
import sys

from PIL import Image

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


def skeleton(path, width, height, title):
    """A project with a canvas and no marks, so the stages that need a page to draw on have one."""
    doc = {'version': 2, 'canvas': {'width': int(width), 'height': int(height)}, 'title': title,
           'stages': [], 'log': [], 'counter': 0, 'incremental': False, 'turn': 0, 'figure': None, 'marks': []}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    return path


def render_project(src, out, sweep=False):
    argv = [sys.executable, '-m', 'lineweight', '--render', str(src), '--out', str(out)]
    if sweep:
        argv.append('--sweep')
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=str(ROOT))
    lines = [l.strip() for l in (proc.stdout or '').splitlines() if l.strip()]
    print('  %-8s %s' % ('render', lines[-2] if len(lines) > 1 else (lines[-1] if lines else 'no output')))
    if proc.returncode != 0:
        print('    %s' % ((proc.stderr or '').strip().splitlines() or ['no message'])[-1])
        raise SystemExit('render returned %d' % proc.returncode)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--line-source', choices=('boundary', 'gradient'), default='boundary')
    ap.add_argument('--canvas-side', type=float, default=2880)
    ap.add_argument('--levels', type=int, default=20, help='quantisation levels per channel for the colour areas')
    ap.add_argument('--min-area', type=int, default=150, help='colour areas below this are folded into a neighbour')
    ap.add_argument('--max-shapes', type=int, default=30000,
                    help='how many areas the picture may be cut into; above this the minimum area rises until it fits. '
                         'Zero turns the budget off. A safety valve, not a working limit: a fill now rasterises into its '
                         'own box, so twenty-seven thousand areas finish in under eight minutes')
    ap.add_argument('--blur', type=float, default=1.0, help='blur before quantising, at the cut size')
    ap.add_argument('--sigma', type=float, default=5.0)
    ap.add_argument('--keep', type=float, default=0.45)
    ap.add_argument('--sweep', action='store_true',
                    help='lay every stroke down as a distance field instead of as stamped discs: the edge loses the '
                         'stamp-pitch scallop, measured at 1.89 pixels of width wobble against 0.76 on the widest '
                         'brush, and the render costs two to eight times more')
    ap.add_argument('--no-render', action='store_true')
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = out / 'lines.json'
    shapes = out / 'shapes.json'
    grads = out / 'gradients.json'
    strokes = out / 'lines.png'
    final = out / 'final.png'

    # **The canvas is decided here, once.** Both routes used to compute it from their own arguments, so a picture could
    # come out with the fills on a 2880 wide page and the lines on a 3456 wide one.
    ref = Image.open(args.reference)
    ref_long = float(max(ref.size))
    canvas_long = max(2880.0, ref_long * 1.2, args.canvas_side)
    width = int(round(ref.size[0] * canvas_long / ref_long))
    height = int(round(ref.size[1] * canvas_long / ref_long))
    board = skeleton(out / 'board.json', width, height, 'canvas of %s' % pathlib.Path(args.reference).stem)

    print('  reference %s  canvas %dx%d  lines from the %s'
          % (pathlib.Path(args.reference).name, width, height, args.line_source))

    if args.line_source == 'gradient':
        run('structure', [HERE / 'edge_line.py', '--src', args.reference, '--out', lines,
                          '--canvas-side', args.canvas_side])
        project = lines
    else:
        run('shapes', [HERE / 'shape_pass.py', '--project', board, '--reference', args.reference,
                       '--out', shapes, '--levels', args.levels, '--min-area', args.min_area,
                       '--max-shapes', args.max_shapes, '--blur', args.blur])
        run('lines', [HERE / 'edge_strokes.py',
                      '--labels', shapes.with_name('%s-labels.npy' % shapes.stem),
                      '--meta', shapes.with_name('%s-meta.json' % shapes.stem),
                      '--reference', args.reference, '--out', lines])
        project = shapes
        if not args.no_render:
            render_project(lines, strokes, args.sweep)

    if args.line_source == 'gradient':
        run('shapes', [HERE / 'shape_pass.py', '--project', project, '--reference', args.reference,
                       '--out', shapes, '--levels', args.levels, '--min-area', args.min_area,
                       '--max-shapes', args.max_shapes, '--blur', args.blur])

    run('gradient', [HERE / 'gradient_fill.py', '--src', shapes, '--reference', args.reference, '--out', grads])

    # **One project, not two.** The fills and the lines were separate files that only met when a PNG was composited, so the
    # drawing could not be revised as one drawing -- "revise this line by id" had no single file to look in. They are
    # combined here, and the composer then reads that one file and splits it by kind for the two-layer render: the blur
    # belongs to the shading, not to the filing.
    picture = out / 'picture.json'
    if args.line_source == 'boundary':
        run('merge', [HERE / 'merge_projects.py', '--fills', grads, '--lines', lines, '--out', picture])
    if not args.no_render:
        source = picture if args.line_source == 'boundary' else grads
        argv = [HERE / 'compose_soft.py', '--src', source, '--out', final,
                '--sigma', args.sigma, '--keep', args.keep]
        if args.sweep:
            argv.append('--sweep')
        run('compose', argv)
        print('  done     %s' % final)
        if args.line_source == 'boundary':
            print('  project  %s' % picture)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
