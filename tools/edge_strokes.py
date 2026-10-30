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
import time

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from lineweight import core, project

import edge_line
import line_from_shapes
import shape_pass
import value_pass

#: The two widths a line can draw at, on the cut grid. **The fine one is for a change of light and the heavy one for a
#: change of material.** Below 0.8 a line disappears when the canvas is scaled up; above 2.2 it reads as an ink blot.
#: The earlier version took one width from the total colour difference, so a shadow line on a cheek was drawn as heavily
#: as the join between hair and skin, and the whole picture came out over-inked.
W_FINE = 0.5
W_MATERIAL = 1.0

#: The colour gap at which a join counts as a change of material rather than a change of light. Quoted on the normalised
#: 0..1 channels the tables hold, where a hue or saturation change of this much is visible at a glance.
MATERIAL_GAP = 0.08

#: **Ink, by the same split, written as colour and not as alpha.** Three bands rather than a continuous ramp: a change of
#: material draws in full black, a change of light draws in a middle grey. `alpha_profile` was tried first and measured to
#: make the picture darker rather than lighter -- whatever that field drives, it is not the concentration of the mark, and
#: a colour is unambiguous: it lands in the render because the render has nothing else to use.
COLOUR_MATERIAL = '#000000'
COLOUR_MIDDLE = '#4a4a4a'
COLOUR_FINE = '#b8b8b8'


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


def width_and_ink(points, gap_colour, gap_light, scale):
    """How heavy a line should be and how dark, **from one pass over its own samples**.

    **Two questions, one measurement.** A line's weight and its ink are both decided by the same number -- the median
    colour gap along its own length -- because that number says whether the join is between two materials or between two
    lightnesses of one surface. They were two functions for a while, each walking the same points and taking the same
    median, which is the same measurement paid for twice.

    **Why the gap and not one pixel**: a boundary crosses both kinds of join in its run, and the median is what the line
    *mostly* is. **Why two outputs**: one width for every join over-inked the picture -- a lock of hair and the shadow under
    a jaw both separate two colours, so a single measure cannot tell them apart, and on the measured reference that put a
    black line down every fold. A change of material draws full and dark; a change of light draws fine and light.
    """
    ys = np.array([int(round(y)) for _x, y in points])
    xs = np.array([int(round(x)) for x, _y in points])
    h, w = gap_colour.shape
    ok = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
    if not ok.any():
        return W_FINE * scale, COLOUR_FINE, 0.0
    # **One fancy index instead of a loop of scalars.** `gap_colour[iy, ix]` in Python costs a few microseconds a sample
    # and there are tens of thousands of samples; indexing with two arrays is one call.
    colour = float(np.median(gap_colour[ys[ok], xs[ok]]))
    material = min(1.0, max(0.0, colour / MATERIAL_GAP))
    width = (W_FINE + (W_MATERIAL - W_FINE) * material) * scale
    if material >= 0.60:
        ink = COLOUR_MATERIAL
    elif material >= 0.30:
        ink = COLOUR_MIDDLE
    else:
        ink = COLOUR_FINE
    # **The lightness gap is returned rather than dropped.** It sits in `gap_light` from the call, was collected in the
    # first version of this function and thrown away, and it turns out to be the best single predictor of whether a
    # boundary is a line at all: measured against the artist's own lines it lifts precision from 39.8 to 50.7 per cent at
    # a cost of 11.5 points of recall, and it beats the colour gap at every operating point.
    light_gap = float(np.median(gap_light[ys[ok], xs[ok]]))
    return width, ink, light_gap


