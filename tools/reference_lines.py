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
from scipy.spatial import cKDTree

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)

import line_agreement as la
from copy_linework import prune, thin, trace
from edge_profile import CROSSING_SHARE, crossing_width
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


#: **How big a hollow has to be before the ink around it counts as a band rather than a line.** The width of a ring is the
#: two sides plus the hole between them, but only a hollow that is one: the union mask on `150673997` holds 5 037 holes
#: and 1 196 983 hole pixels, more than the ink itself, and almost all of them are pinholes from hatching and paper
#: noise. Widening a stroke by the radius of its nearest pinhole is how a line gets fat, so a hole below this radius is
#: treated as no hole at all. Two and a half pixels is one brush width -- smaller than that there is nothing to see across.
HOLE_RADIUS = 2.5
#: **And how big one may be before it stops being a hollow and becomes a region.** A contour drawn around an arm leaves a
#: hole with a radius of a hundred pixels or more; adding that to the ink around it does not measure a band, it measures
#: the picture. Measured without this cap, the width of the widest line came out at twenty-five per cent of the page.
#: Twelve pixels is the radius of a hollow twice the top hat's element, which is the widest band that filter can hollow.
HOLE_CEILING = 12.0
#: **What the ink itself reads as grey, because an alpha profile is a mix and the mix needs both ends.** The renderer
#: lays `field*(1-a) + ink*a` on the page, so the alpha that puts a line's core on a stated grey is
#: `(field - wanted) / (field - ink)`. Dividing by `field` alone is the same thing only when the ink is black, and this
#: one is `#1a1620` -- a dark violet, whose PIL luma is 24.3. Read off the render: the darkest pixel any drawing
#: reached was 25, never lower, which is what a floor of 24.3 looks like once the picture has been quantised.
INK_GREY = 0.299 * 26 + 0.587 * 22 + 0.114 * 32


def ring_room(mask, edt, hole_radius=HOLE_RADIUS):
    """How far the ink reaches from each pixel: twice the transform, or the whole band where the ink is a ring.

    **The distance transform answers "how far to the nearest pixel that is not ink", which is half a width on a solid
    stroke and half a *ring* on a hollow one.** The top hat hollows out any band wider than its element, so on such a band
    the transform reports the thickness of the rim: measured on 2 935 sections taken on a ring, `2 * edt` came out at 0.41
    of the artist's own half-depth width, and `4 * edt + 2 * hole radius` -- the two rims plus the hollow between them --
    at 0.81.

    **The ring correction is applied only where the hollow is closer than the outside**, which is what "on a ring" means
    geometrically, and only to holes above `hole_radius`. Both conditions are needed: without the first, a line beside a
    hole would be widened by it; without the second, a pinhole in hatching would do the same. Where neither holds the
    answer is the plain `2 * edt`, so a mask with no holes costs one comparison per pixel and nothing else.
    """
    plain = 2.0 * edt
    filled = ndimage.binary_fill_holes(mask)
    holes = filled & ~mask
    if not holes.any():
        return plain
    radius_map = ndimage.distance_transform_edt(holes)
    labels, count = ndimage.label(holes)
    per_hole = np.zeros(count + 1, dtype=np.float64)
    per_hole[1:] = np.asarray(ndimage.maximum(radius_map, labels, index=np.arange(1, count + 1)))
    # **A hole too small to be a hollow is not a hollow, and neither is one too big to be anything but a region.** Both
    # ends of the range are set to zero, so a pinhole can never widen a stroke and a contour's inside can never widen it
    # either; what survives is a hollow the ink could plausibly have been drawn around.
    per_hole[(per_hole < hole_radius) | (per_hole > HOLE_CEILING)] = 0.0
    if not (per_hole > 0).any():
        return plain
    # **`~holes`, not `holes`, and the difference is the whole of whether this works.** `distance_transform_edt` measures
    # the distance to the nearest *zero* pixel, so transforming `holes` reports the depth into a hole and nought everywhere
    # outside it -- which is where every ink pixel is. Transforming `~holes` reports, for each ink pixel, the distance to
    # the nearest hole, which is the quantity the formula needs. The first version had it the other way round, every test
    # came out zero, and the ring correction changed not one number while looking entirely in place.
    far, index = ndimage.distance_transform_edt(~holes, return_indices=True)
    here = per_hole[labels[index[0], index[1]]]
    # **The hollow has to be wider than the rim for the ink around it to be a band.** A pinhole beside a stroke sits at the
    # same distance from the skeleton as the stroke's own edge does, so "the hole is nearer than the outside" alone fires
    # on ordinary lines and doubles their width -- measured, that alone drove `width share` to 1.387 and `p90 / median`
    # to 4.08. A band's hollow is half its width while its rim is a fifth, so the ratio separates the two cases without a
    # second constant.
    on_ring = (far <= edt) & (here > 2.0 * edt) & (here > 0)
    return np.where(on_ring, 4.0 * edt + 2.0 * here, plain)


