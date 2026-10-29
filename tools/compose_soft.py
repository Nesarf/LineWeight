"""Soft shading under a sharp line: render the two halves of a drawing separately and put them together.

**Why the edge reads hard.** The value layer is four flat bands, so every boundary between them is a step of a whole
value -- which is what a poster looks like, not what a painting does. The steps are not wrong as *decisions*; they are
wrong as *edges*. A painting arrives at the same boundary over a few pixels.

**So the bands are blurred and the lines are not.** Blurring the whole picture would soften the line too, and the line is
the one thing that should stay sharp -- it is what the drawing is. Separating the fills from the strokes, softening only
the first, and multiplying the second back over it gives both: a gradient between the bands and a crisp contour.

    python tools/compose_soft.py --src colour.json --reference "...jpg" --out soft.png --sigma 6
"""
import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter


def split(doc, keep):
    out = dict(doc)
    out['marks'] = [m for m in doc.get('marks', []) if m.get('kind') == keep]
    return out


def render(doc, path, sweep=False):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    project = path.with_suffix('.json')
    project.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    png = path.with_suffix('.png')
    argv = [sys.executable, '-m', 'lineweight', '--render', str(project), '--out', str(png)]
    # **The analytic brush is a rendering choice, so it is forwarded rather than decided here.** It changes how a width
    # becomes pixels, not what the two layers are; the blur below is a decision about the layers and is untouched by it.
    if sweep:
        argv.append('--sweep')
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=r'E:\lineweight')
    if proc.returncode != 0:
        print(proc.stderr[-400:])
        raise SystemExit('render failed for %s' % project)
    return png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--work-dir', default='')
    ap.add_argument('--sigma', type=float, default=6.0, help='blur applied to the shading only')
    ap.add_argument('--keep', type=float, default=0.55, help='how much of the softened shading to mix back; 1 is full')
    ap.add_argument('--strokes', default='',
                    help='a greyscale line image to multiply over the shading instead of rendering the project strokes; '
                         'this is how a line layer from another source is tried without rebuilding it as marks')
    ap.add_argument('--sweep', action='store_true',
                    help='render the marks with the analytic brush: the edge loses the stamp-pitch scallop and the '
                         'composer pays two to eight times the render time for it')
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.src).read_text(encoding='utf-8'))
    work = pathlib.Path(args.work_dir or pathlib.Path(args.out).with_suffix(''))
    work.mkdir(parents=True, exist_ok=True)

    fills = render(split(doc, 'fill'), work / 'fills', sweep=args.sweep)
    if args.strokes:
        strokes = pathlib.Path(args.strokes)
        print('  using %s as the line layer' % strokes)
    else:
        strokes = render(split(doc, 'stroke'), work / 'strokes', sweep=args.sweep)
    print('  rendered %s' % fills.name)

    shade = Image.open(fills).convert('RGB')
    soft = shade.filter(ImageFilter.GaussianBlur(args.sigma))
    # **Part of the way, not all of it.** A full blur loses the band's own shape; mixing the softened version back over
    # the flat one keeps the band and removes the step.
    soft = Image.blend(shade, soft, args.keep)

    sharp = Image.open(strokes).convert('L')
    # **A line layer from elsewhere is at its own resolution.** The cut that produced it is smaller than the canvas, so it
    # is scaled here rather than requiring the caller to match the two by hand.
    if sharp.size != shade.size:
        sharp = sharp.resize(shade.size, Image.LANCZOS)
    ink = np.asarray(sharp, dtype=np.float32) / 255.0
    # **The renderer's paper is not white.** Measured at 0.945, so multiplying it in darkened the whole picture by six per
    # cent -- larger than every difference the line layer was being judged on, and it hid the improvement of a better line
    # layer entirely. Normalising to the paper's own value puts the paper at one and leaves the lines where they are.
    paper = float(np.percentile(ink, 92))
    if paper > 0.2:
        ink = np.clip(ink / paper, 0.0, 1.0)
    base = np.asarray(soft, dtype=np.float32)
    # **Multiply, because a line is a darkening of whatever is under it.** On paper that multiplies toward the paper's
    # own tone, and over shading it multiplies toward the shading -- which is what ink on paint does.
    out = np.clip(base * ink[:, :, None], 0.0, 255.0).astype(np.uint8)
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out).save(args.out)
    print('  wrote %s (sigma %.1f, mixed %.2f)' % (args.out, args.sigma, args.keep))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
