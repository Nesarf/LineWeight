"""The colour-area boundaries as vector strokes, so they can be joined and so their width can be right.

**Why a bitmap was not the end.** The boundary image made the third reference recognisable, and its one visible fault was
on the face: the join between hair and skin came out as a hundred short dashes instead of one line. A dash pattern in a
bitmap cannot be repaired without tracing it -- joining needs endpoints and directions, and a raster has neither. So the
boundaries are walked into polylines, the same walk and the same joining the gradient route uses, and what comes out is a
line drawing again rather than a picture of one.

**The width comes from the colour difference the join separates.** A join between silver hair and white cloth is a
material change and draws at full weight; the join inside one lock of hair draws fine, because that is what it is.

Reads the areas the fills pass already cut -- `shape_pass` writes them beside its project -- so the line and the colour
land on exactly the same boundaries instead of being cut twice and missing each other by a pixel.

    python tools/edge_strokes.py --labels areas-labels.npy --meta areas-meta.json --reference "...jpg" --out lines.json
"""
import argparse
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from lineweight import core, project

import edge_line
import line_from_shapes
import shape_pass
import value_pass

#: The two widths a line can draw at, on the cut grid. Below the first a line disappears when the canvas is scaled up;
#: above the second it reads as an ink blot rather than a contour.
THIN = 1.4
THICK = 3.6


def boundary(labels):
    """Every pixel that has a differently labelled neighbour, and the pair of areas it sits between."""
    ys = []
    xs = []
    low = []
    high = []
    for dy, dx in line_from_shapes.NEIGHBOURS:
        a = labels[max(0, dy):labels.shape[0] + min(0, dy), max(0, dx):labels.shape[1] + min(0, dx)]
        b = labels[max(0, -dy):labels.shape[0] + min(0, -dy), max(0, -dx):labels.shape[1] + min(0, -dx)]
        same = a == b
        if not (~same).any():
            continue
        ya, xa = np.nonzero(~same)
        ys.append((ya + max(0, dy)).astype(np.int64))
        xs.append((xa + max(0, dx)).astype(np.int64))
        low.append(np.minimum(a[~same], b[~same]).astype(np.int32))
        high.append(np.maximum(a[~same], b[~same]).astype(np.int32))
    if not ys:
        empty = np.zeros(0, dtype=np.int64)
        return np.zeros(labels.shape, dtype=bool), empty, empty, np.zeros(0, np.int32), np.zeros(0, np.int32)
    ya = np.concatenate(ys)
    xa = np.concatenate(xs)
    mask = np.zeros(labels.shape, dtype=bool)
    mask[ya, xa] = True
    return mask, ya, xa, np.concatenate(low), np.concatenate(high)