def subpixel_axis(mask, run, gray=None, edt=None, step=0.25, extra=2.0, source='section', room=None):
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

    Returns `(points, widths, edges, depths)` in image pixels, one entry per run point; `edges` is empty when no grey was
    given. **`room` is how far the ink reaches from each pixel** -- `ring_room`'s answer, which is twice the transform
    except on a band the top hat hollowed out. Passing it is optional so the function still works on a mask with no
    holes, and when it is left out the plain transform is the ceiling, which is what every earlier measurement used.
    """
    field = mask.astype(np.float64)
    if edt is None:
        edt = ndimage.distance_transform_edt(mask)
    if room is None:
        room = 2.0 * edt
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
        edge_now = None
        if gray is not None:
            section = _bilinear(gray, x + nx * offsets, y + ny * offsets)
            # **The section's own step, because the answer is a length.** This used to leave `crossing_width` on its
            # module's step of a tenth while sampling at a quarter, so every line's edge came back 2.5 times too small
            # and the copy was drawn with a hard edge on a soft drawing. See `crossing_width`.
            width = crossing_width(section, step)
            if width is not None:
                edges.append(width)
                edge_now = width
            # **The ink's depth on the same section: how dark this line is here, as a share of black.** An artist's
            # line is not one value along its length -- the water in a wash pools and thins, a nib lays down more where
            # it lingers -- and a renderer that gives every point the same alpha cannot say so. This is the field that
            # can: `alpha_profile` multiplies the brush's opacity along the stroke.
            #
            # **Read inside this line's own half width, because a section does not know where its line ends.** The width
            # was capped by the distance transform for exactly this reason; the depth was not, and a section taken where
            # two hatched strokes cross found the *other* stroke's core and reported this one as darker than it is. That
            # is what the beads were: the deep samples sat on the junctions and every crossing got a dark disc.
            own = np.abs(offsets) <= float(edt[yi, xi]) + 0.5
            darkest = float(section[own].min()) if own.any() else float(section.min())
            # **The denominator is the dye's own reach, not black.** The renderer composites `field*(1-a) + ink*a`,
            # so the alpha that lands the core on `darkest` is `(field - darkest) / (field - ink)`. Dividing by 255
            # assumes `ink == 0`; this renderer's ink is `#1a1620`, whose luma is 24.3, so every profile came out 0.905
            # times too small and every line was drawn about ten per cent pale -- measured over eleven drawings, the
            # acceptance's `ink depth` sat at a median of 0.851 and two drawings fell outside the band (§4.46). The
            # two agree exactly when the ink is black, which is what made the 255 look right for as long as nobody
            # checked it against a picture.
            depths.append(min(1.0, max(0.0, (255.0 - darkest) / (255.0 - INK_GREY))))
        else:
            depths.append(1.0)
        # **And the section is capped by the distance transform, because a cross-section does not know where its line
        # ends.** On a dense drawing nearly half the marks came back with a median width of more than twice the
        # reference's, and the lines were not wrong: the window reached across to the ink of the neighbouring stroke and
        # measured the gap between two lines as if it were the thickness of one. The distance transform cannot be fooled
        # that way -- it is the distance to the nearest empty pixel, which is the thickness along the narrowest direction
        # -- so it is the ceiling and the section is the refinement.
        #
        # **`source` exists so the ways of getting a width can be compared on one skeleton**, which is the same
        # experiment as holding a brush fixed and changing only how it is loaded. `edt` is the plain thickness, `fixed`
        # is what this tool did before any of it (a constant), `section` is the mask's extent along the section, and
        # `halfdepth` is where the grey reaches half the line's own depth -- see `_half_depth_width`.
        #
        # **Two ceilings, because the two sources are wrong in different places.** The plain transform is the right guard
        # for a mask extent -- it stops a section reaching the next stroke -- and it is the wrong answer on a hollow band,
        # where it measures the rim; `ring_room` is that correction and it belongs to the reading that needs it. Taking
        # the ring width onto the mask extent as well was tried and made the picture worse on every row: width share went
        # to 1.387 and `p90 / median` to 4.08, because a hollow's radius is not stable enough to be a width on its own.
        ceiling = 2.0 * float(edt[yi, xi])
        if source == 'edt':
            widths.append(ceiling)
        elif source == 'fixed':
            widths.append(1.0)
        elif source == 'halfdepth':
            measured = _half_depth_width(section, offsets) if gray is not None else None
            # **The ceiling is a guard against reaching the next line.** Letting the grey overrule the mask by a factor was
            # tried and is not kept: at 2.5 times, `p90 / median` on `150673997` went from 2.06 to 4.83, because a section
            # beside another stroke comes back several times too wide and the factor let it through. A reading off the
            # grey is used only where the mask has no opinion to overrule, which is not the same as having a better one.
            room_ceiling = float(room[yi, xi])
            widths.append(room_ceiling if measured is None else min(measured, room_ceiling))
        elif source == 'cover':
            # **The width a mark is drawn at has to be the ink's width *minus* the soft edge, because the renderer puts
            # the edge outside it.** Coverage in `sweep_layer` is `(half + edge/2 - d) / edge`, so a stroke carrying
            # `width` and `edge` reaches as far as `width + edge` before it fades out, while the artist's own ink already
            # contains its own soft edge. Writing the ink's own width straight into `width` therefore draws a line wider
            # than the one measured -- by one whole edge, which on a thin line is most of it: measured on `150721001`,
            # whose artist lines are 4.5 pixels, the copy came out at 1.789 times their width while the recorded widths
            # were already the same 4.47.
            #
            # A share of the line's own depth range, rather than a fixed grey, because the same stroke is not equally
            # dark everywhere and a pale line must not be called thin for being pale.
            cover = _coverage_width(section, offsets) if gray is not None else None
            if cover is None:
                widths.append(min(total * step, ceiling))
            else:
                # **A whole edge, measured rather than reasoned.** Six tenths was tried first on the arithmetic -- the
                # renderer's own fifth-coverage sits `0.6 * edge` outside the half-width -- and it is wrong in practice:
                # with six tenths `150721001`'s width share stays at 1.342, with a whole edge it lands on 1.001. What
                # the six-tenths reasoning leaves out is that the artist's own profile is not the renderer's, so the
                # correction is calibrated on the result rather than derived from the formula.
                #
                # **And the mask's own width is a ceiling on top of it, because a section cannot tell when it has left
                # its line.** Walking outward stops where the ink does, but two strokes that touch are one run of ink to
                # that walk: without a ceiling, 1.47 per cent of the points came back wider than forty pixels with a
                # maximum of 163.7, and in the picture they were black patches at the collar, the jaw and the hem -- the
                # one fault none of the six rows had shown, because a median and a ninetieth percentile cannot see one
                # and a half per cent. `room` is what the mask says the ink reaches there, so the smaller of the two is
                # what both measurements agree on.
                #
                # **The width also may not fall below the edge, or the stroke cannot reach full coverage at its own
                # centre.** `sweep_layer` puts the centre at `0.5 + half / edge`, so a one-pixel stroke with a four-pixel
                # edge tops out at 0.625 -- drawn, and still looking like a faint hairline. That is what the brick wall
                # showed: its horizontal joints were in the mask and in the skeleton (dark runs across a row, 45 per cent
                # of rows against the copy's 43), and the plate read as if they had never been drawn, because they were
                # thin enough for `cover - edge` to land on the floor.
                edge_here = edge_now or 0.0
                widths.append(min(float(room[yi, xi]), max(cover - edge_here, edge_here, 1.0)))
        else:
            # **The ceiling is `room`, not twice the transform, and that is the whole correction.** `2 * edt` is the
            # distance to the nearest non-ink, which is half a *rim* on a band the top hat hollowed; `room` is twice that
            # except on such a band, where it is the two rims plus the hollow. Taking the smaller of the section's extent
            # and `room` is therefore safe in both places and needs no test: on ordinary ink the mask extent is what it
            # always was, on a band the extent either crosses the whole band -- and then it and `room` agree -- or it
            # stops at the rim, and then `room` supplies the rest. Requiring the section to have stopped at the rim first
            # was tried and is wrong: on the widest bands the section does cross the band, so the condition excluded
            # exactly the ink it was written for.
            widths.append(min(total * step, float(room[yi, xi])))
    return points, widths, edges, depths


def _half_depth_width(section, offsets):
    """How wide the ink is where the grey is halfway between the field and the darkest sample.

    **The width the trace asks for is a grey question, and the mask cannot answer it.** A mask is a threshold: where a pale
    stroke crosses the floor it simply stops, so the width it reports follows how dark the ink is rather than how wide the
    stroke is. Measured against the artist's own half-depth width on 23 773 sections, the recorded width was 0.73 of the
    truth on a pale drawing and 1.14 on a denser one, and inside each drawing the ratio climbed with the ink's depth
    (0.67 at depth 0.10 to 1.13 at 0.70). Two drawings, one estimator, opposite directions -- which is what a threshold
    does and what a profile does not.

    **Half depth rather than a fixed grey**, because the same stroke is not equally dark everywhere and the artist's pale
    passages must not come out thin for being pale. The two sides are averaged from the darkest sample, so an asymmetric
    line is measured as a whole line.
    """
    low, high = float(section.min()), float(section.max())
    if high - low < 20.0:
        return None
    normalised = (high - section) / (high - low)      # 1 at the darkest sample
    centre = int(np.argmin(section))
    sides = []
    for side in (normalised[:centre + 1][::-1], normalised[centre:]):
        above = np.flatnonzero(side >= 0.5)
        sides.append(float(above[-1]) if above.size else 0.0)
    return (sides[0] + sides[1]) * float(offsets[1] - offsets[0])


def _coverage_width(section, offsets, share=0.2):
    """How wide the section is at a stated share of its own depth range, **walked outward from its darkest sample**.

    **The first version took the outermost two samples above the share, which is not a width when the section crosses
    something.** On `150673997`, where fine and heavy lines sit close together, that came back at a median of 13.50 pixels
    and a 90th percentile of 27.0 against lines whose ink is 7.2 wide -- it was measuring across the gap from one stroke
    to its neighbour. Walking outward from the centre and stopping at the first sample below the share is the same
    arithmetic `crossing_width` uses for the edge, and it cannot leave the line it started on.

    The centre is the darkest sample for the same reason it is there: a skeleton pixel is a grid point, not the middle of
    the ink, so the window's midpoint would split a section whose dark part sits to one side.
    """
    field = float(np.percentile(section, 90))
    dark = float(section.min())
    if field - dark < 20.0:
        return None
    coverage = np.clip((field - section) / (field - dark), 0.0, 1.0)
    centre = int(np.argmin(section))
    # **A stroke's section is one hump, so walking outward stops at the valley as well as at the edge.** Stopping only
    # where the ink falls below the share merges two strokes that touch: the walk crosses the shallow dip between them
    # and reports one line several times as wide. Measured, that put 1.47 per cent of the points above forty pixels with
    # a maximum of 163.7, and the picture carried them as black patches at the collar, the jaw and the hem -- none of
    # which a median or a ninetieth percentile could show.
    #
    # The rise that ends the walk is a quarter of the line's own depth, which is a change of direction rather than a
    # level: a section that has reached its neighbour is climbing towards a second maximum, and a section on a broad
    # stroke is still inside one.
    climb = 0.15
    sides = []
    for step_sign, stop in ((-1, -1), (1, len(coverage))):
        deepest = coverage[centre]
        index = centre
        while index != stop:
            value = coverage[index]
            if value < share or value > deepest + climb:
                break
            deepest = max(deepest, value)
            index += step_sign
        # **The walk can leave the window before it meets either stop**, and then the window's own end is the answer.
        index = min(max(index, 0), len(offsets) - 1)
        sides.append(abs(float(offsets[index])))
    return float(sum(sides))


def ink_mask(gray, mode='coverage', element=la.ELEMENT, floor=la.FLOOR, window=41, level=200.0, share=0.2):
    """Which pixels of the reference are ink, on one of four definitions.

    **The top hat is the one every measurement in this project was quoted against, and it has a blind spot.** It keeps a
    pixel when it is darker than a size-`element` grey closing of itself, which finds a *thin* structure; a solid band
    wider than `element` is closed over and the band's interior stops being ink at all. Read off `150673997`'s difference
    plate, that is the whole of the largest area the copy was missing: the skirt hem, the sleeve and the dark mass in the
    corner come back as **rings**, the tracer walks the ring, and the copy draws a hairline along a band twenty pixels wide
    while the band's interior lands in the extra-ink colour. No width or edge could have fixed that, because the width it
    was handed was the thickness of the ring.

    **Both relative definitions fail inside a solid mass for the same reason**: each asks whether a pixel is darker than
    its surroundings, and the middle of a filled region has no surroundings that are lighter. The field's answer to that
    is **the size of its window**, and the size is measured rather than chosen: on `150673997` the field finds 236 890
    line pixels at 15, 685 611 at 41 and 752 836 at 61, against the top hat's 618 557. At 41 the union is 880 711.

    **`coverage` is the union's answer to a question the union gets wrong: how big the mask should be.** Measured against
    a share of each picture's own field-to-darkest range, the union comes to 86.5 per cent of it on `150673997` and 127 per
    cent on `150721001` -- and that factor carries straight into the width, which is why one drawing ends up with 14 per
    cent too little ink and the other with 45 per cent too much. Normalising each picture by its own range before
    thresholding removes the factor: it is the same definition `accept.py` quotes as an amount of ink.

    The cost of `coverage` is stated: a pale wash is ink under it, where the top hat would leave it alone.
    """
    if mode == 'coverage':
        field = float(np.percentile(gray, 95))
        dark = float(np.percentile(gray, 0.5))
        if field - dark < 8.0:
            return np.zeros(gray.shape, dtype=bool)
        return np.clip((field - gray) / (field - dark), 0.0, 1.0) >= share
    if mode == 'level':
        return gray < level
    if mode == 'field':
        local = ndimage.median_filter(gray, size=window)
        return (local - gray) > floor
    if mode == 'both':
        local = ndimage.median_filter(gray, size=window)
        return la.artist_line(gray, element=element, floor=floor) | ((local - gray) > floor)
    return la.artist_line(gray, element=element, floor=floor)


def _smooth_depths(values, window=5):
    """The depth along one line, with single-point spikes removed.

    **A section's darkest sample is a value at a point; an artist's ink is a value along a line.** Where two strokes cross
    the section reaches the fused core and reports this line darker than it is, and those over-reads sit exactly where
    marks meet -- measured on `150673997`, ink under one mark has a median grey of 158 and under three 136, while the
    artist's own ink is flat across the same places (146 to 154, no trend). A median over five samples removes a spike
    one sample wide and keeps a line that is darker for fifty: the junction excess went from 18 grey levels to 10.

    **One value per run was tried and is worse.** It removes the rest of the junction excess but it also takes the
    picture below the ink it needs -- the page goes from 6.25 to 5.65 per cent of ink and the hatch strokes stop crossing
    `artist_line`'s floor at all, so a row of eight separate strokes reads as one pale mass. The banding that survives
    here is not what makes a copied stroke look like a chain of lozenges; the capsules' own geometry is, because a
    four-pixel stroke cut into six-pixel pieces is drawn as six-pixel capsules and the union of their round ends is
    scalloped. That is a join, not a value.
    """
    if len(values) < window:
        return list(values)
    half = window // 2
    out = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(float(np.median(values[lo:hi])))
    return out


def _edge_of(measured, pinned, scale):
    """The record's `edge` from a line's own crossings, or the caller's pin.

    **A measurement is a tenth-to-ninetieth span; the record's `edge` is the whole ramp the renderer draws.** Dividing
    by `CROSSING_SHARE` is the whole of the conversion, and leaving it out made every copied line a fifth harder than
    its source even after the sampling step was passed through. See `edge_profile`.
    """
    if pinned > 0:
        return pinned
    if not measured:
        return 0.0
    return min(8.0, max(1.0, float(np.median(measured)) * scale / CROSSING_SHARE))


def _join_runs(runs, gap=2.0, straight=0.6):
    """Runs that continue into one another, concatenated into one path.

    **Why a join and not a smaller threshold.** A four-pixel stroke cut into six-pixel pieces is drawn as six-pixel
    capsules, and the union of their round ends is scalloped -- the copy of `150673997` reads as a chain of pale lozenges
    where the artist has a stroke, and no value of alpha or edge removes it, because it is the *shape* of the union. The
    width, edge and depth of a joined path are then measured across the joins instead of at their ends, which is also
    where they were least reliable.

    **The join is stated as geometry, which is what the earlier attempt got wrong.** `render_to_project.stitch` binned run
    ends into a grid, so it joined a line's two genuine ends to each other by accident and nearly doubled the mark count
    (5310 to 6138). Two conditions are used here instead, and both are about the stroke rather than about a grid:

    * the ends must be within `gap` pixels, which is one line's own width;
    * each run's inward direction at its end must point **opposite** the other's -- `dot <= -straight` -- because two
      pieces of one stroke leave their shared end in opposite directions, while two strokes that merely pass close by do
      not.

    Each end is used at most once, so the result is a set of paths rather than a graph. A closed contour is one run
    already (the tracer walks it from both ways) and a cycle of runs is left as separate paths rather than guessed at.
    """
    count = len(runs)
    if count < 2:
        return [list(run) for run in runs]

    def inward(i, side):
        run = runs[i]
        if len(run) < 2:
            return np.zeros(2)
        if side == 0:
            v = np.array([run[1][0] - run[0][0], run[1][1] - run[0][1]], dtype=np.float64)
        else:
            v = np.array([run[-2][0] - run[-1][0], run[-2][1] - run[-1][1]], dtype=np.float64)
        length = float(np.hypot(v[0], v[1]))
        return v / length if length > 1e-9 else np.zeros(2)

    ends = [(i, side) for i in range(count) for side in (0, 1)]
    spot = np.array([[runs[i][0 if side == 0 else -1][0], runs[i][0 if side == 0 else -1][1]]
                     for i, side in ends], dtype=np.float64)
    tree = cKDTree(spot)
    candidates = []
    for a, b in tree.query_pairs(gap, output_type='ndarray'):
        ia, sa = ends[int(a)]
        ib, sb = ends[int(b)]
        if ia == ib:
            continue
        if float(np.dot(inward(ia, sa), inward(ib, sb))) > -straight:
            continue
        candidates.append((float(np.hypot(*(spot[a] - spot[b]))), (ia, sa), (ib, sb)))
    candidates.sort()

    link, taken = {}, set()
    for _, first, second in candidates:
        if first in taken or second in taken:
            continue
        link[first] = second
        link[second] = first
        taken.update((first, second))

    used = [False] * count
    joined = []
    for i in range(count):
        if used[i] or (i, 0) in taken and (i, 1) in taken:
            continue
        start = 0 if (i, 0) not in taken else 1
        chain, here = [], (i, start)
        while here is not None:
            ci, cs = here
            if used[ci]:
                break
            used[ci] = True
            chain.extend(runs[ci] if cs == 0 else runs[ci][::-1])
            step = link.get((ci, 1 - cs))
            here = step if step is not None and not used[step[0]] else None
        joined.append(chain)
    # **A ring of runs has no end to start from**, so whatever the walk above could not reach is kept as it was.
    for i in range(count):
        if not used[i]:
            joined.append(list(runs[i]))
    return joined


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
    #: **Which reading of the ink becomes the width, and the one that works asks the two questions that were being
    #: confused.** A mark's `width` is not the ink's width: `sweep_layer`'s coverage is `(half + edge/2 - d) / edge`, so
    #: the stroke reaches `width + edge` before it fades, while the artist's ink already contains its own soft boundary.
    #: `cover` reads the ink at a fifth of its own depth range -- the same share `accept.py` counts the page with -- and
    #: subtracts that edge, and both numbers land: `width share` 1.000 on `150673997` and 1.001 on `150721001`, with the
    #: page's ink at 1.006 and 1.025 of the artist's against 0.843 and 1.221 before it.
    #:
    #: **`section` was the default for four rounds and is kept beside it** because it is the plain mask extent and remains
    #: the thing to compare against; `halfdepth` made the recorded width equal to the half-depth width almost exactly and
    #: the picture worse (page ink 5.67 to 3.91 per cent, `ink reached` 0.989 to 0.641), which is what taught the
    #: difference between a number that agrees and a picture that does.
    #:
    #: What `cover` does not fix is `p90 / median` on `150673997` (1.419) -- the widths record at 2.36 of their own median,
    #: and the finished picture measures 3.34 because `cl.INK` fuses neighbouring strokes in a dense drawing and twice the
    #: transform then spans the pair. That is the judging side, not the drawing side, and it is written down rather than
    #: tuned away.
    parser.add_argument('--width-source', choices=('cover', 'section', 'halfdepth', 'edt', 'fixed'), default='cover')
    #: **How many pixels a line's boundary takes from ink to paper, measured from the line itself.** One value for the
    #: whole drawing was the first version and it does not fit: across three drawings the right number ran from 2.0 to
    #: beyond 3.5, and one line was softer than any value could reach. So the default reads each line's own section, and
    #: this flag exists to pin it when the question is "what does one constant do" rather than "what does this line need".
    parser.add_argument('--edge', type=float, default=0.0,
                        help='pin the edge in pixels; 0 measures it from each line\'s own section')
    #: **Off by default, because drawing the fragments was measured not to buy coverage and to cost depth.** With them
    #: on, 17,858 extra marks moved the ink on the page from 6.4677 to 6.4902 per cent -- a third of one per cent -- while
    #: the depth spread went from 1.016 to 1.152 and the picture showed dark beads where fragments piled on top of the
    #: line they borrowed from. Source-over composites, so re-laying ink that is already there deepens it: a fragment's
    #: ink is redundant in area and additive in alpha. **Re-tested once the runs were joined, since a joined fragment is
    #: no longer the same tape**: 7,937 borrowed marks then move the ink from 6.04 to 6.10 per cent, depth spread
    #: 1.071 -> 0.921, but width share 1.000 -> 1.109 and edge 1.093 -> 1.168. Still not worth it -- two rows away from
    #: one for six hundredths of a per cent of ink.
    parser.add_argument('--fragments', action='store_true',
                        help='also draw runs shorter than --min-segment, borrowing their appearance from the nearest')
    #: **The destination the focus actually names.** A project is the editable form, and a painting application cannot
    #: open one; `psd.layers_from_project` renders each `Mark.layer` through the same renderer the picture comes from, so
    #: the file carries the soft edge instead of a staircase. One flag turns a reference picture into layers SAI opens.
    parser.add_argument('--psd', default='', help='also write this path as a layered PSD')
    #: **Which pixels count as the reference's ink, and the answers differ by more than they look.** See `ink_mask`: the
    #: top hat, which every earlier measurement was quoted against, comes back as a *ring* around any band wider than its
    #: element, so the trace drew a hairline down the middle of a twenty-pixel hem. The default is the union with a field
    #: test, which keeps the top hat's thin strokes and adds the bands; measured, it moves the copy's ink on the page from
    #: 9.22 to 11.99 per cent of the same measure where the artist has 14.23.
    parser.add_argument('--ink', choices=('coverage', 'tophat', 'field', 'both', 'level'), default='coverage',
                        help='both (default: the top hat and a local-median field), tophat (the eleven-drawing '
                             'baseline), field (the field alone) or level (darker than --ink-level)')
    #: **How far a field sample reaches, and the size is measured rather than chosen.** At 15 the median window never sees
    #: paper inside close hatching; at 41 the union reaches 880 711 pixels on `150673997`, within a thousand of a fixed
    #: threshold at 200, so the window has grown enough to see around a band twenty pixels wide.
    parser.add_argument('--ink-window', type=int, default=41,
                        help='with --ink field or both: the median window, in pixels')
    #: **The one definition with no blind spot inside a filled region**, because it never asks about the surroundings. 200
    #: is `drawn_line`'s own threshold inverted. It is not the default and the second drawing is why: on a pale drawing it
    #: throws away 76 492 of the artist's own lines while the union adds 7 736.
    parser.add_argument('--ink-level', type=float, default=200.0,
                        help='with --ink level: a pixel is ink when its grey is below this')
    args = parser.parse_args()

    # **Everything is read at the page's own scale, which is what every threshold here is quoted against.** This used to
    # take the ink at the source picture's resolution and then scale the coordinates, and the difference is not
    # cosmetic: `line_mask` keeps only what is thinner than 2.5 *source* pixels, so on a small reference a line that is
    # six pixels on the 2880 page is 2.3 at the source and barely survives -- the mask loses the heavy lines and the
    # trace inherits a picture that is thinner than the one it copies.
    gray = la.load_gray(args.picture, la.LONG_SIDE)
    mask = ink_mask(gray, args.ink, args.element, args.floor, window=args.ink_window, level=args.ink_level)
    height, width = mask.shape
    scale = 1.0
    canvas = project.Project(width=width, height=height,
                             title='lines of %s' % os.path.basename(args.picture))
    # **这个文件自己说明它是哪一次运行做出来的。** 一个目录里可以同时躺着两代产物 —— 真的躺过，而差别只在一列测量上
    # 显形、另外三列看着正常，为此重测了两次。参数全写在这里，所以「这个数能不能和那个数比」不再靠记忆回答。
    canvas.settings = {
        'tool': 'reference_lines',
        'source': os.path.basename(args.picture),
        'floor': args.floor,
        'element': args.element,
        'ink': args.ink if args.ink != 'level' else 'level %g' % args.ink_level,
        'prune': args.prune,
        'min_segment': args.min_segment,
        'width_source': args.width_source,
        'width_scale': args.width_scale,
        'edge': args.edge if args.edge else 'per line',
        'fragments': bool(args.fragments),
        'page_long': la.LONG_SIDE,
    }

    skeleton = prune(thin(mask.astype(np.uint8)), args.prune)
    runs = trace(skeleton)
    # **`render_to_project.stitch` was tried here and made it worse** -- 6138 marks against 5310, because it joins runs by
    # binning their ends into a grid, which is right for a closed contour walked from both ways and wrong for an open
    # line whose ends are genuine. `_join_runs` joins by geometry instead: an end within one line's width whose inward
    # directions are opposed, one end used once. Without it each of the artist's strokes is drawn as a chain of round
    # ends, which is the scallop the magnified copy shows.
    runs = _join_runs(runs)
    kept = [run for run in runs if len(run) >= args.min_segment]
    # **A run too short to describe itself can borrow its neighbour's appearance instead of vanishing -- but it is off
    # by default, because it was measured not to pay.** Dropping these runs was priced as the whole of the ink deficit:
    # they are 25.8 per cent of the skeleton's path and the copy leaves 30 per cent of the artist's ink on the page. What
    # drawing them returns is a third of one per cent of the ink, because the ink they stand on is already inked by the
    # run they were cut from -- and what they cost is doubled alpha there, which reads as beads. The measurement is in
    # the `--fragments` help; the geometry below is right, the compositing is why it does not help.
    long_runs = kept
    short_runs = [run for run in runs if 2 <= len(run) < args.min_segment] if args.fragments else []
    # **The ink's own width and centre, from a cross-section at each skeleton point.** This wrote a constant `2 * scale`
    # for every mark, which is the same fault `render_to_project` had: a traced picture came out at one thickness whatever
    # the reference said. Then it read the distance transform, which gets the width right and still leaves the centre on
    # the integer grid -- measured, 40 per cent of the ink was uncovered at the pixel level while all of it was reached
    # within six. `subpixel_axis` samples across the line instead: the centroid moves the point off the grid and the
    # extent is the width. One section per run, computed once and used twice: to draw that run, and as the pool the
    # fragments borrow from.
    edt = ndimage.distance_transform_edt(mask)
    # **How far the ink reaches, which is not twice the transform on a band the top hat has hollowed out.** One array for
    # the whole page, computed once and handed to every section, because it is a property of the mask rather than of a run.
    room = ring_room(mask, edt)
    sections = [subpixel_axis(mask, run, gray=gray, edt=edt, source=args.width_source, room=room)
                for run in long_runs]
    # **A run's thickness is decided by its middle, because its ends are where other runs meet it.** At a junction the
    # section crosses two or three strokes at once, `cover` comes back large and the mark is drawn as a round black dot --
    # the small version of the seventy-five black bands, and the thing the magnified brick wall showed at every crossing.
    # A cap on the whole drawing cannot reach it: the dot is twenty pixels wide and a heavy line here is sixteen.
    #
    # So the ends of a run are not allowed to be thicker than the median of its own middle. Stated that way it needs no
    # threshold and no knowledge of which junctions exist: a run that really does thicken towards its end is a run whose
    # middle thickens too, and a run whose middle is thin was thin at its ends as well.
    for px_points, px_widths, _edges, _depths in sections:
        if len(px_widths) > 12:
            middle = float(np.median(px_widths[3:-3]))
            px_widths[:3] = [min(w, middle) for w in px_widths[:3]]
            px_widths[-3:] = [min(w, middle) for w in px_widths[-3:]]
    # **One cap for the whole drawing, from the drawing's own widths, because the widest few are not lines.** Seventy-five
    # of three thousand six hundred marks held a point above forty pixels and the widest reached 112.9; in the picture
    # they were black patches at the collar, the jaw and the hem. Twice the ninetieth percentile is what "a heavy line in
    # this drawing" means measured on the drawing itself, so a point beyond it is not a heavy line -- it is a solid region
    # the trace has no business drawing as a stroke. Stated as a cap rather than a threshold because the distribution is
    # what says it, and a different drawing gets a different number for the same reason.
    measured = np.concatenate([np.asarray(widths) for _, widths, _, _ in sections]) if sections else np.zeros(1)
    cap = max(8.0, 2.0 * float(np.percentile(measured, 90))) if measured.size else 0.0
    canvas.settings['width_cap'] = round(cap, 2)
    # The pool the fragments draw on: one row per point of a long run, holding what that point measured.
    pool_points, pool_rows = [], []
    for px_points, px_widths, px_edges, px_depths in sections:
        edge = _edge_of(px_edges, args.edge, scale)
        for k, (x, y) in enumerate(px_points):
            pool_points.append((x, y))
            pool_rows.append((min(px_widths[k], cap), edge, px_depths[k]))
    tree = cKDTree(np.asarray(pool_points, dtype=np.float64)) if pool_points else None

    written = 0
    borrows = 0
    for i, (px_points, px_widths, px_edges, px_depths) in enumerate(sections):
        if len(px_points) < 2:
            continue
        # **`resolution=1` keeps every cross-section**, because `catmull` at one sample per segment returns the points it
        # was given. Simplifying first would put the width profile at control-point resolution and describe a different
        # polyline than the one drawn -- which is what the previous version had to work around by expanding twice.
        points = [(x * scale, y * scale) for x, y in px_points]
        # **The cap follows the line it is on, not the drawing.** Twice the drawing's own ninetieth percentile is one
        # number for marks of every weight, so it is slack on a heavy line and tight on a fine one. A stroke's thickness
        # changes slowly along its length, so the median over twenty-one points is what this line is thick here, and a
        # point half again beyond it is carrying another stroke's ink rather than this one's.
        local = _smooth_depths(px_widths, 21)
        # **A median may lower a width but never raise it.** Smoothing is there to take out the noise a section picks up,
        # and the first version also carried a heavy neighbour's width into a narrow place: the dots that survived every
        # cap were marks twenty-eight pixels wide at points where the artist's grey is 156 -- the width was right for the
        # line a few pixels away and wrong here. Taking the smaller of the smoothed and the measured value keeps the
        # noise out without inventing ink the artist did not put there.
        smoothed = _smooth_depths(px_widths, 9)
        widths = [max(1.0, min(w, raw, cap, 1.5 * c) * scale * args.width_scale)
                  for w, raw, c in zip(smoothed, px_widths, local)]
        # **A mark whose width approaches its own length is a dot, not a stroke.** The four pixels a skeleton junction
        # spawns, drawn ten pixels wide, is exactly the round black dot the magnified brick wall shows at every crossing.
        # Nothing upstream can see it: the width is what the ink says there, and the alpha is what the ink says there.
        span = sum(math.hypot(points[k + 1][0] - points[k][0], points[k + 1][1] - points[k][1])
                   for k in range(len(points) - 1))
        if span > 0.0:
            widths = [min(w, 0.6 * span) for w in widths]
        # **The edge is this line's own, unless the caller pins it.** One constant was measured not to fit the set: on
        # three drawings the value that matched ran from 2.0 to beyond 3.5, and one could not be reached at all because
        # its line is softer than this renderer can express. The section already carries the number, so it is read
        # there -- a line drawn with a dry pen and a line drawn with a wet one stop being the same mark.
        record = core.stroke_record(points, 'fine', seed=i, resolution=1,
                                    width_profile=widths, absolute_width=True,
                                    edge=_edge_of(px_edges, args.edge, scale),
                                    alpha_profile=_smooth_depths(px_depths, 11))
        canvas.add_stroke(record, stage='line', layer='ink', note='reference %d' % i)
        written += 1

    # **The fragments, drawn at their own places in their neighbour's hand.** No fragment exists where there is no long
    # run within a few pixels -- it is a piece of the skeleton that was cut off at a junction -- so the lookup is a local
    # one and a fragment that somehow has no neighbour keeps its own numbers rather than being dropped.
    for j, run in enumerate(short_runs):
        px_points, px_widths, px_edges, px_depths = subpixel_axis(mask, run, gray=gray, edt=edt,
                                                                  source=args.width_source, room=room)
        if len(px_points) < 2:
            continue
        if tree is not None:
            near = tree.query(np.asarray(px_points, dtype=np.float64), k=1)[1]
            px_widths = [pool_rows[int(n)][0] for n in near]
            borrowed = [pool_rows[int(n)][1] for n in near if pool_rows[int(n)][1]]
            px_edges = borrowed
            px_depths = [pool_rows[int(n)][2] for n in near]
            borrows += 1
        points = [(x * scale, y * scale) for x, y in px_points]
        # **The cap follows the line it is on, not the drawing.** Twice the drawing's own ninetieth percentile is one
        # number for marks of every weight, so it is slack on a heavy line and tight on a fine one. A stroke's thickness
        # changes slowly along its length, so the median over twenty-one points is what this line is thick here, and a
        # point half again beyond it is carrying another stroke's ink rather than this one's.
        local = _smooth_depths(px_widths, 21)
        # **A median may lower a width but never raise it.** Smoothing is there to take out the noise a section picks up,
        # and the first version also carried a heavy neighbour's width into a narrow place: the dots that survived every
        # cap were marks twenty-eight pixels wide at points where the artist's grey is 156 -- the width was right for the
        # line a few pixels away and wrong here. Taking the smaller of the smoothed and the measured value keeps the
        # noise out without inventing ink the artist did not put there.
        smoothed = _smooth_depths(px_widths, 9)
        widths = [max(1.0, min(w, raw, cap, 1.5 * c) * scale * args.width_scale)
                  for w, raw, c in zip(smoothed, px_widths, local)]
        # **A mark whose width approaches its own length is a dot, not a stroke.** The four pixels a skeleton junction
        # spawns, drawn ten pixels wide, is exactly the round black dot the magnified brick wall shows at every crossing.
        # Nothing upstream can see it: the width is what the ink says there, and the alpha is what the ink says there.
        span = sum(math.hypot(points[k + 1][0] - points[k][0], points[k + 1][1] - points[k][1])
                   for k in range(len(points) - 1))
        if span > 0.0:
            widths = [min(w, 0.6 * span) for w in widths]
        record = core.stroke_record(points, 'fine', seed=100000 + j, resolution=1,
                                    width_profile=widths, absolute_width=True,
                                    edge=_edge_of(px_edges, args.edge, scale),
                                    alpha_profile=_smooth_depths(px_depths, 11))
        canvas.add_stroke(record, stage='line', layer='ink', note='fragment %d' % j)
        written += 1
    canvas.settings['fragment_marks'] = borrows

    project.save_project(canvas, args.out)
    print('  %s %dx%d, %d line px, %d runs, %d marks (%d borrowing) -> %s'
          % (os.path.basename(args.picture), width, height,
             int(mask.sum()), len(runs), written, borrows, args.out))
    if args.psd:
        layers = psd.layers_from_project(canvas)
        path = psd.save_psd(layers, args.psd)
        print('  %d layer%s -> %s'
              % (len(layers), '' if len(layers) == 1 else 's', path))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
