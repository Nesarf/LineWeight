"""A project built from a reference picture's own lines, so the break counter can be pointed at a drawing that is known good.

The counter has only ever run on output, where "279 breaks" has nothing to mean anything against. A picture an artist made
is the obvious baseline, and its lines can be taken with `line_mask` -- thin, and darker than its own surroundings -- which
4.12 validated across four styles: on a line drawing it finds the ink, and on a painted one it finds the linework the paint
did not cover.

**What this is not.** These are the artist's own lines, so nothing here was reconstructed and there is no join step behind
them. The number says what the same counter reads on a drawing where the lines were drawn rather than recovered, and that
is exactly the comparison the row was missing.

    python tools/reference_lines.py --picture ref.jpg --out ref-lines.json
"""

import argparse
import math
import os
import sys

import numpy as np
from scipy import ndimage

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)

import line_agreement as la
from copy_linework import prune, thin, trace
from lineweight import core, project, psd


def _bilinear(field, xs, ys):
    """The mask sampled between pixels, so a cross-section is a length instead of a count."""
    height, width = field.shape
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    fx = xs - x0
    fy = ys - y0
    x0 = np.clip(x0, 0, width - 1)
    y0 = np.clip(y0, 0, height - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    return (field[y0, x0] * (1 - fx) * (1 - fy) + field[y0, x1] * fx * (1 - fy)
            + field[y1, x0] * (1 - fx) * fy + field[y1, x1] * fx * fy)


def crossing_width(profile, step=0.25):
    """How far along a grey section the ink takes to go from ten to ninety per cent, both sides averaged.

    **The same measure `tools/edge_profile.py` reports for a whole picture**, applied to one line's own section. It is
    here rather than imported because the two read sections at different scales, and a shared helper with a scale
    argument would be a third thing to keep in step.
    """
    low, high = float(profile.min()), float(profile.max())
    if high - low < 40.0:
        return None
    normalised = (high - profile) / (high - low)
    # **The centre is the darkest sample, not the middle of the window** -- see the same note in `edge_profile`.
    centre = int(np.argmin(profile))
    found = []
    # **The left half is reversed so index nought is the centre on both sides**, which makes "further into the field" a
    # larger index in both. Comparing the other way returns nothing at all -- see the same note in `edge_profile`.
    for side in (normalised[:centre + 1][::-1], normalised[centre:]):
        deep = np.flatnonzero(side >= 0.9)
        shallow = np.flatnonzero(side <= 0.1)
        if not deep.size or not shallow.size:
            continue
        beyond = shallow[shallow > deep[-1]]
        if not beyond.size:
            continue
        found.append((beyond[0] - deep[-1]) * step)
    return float(np.mean(found)) if found else None


def subpixel_axis(mask, run, gray=None, edt=None, step=0.25, extra=2.0, source='section'):
    """The ink's own centre and thickness across a skeleton run, at sub-pixel positions.

    **The skeleton is a pixel path; the ink is not.** A skeleton pixel names a corner of the grid, so its own distance to
    the boundary is quantised to half a pixel, and where strokes meet or bend the thinning algorithm drifts off the centre
    line altogether. Measured on a reference's own lines, a project rebuilt from the skeleton left **40 per cent of the
    ink uncovered at the pixel level** while reaching all of it within six pixels -- so the lines were in the right place
    and were not the same pixels.

    Each run point therefore gets a cross-section: the ink sampled along the normal at a quarter-pixel step, its centroid
    as the offset to apply, and its extent as the width. **That is what turns a centre line into something the ink agrees
    with**, and it costs one bilinear sample per offset rather than a new skeletoniser.

    **`gray` is read on the same section when it is given**, and what it measures is how wide that line's own edge is --
    a property of the pen and the paper rather than of the picture, which is why one number for the whole drawing is the
    wrong shape and was measured to be so.

    Returns `(points, widths, edges)` in image pixels, one entry per run point; `edges` is empty when no grey was given.
    """
    field = mask.astype(np.float64)
    if edt is None:
        edt = ndimage.distance_transform_edt(mask)
    count = len(run)
    points, widths, edges, depths = [], [], [], []
    for i in range(count):
        y, x = float(run[i][0]), float(run[i][1])
        yi, xi = int(round(y)), int(round(x))
        prev = run[max(0, i - 1)]
        nxt = run[min(count - 1, i + 1)]
        ty, tx = float(nxt[0] - prev[0]), float(nxt[1] - prev[1])
        length = math.hypot(tx, ty)
        if length < 1e-9:
            tx, ty = 1.0, 0.0
        else:
            tx, ty = tx / length, ty / length
        nx, ny = -ty, tx
        # **The reach follows the local half width.** A fixed window clips a heavy line and swallows its neighbour on a
        # fine one; two pixels beyond the measured half width is enough to see both edges of anything narrower than that.
        reach = max(4.0, 2.0 * float(edt[yi, xi]) + extra)
        offsets = np.arange(-reach, reach + step, step)
        vals = _bilinear(field, x + nx * offsets, y + ny * offsets)
        total = float(vals.sum())
        if total <= 1e-6:
            points.append((float(x), float(y)))
            widths.append(1.0)
            depths.append(1.0)
            continue
        shift = float((offsets * vals).sum() / total)
        points.append((x + nx * shift, y + ny * shift))
        # **The same section, read on the grey instead of on the ink, is how wide this line's edge is.** It costs one
        # more bilinear sample per offset and it is the only place the paper's own softness is visible -- a mask is
        # binary by construction and cannot carry it.
        if gray is not None:
            section = _bilinear(gray, x + nx * offsets, y + ny * offsets)
            width = crossing_width(section, step)
            if width is not None:
                edges.append(width)
            # **The ink's depth on the same section: how dark this line is here, as a share of black.** An artist's
            # line is not one value along its length -- the water in a wash pools and thins, a nib lays down more where
            # it lingers -- and a renderer that gives every point the same alpha cannot say so. This is the field that
            # can: `alpha_profile` multiplies the brush's opacity along the stroke.
            depths.append(min(1.0, max(0.0, (255.0 - float(section.min())) / 255.0)))
        else:
            depths.append(1.0)
        # **And the section is capped by the distance transform, because a cross-section does not know where its line
        # ends.** On a dense drawing nearly half the marks came back with a median width of more than twice the
        # reference's, and the lines were not wrong: the window reached across to the ink of the neighbouring stroke and
        # measured the gap between two lines as if it were the thickness of one. The distance transform cannot be fooled
        # that way -- it is the distance to the nearest empty pixel, which is the thickness along the narrowest direction
        # -- so it is the ceiling and the section is the refinement.
        #
        # **`source` exists so the three ways of getting a width can be compared on one skeleton, which is the same
        # experiment as holding a brush fixed and changing only how it is loaded.** `edt` is the plain thickness,
        # `fixed` is what this tool did before any of it (a constant), and `section` is the pair above.
        ceiling = 2.0 * float(edt[yi, xi])
        if source == 'edt':
            widths.append(ceiling)
        elif source == 'fixed':
            widths.append(1.0)
        else:
            widths.append(min(total * step, ceiling))
    return points, widths, edges, depths


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--picture', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--prune', type=int, default=4, help='skeleton spurs shorter than this are cut')
    parser.add_argument('--min-segment', type=int, default=6, help='runs shorter than this are dropped')
    #: **The reference's line, defined once and shared with every tool that measures against it.** `line_agreement`
    #: reads the same function at the same floor, so a project built here is measured against the very set it was built
    #: from -- without that, part of any difference is the difference between two definitions of "the line", and there
    #: is no way to tell an error of drawing from an error of definition. The floor's own reasoning is in
    #: `line_agreement`: 12 takes in soft value boundaries (17.88 per cent of a page), 40 does not (7.50).
    parser.add_argument('--floor', type=float, default=la.FLOOR)
    parser.add_argument('--element', type=int, default=la.ELEMENT)
    #: **The one knob where "matches the artist" and "matches the pixels" point at different values.** 1.0 uses the
    #: width measured across the line, which puts the median at 0.2085 per cent of the long side against an artist's
    #: 0.2219 -- inside their range. About 0.7 makes the drawn area equal to the reference's, and the symmetric
    #: difference falls from 291 677 to 213 233, at a median of 0.146 per cent which is in the bottom quarter of the
    #: artists' range. **Neither is wrong**: one asks whether the line looks like a drawn line, the other asks whether
    #: the ink is in the same pixels, and on this knob the two answers are 80 000 pixels apart.
    parser.add_argument('--width-scale', type=float, default=1.0,
                        help='multiply the measured width; 1.0 reads the ink, ~0.7 matches its area')
    #: Which reading of the ink becomes the width. **`section` is the default and the pair that works**: the plain
    #: thickness from the distance transform ignores the way a line thins at a corner, and a fixed one ignores the
    #: drawing entirely -- but both are here because a measurement nobody can compare against an alternative is a
    #: measurement with no scale.
    parser.add_argument('--width-source', choices=('section', 'edt', 'fixed'), default='section')
    #: **How many pixels a line's boundary takes from ink to paper, measured from the line itself.** One value for the
    #: whole drawing was the first version and it does not fit: across three drawings the right number ran from 2.0 to
    #: beyond 3.5, and one line was softer than any value could reach. So the default reads each line's own section, and
    #: this flag exists to pin it when the question is "what does one constant do" rather than "what does this line need".
    parser.add_argument('--edge', type=float, default=0.0,
                        help='pin the edge in pixels; 0 measures it from each line\'s own section')
    #: **The destination the focus actually names.** A project is the editable form, and a painting application cannot
    #: open one; `psd.layers_from_project` renders each `Mark.layer` through the same renderer the picture comes from, so
    #: the file carries the soft edge instead of a staircase. One flag turns a reference picture into layers SAI opens.
    parser.add_argument('--psd', default='', help='also write this path as a layered PSD')
    args = parser.parse_args()

    # **Everything is read at the page's own scale, which is what every threshold here is quoted against.** This used to
    # take the ink at the source picture's resolution and then scale the coordinates, and the difference is not
    # cosmetic: `line_mask` keeps only what is thinner than 2.5 *source* pixels, so on a small reference a line that is
    # six pixels on the 2880 page is 2.3 at the source and barely survives -- the mask loses the heavy lines and the
    # trace inherits a picture that is thinner than the one it copies.
    gray = la.load_gray(args.picture, la.LONG_SIDE)
    mask = la.artist_line(gray, element=args.element, floor=args.floor)
    height, width = mask.shape
    scale = 1.0
    canvas = project.Project(width=width, height=height,
                             title='lines of %s' % os.path.basename(args.picture))

    skeleton = prune(thin(mask.astype(np.uint8)), args.prune)
    runs = trace(skeleton)
    # **`render_to_project.stitch` was tried here and made it worse** -- 6138 marks against 5310, because it joins runs by
    # binning their ends into a grid, which is right for a closed contour walked from both ways and wrong for an open
    # line whose ends are genuine. So the runs stay as the skeleton broke them, and the ink comes out at 1.04 to 1.11
    # times the reference's rather than twice it once the comparison uses the same definition.
    kept = [run for run in runs if len(run) >= args.min_segment]
    # **The ink's own width and centre, from a cross-section at each skeleton point.** This wrote a constant `2 * scale`
    # for every mark, which is the same fault `render_to_project` had: a traced picture came out at one thickness whatever
    # the reference said. Then it read the distance transform, which gets the width right and still leaves the centre on
    # the integer grid -- measured, 40 per cent of the ink was uncovered at the pixel level while all of it was reached
    # within six. `subpixel_axis` samples across the line instead: the centroid moves the point off the grid and the
    # extent is the width.
    edt = ndimage.distance_transform_edt(mask)
    written = 0
    for i, run in enumerate(kept):
        px_points, px_widths, px_edges, px_depths = subpixel_axis(mask, run, gray=gray, edt=edt,
                                                                  source=args.width_source)
        if len(px_points) < 2:
            continue
        # **`resolution=1` keeps every cross-section**, because `catmull` at one sample per segment returns the points it
        # was given. Simplifying first would put the width profile at control-point resolution and describe a different
        # polyline than the one drawn -- which is what the previous version had to work around by expanding twice.
        points = [(x * scale, y * scale) for x, y in px_points]
        widths = [max(1.0, w * scale * args.width_scale) for w in px_widths]
        # **The edge is this line's own, unless the caller pins it.** One constant was measured not to fit the set: on
        # three drawings the value that matched ran from 2.0 to beyond 3.5, and one could not be reached at all because
        # its line is softer than this renderer can express. The section already carries the number, so it is read
        # there -- a line drawn with a dry pen and a line drawn with a wet one stop being the same mark.
        if args.edge > 0:
            edge = args.edge
        elif px_edges:
            edge = min(8.0, max(1.0, float(np.median(px_edges)) * scale))
        else:
            edge = 0.0
        record = core.stroke_record(points, 'fine', seed=i, resolution=1,
                                    width_profile=widths, absolute_width=True, edge=edge,
                                    alpha_profile=px_depths)
        canvas.add_stroke(record, stage='line', layer='ink', note='reference %d' % i)
        written += 1

    project.save_project(canvas, args.out)
    print('  %s %dx%d, %d line px, %d runs, %d marks -> %s'
          % (os.path.basename(args.picture), width, height,
             int(mask.sum()), len(runs), written, args.out))
    if args.psd:
        layers = psd.layers_from_project(canvas)
        path = psd.save_psd(layers, args.psd)
        print('  %d layer%s -> %s'
              % (len(layers), '' if len(layers) == 1 else 's', path))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