def width_of(points, gap, scale):
    """How heavy a line should be: the colour difference of the joins it runs along, mapped between thin and thick."""
    seen = []
    for x, y in points:
        iy = int(round(y))
        ix = int(round(x))
        if 0 <= iy < gap.shape[0] and 0 <= ix < gap.shape[1]:
            value = float(gap[iy, ix])
            if value > 0.0:
                seen.append(value)
    if not seen:
        return THIN * scale
    value = float(np.median(seen))
    ratio = min(1.0, max(0.0, value / 0.20))
    return (THIN + (THICK - THIN) * ratio) * scale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--labels', required=True, help='the area labels written beside the fills project')
    ap.add_argument('--meta', required=True)
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--canvas-width', type=float, default=0)
    ap.add_argument('--canvas-height', type=float, default=0)
    ap.add_argument('--min-segment', type=float, default=6.0, help='shortest walk kept, at the 2880 reference')
    ap.add_argument('--prune-length', type=float, default=20.0,
                    help='strokes shorter than this must continue a longer one to be kept; 0 turns it off')
    ap.add_argument('--prune-reach', type=float, default=25.0)
    ap.add_argument('--prune-angle', type=float, default=20.0)
    ap.add_argument('--merge-reach', type=float, default=18.0)
    ap.add_argument('--merge-angle', type=float, default=35.0)
    ap.add_argument('--all-joins', action='store_true',
                    help='draw every boundary; by default only those the coarser cut also sees, measured to keep 46 per '
                         'cent of them and to be the difference between a drawing and a mass of hatching')
    args = ap.parse_args()

    labels = np.load(args.labels)
    meta = json.loads(pathlib.Path(args.meta).read_text(encoding='utf-8'))
    w, h = int(meta['cut'][0]), int(meta['cut'][1])
    if labels.shape != (h, w):
        print('  the labels are %s but the meta says %dx%d' % (labels.shape, w, h))
        return 1

    image = Image.open(args.reference).convert('RGB')
    scale = float(w) / float(image.size[0])
    work = image if abs(scale - 1.0) < 1e-6 else image.resize((w, h), Image.LANCZOS)
    rgb = np.asarray(work, dtype=np.float32) / 255.0

    canvas_w = int(args.canvas_width or round(max(2880.0, float(max(w, h)))))
    canvas_h = int(args.canvas_height or round(canvas_w * h / float(w)))
    s = canvas_w / float(w)

    # **Every pixel quantity is quoted at the 2880 reference**, the same convention the gradient route uses: a length floor
    # means something different on a thousand pixel cut and on a two thousand four hundred one.
    k = float(max(w, h)) / 2880.0

    table, _counts = shape_pass.colour_table(labels, rgb)
    light, sat, hue = line_from_shapes.rgb_stats(table)
    mask, ya, xa, low, high = boundary(labels)
    print('  %d areas, %d boundary pixels (%.2f%% of the cut)'
          % (int(labels.max()), int(mask.sum()), 100.0 * mask.mean()))

    # **Only the joins the coarser cut also sees.** Measured on this reference: drawing all of them produced a mass of
    # hatching over the whole picture, and the bitmap version looked right only because it had this filter in it. A join
    # inside one material is the same surface at two lightnesses; a join between two materials is what a line marks.
    if not args.all_joins:
        gray = (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)
        person = value_pass.person_mask(gray)
        coarse, coarse_areas = line_from_shapes.coarse_boundary(
            rgb, person, int(meta['levels']), float(meta['blur']), int(meta['min_area']))
        kept = mask & coarse
        print('  the coarser cut keeps %d areas; %d of %d boundary pixels survive it (%.1f%%)'
              % (coarse_areas, int(kept.sum()), int(mask.sum()),
                 100.0 * float(kept.sum()) / max(1, int(mask.sum()))))
        mask = kept

    # **The same colour gap the boundary analysis uses**, so a line is as heavy as the analysis says the join is. A hue
    # difference is weighted by the smaller of the two saturations, because two nearly grey areas have a hue that is noise.
    dh = np.abs(hue[low] - hue[high])
    dh = np.minimum(dh, 1.0 - dh) * 2.0
    dc = (dh * np.minimum(sat[low], sat[high]) + 0.5 * np.abs(sat[low] - sat[high])).astype(np.float32)
    flat = ya * w + xa
    gap = line_from_shapes.scatter_max(flat, dc, w * h).reshape(labels.shape)

    lines = edge_line.walks(mask, max(1, int(round(args.min_segment * k))))
    print('  %d walks, %d points' % (len(lines), sum(len(line) for line in lines)))
    if args.prune_length:
        before = len(lines)
        lines = edge_line.prune_fragments(lines, args.prune_length * k, args.prune_reach * k, args.prune_angle,
                                          8.0 * k, 20.0 * k, 600.0 * k, None, 30.0 * k, 0.0)
        print('  fragments: %d kept of %d' % (len(lines), before))
    if args.merge_reach:
        before = len(lines)
        lines = edge_line.merge_fragments(lines, args.merge_reach * k, args.merge_angle, 90.0 * k)
        print('  joined: %d walks -> %d lines' % (before, len(lines)))

    proj = project.Project(width=canvas_w, height=canvas_h,
                           title='colour boundaries of %s' % pathlib.Path(args.reference).stem)
    written = 0
    for i, pts in enumerate(lines):
        if len(pts) < 2:
            continue
        width = width_of(pts, gap, s)
        scaled = [(x * s, y * s) for x, y in pts]
        record = core.stroke_record(scaled, 'fine', seed=i, resolution=1, width_profile=[width] * len(scaled))
        proj.add_stroke(record, stage='line', layer='ink', note='boundary %d' % i)
        written += 1
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out))
    print('  %d lines on a %dx%d canvas, written to %s' % (written, canvas_w, canvas_h, out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