def part_by_height(y, box, head=0.16, torso=0.55):
    """A first division of the figure by height: `head`, `torso`, `legs`.

    **Crude, and the crudeness is the point of starting here.** A hand at hip height lands in `torso`; an arm raised above
    the head lands in `head`; a knee-length skirt straddles the boundary. But the rule costs nothing, needs no
    segmentation, and it already separates "lines in the face" from "lines in the clothes" -- which is the split the role
    table is built on and the reason a line carrying `part` is worth more than a line carrying nothing.

    The fractions are where a standing figure's landmarks sit: the head is about a sixth of the height at six heads, and
    the legs begin a little below the halfway mark because the crotch does not sit at the middle of the silhouette.
    """
    y0, y1 = float(box[0]), float(box[1])
    span = max(1.0, y1 - y0)
    where = (float(y) - y0) / span
    if where < head:
        return 'head'
    if where < torso:
        return 'torso'
    return 'legs'


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
    ap.add_argument('--min-light-gap', type=float, default=0.04,
                    help='drop boundaries whose lightness difference across them is below this. **0.04 is the measured '
                         'default, not a round number**: against a reference drawing\'s own lines it lifts the share of '
                         'drawn lines that land on a real one from 39.8%% to 50.7%% and costs 11.5 points of coverage, '
                         'and it beats the colour gap at every operating point. Zero restores every candidate. Length and '
                         'area ratio were tried as second filters and both point the same way -- smaller is more likely '
                         'to be a real line -- but each costs a third of the recall, so neither is applied')
    ap.add_argument('--merge-angle', type=float, default=35.0)
    ap.add_argument('--all-joins', action='store_true',
                    help='draw every boundary; by default only those the coarser cut also sees, measured to keep 46 per '
                         'cent of them and to be the difference between a drawing and a mass of hatching')
    args = ap.parse_args()

    # **A stage that prints nothing for four minutes is not diagnosable.** This tool is half of the pipeline's wall time on a
    # large reference and the cost is not spread evenly: the skeleton walk alone can be most of it.
    mark = time.perf_counter()

    def tick(label):
        nonlocal mark
        now = time.perf_counter()
        print('    %6.1fs  %s' % (now - mark, label))
        mark = now

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

    # **The canvas comes from the cut that made the areas**, so lines and fills land on one page by construction rather
    # than by the caller remembering to pass the same two numbers twice.
    declared = meta.get('canvas') or [0, 0]
    canvas_w = int(args.canvas_width or declared[0] or round(max(2880.0, float(max(w, h)))))
    canvas_h = int(args.canvas_height or declared[1] or round(canvas_w * h / float(w)))
    s = canvas_w / float(w)

    # **Every pixel quantity is quoted at the 2880 reference**, the same convention the gradient route uses: a length floor
    # means something different on a thousand pixel cut and on a two thousand four hundred one.
    k = float(max(w, h)) / 2880.0

    table, _counts = shape_pass.colour_table(labels, rgb)
    light, sat, hue = line_from_shapes.rgb_stats(table)
    tick('area colours')

    mask, ya, xa, low, high = boundary(labels)
    tick('boundary pixels')
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
        tick('coarse filter')

    # **The same colour gap the boundary analysis uses**, so a line is as heavy as the analysis says the join is. A hue
    # difference is weighted by the smaller of the two saturations, because two nearly grey areas have a hue that is noise.
    dh = np.abs(hue[low] - hue[high])
    dh = np.minimum(dh, 1.0 - dh) * 2.0
    dc = (dh * np.minimum(sat[low], sat[high]) + 0.5 * np.abs(sat[low] - sat[high])).astype(np.float32)
    dl = np.abs(light[low] - light[high]).astype(np.float32)
    flat = ya * w + xa
    size = w * h
    gap_colour = line_from_shapes.scatter_max(flat, dc, size).reshape(labels.shape)
    gap_light = line_from_shapes.scatter_max(flat, dl, size).reshape(labels.shape)
    tick('colour and lightness gaps')

    parts = {}
    lines = edge_line.walks(mask, max(1, int(round(args.min_segment * k))), timing=parts)
    tick('skeleton and walk')
    print('  within it: thin %.1fs, trace %.1fs, simplify %.1fs'
          % (parts.get('thin', 0), parts.get('trace', 0), parts.get('simplify', 0)))
    print('  %d walks, %d points' % (len(lines), sum(len(line) for line in lines)))
    if args.prune_length:
        before = len(lines)
        lines = edge_line.prune_fragments(lines, args.prune_length * k, args.prune_reach * k, args.prune_angle,
                                          8.0 * k, 20.0 * k, 600.0 * k, None, 30.0 * k, 0.0)
        tick('pruned')
        print('  fragments: %d kept of %d' % (len(lines), before))
    if args.merge_reach:
        before = len(lines)
        lines = edge_line.merge_fragments(lines, args.merge_reach * k, args.merge_angle, 90.0 * k)
        tick('joined')
        print('  joined: %d walks -> %d lines' % (before, len(lines)))

    proj = project.Project(width=canvas_w, height=canvas_h,
                           title='colour boundaries of %s' % pathlib.Path(args.reference).stem)
    # **The figure's box, so a line can be filed by where it sits.** Without a part a line is a shape; with one it can be
    # given a role by the table (`roles.role_for_part`) and asked questions like "how many lines are in the face".
    # **The boundary mask's own rows, not a person mask**: a person mask costs another pass over the picture and these
    # lines lie on the figure by construction, so the outermost boundary row is the figure's top and bottom.
    rows = np.flatnonzero(mask.any(axis=1))
    figure_box = (int(rows[0]), int(rows[-1])) if rows.size else None
    # **And the person, because a boundary lies wherever two colours meet and this picture has a sea in it.** The first
    # version filed every line by height alone, and the head band came out holding 550 lines whose x range was 3399 of a
    # 3464 pixel canvas -- waves, sky and a halo, not a face. A part is only meaningful for a line that is on the figure.
    gray_cut = (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)
    person = value_pass.person_mask(gray_cut)
    # **And the person's own bounds in x as well as y**, because a person mask is generous on a picture with a sea in it:
    # the first pass kept 5007 of 5028 lines as "on the figure", and the head band still held lines 3399 pixels wide. A
    # boundary that spans the canvas is the water's edge, and the midpoint of a line is not where a long line lives.
    labelled, count_person = ndimage.label(person)
    person_box = None
    if count_person:
        sizes = np.bincount(labelled.ravel())
        sizes[0] = 0
        biggest = labelled == int(sizes.argmax())
        cols = np.flatnonzero(biggest.any(axis=0))
        bands = np.flatnonzero(biggest.any(axis=1))
        if cols.size and bands.size:
            person_box = (int(bands[0]), int(bands[-1]), int(cols[0]), int(cols[-1]))
    written = 0
    added_by_part = 0
    for i, pts in enumerate(lines):
        if len(pts) < 2:
            continue
        width, ink, light_gap = width_and_ink(pts, gap_colour, gap_light, s)
        if light_gap < args.min_light_gap:
            continue
        scaled = [(x * s, y * s) for x, y in pts]
        record = core.stroke_record(scaled, 'fine', seed=i, resolution=1, colour=ink,
                                    width_profile=[width] * len(scaled))
        added = proj.add_stroke(record, stage='line', layer='ink', note='boundary %d' % i)
        if person_box is not None:
            mid = pts[len(pts) // 2]
            mid_y = mid[1] * s
            mid_x = mid[0] * s
            # **The person's box is in cut coordinates and the mark in canvas ones**, so the comparison divides by the
            # same scale the mark was multiplied by.
            iy = int(mid_y / s) if s else 0
            ix = int(mid_x / s) if s else 0
            top, bottom, left, right = person_box
            if top <= iy <= bottom and left <= ix <= right:
                added.part = part_by_height(mid_y, (top * s, bottom * s))
                added_by_part += 1
        written += 1
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out))
    print('  %d lines on a %dx%d canvas, written to %s' % (written, canvas_w, canvas_h, out))
    print('  %d of them fall on the figure and carry a part; the rest are background boundaries' % added_by_part)
    tick('records written')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
