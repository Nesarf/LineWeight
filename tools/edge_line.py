"""Where a painted picture changes quickly, which is where its structure is: a line drawing derived from tone.

**Why this is a different problem from tracing.** A line drawing states its structure directly -- the lines *are* the
structure. A painted picture states it in the rate of change of tone: an arm is a place where the brightness turns
sharply, and the inside of the arm is not. So the structure is a property of the gradient, and the tool that finds it is
the edge detector, with the two things that make an edge detector useful here rather than noisy everywhere:

- **non-maximum suppression**, so a ramp becomes one pixel of edge instead of a band; and
- **hysteresis**, so an edge is kept only if it is either strong or attached to something strong. A painted reference
  has a gradient almost everywhere; what separates a contour from a cheek's blush is the strength of the change, not
  the fact of it.

The result is a one-pixel structure line which is then walked into polylines and drawn, exactly as a traced skeleton is.

    python tools/edge_line.py --src "...jpg" --out out.json --png out.png --render
"""
import argparse
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from lineweight import core, project

import trace as silhouette

#: Blur before differentiating. **A painted reference has noise at the scale of one pixel** -- texture, brushwork, the
#: JPEG's own blocks -- and differentiating that noise gives edges everywhere. The blur is the scale below which a
#: difference stops being structural.
BLUR = 2.0

#: Percentiles of the surviving gradient magnitude that divide strong from weak. **Chosen as quantiles of this
#: picture's own distribution**, so a darker or a flatter reference does not need its numbers changed.
STRONG_PCT = 88.0
WEAK_PCT = 96.0

#: Shortest polyline kept, in work pixels. Shorter runs are the stubble of a noisy gradient.
MIN_SEGMENT = 10


def region_edges(rgb, levels=8, blur=2.0, tolerance=2):
    """Where **one area of colour becomes another**, which is where a form has a boundary.

    **The distinction this makes is the one colour alone could not.** An eye and a brow's shine are both pale edges on
    skin, so no amount of chroma separates them; but an eye is a *different colour area* from the skin around it, while
    a shine is the same area lit. Quantising the picture into a few levels per channel and keeping the pixels where the
    level changes gives exactly the boundaries between areas of material -- and a highlight, being the same material,
    falls inside one area and leaves no boundary behind.

    Quantisation rather than clustering because the picture is five million pixels: a k-means over that is minutes,
    while a blur and a shift is a second and answers the same question -- is the colour on this side the same as the
    colour on that. `tolerance` widens the boundary so a structure line that wanders a pixel off it is not lost.
    """
    from scipy import ndimage
    soft = ndimage.gaussian_filter(rgb.astype(np.float32), blur)
    step = 256.0 / float(max(2, levels))
    q = (soft / step).astype(np.int32)
    key = (q[:, :, 0] * levels + q[:, :, 1]) * levels + q[:, :, 2]
    edge = np.zeros(key.shape, dtype=bool)
    edge[:, 1:] |= key[:, 1:] != key[:, :-1]
    edge[1:, :] |= key[1:, :] != key[:-1, :]
    if tolerance:
        edge = ndimage.binary_dilation(edge, iterations=tolerance)
    return edge


def structure(rgb, blur, strong_pct, weak_pct, pair_distance=4, chroma_guard=0.0, regions=None,
              hysteresis=True, faint_at=0.0):
    """A one-pixel structure mask: Canny on tone, with colour used as a **veto** rather than as weight.

    **Brightness alone cannot tell a contour from a highlight.** A thigh's silhouette and the pale band running down
    that same thigh are both sharp changes in tone. What separates them is colour: crossing a silhouette moves from skin
    to cloth or to background, while crossing a highlight stays on one material and merely gets lighter.

    **Adding colour to the gradient was tried and it is wrong.** A colour gradient is large wherever skin reddens or
    cloth changes dye, so weighting it in multiplied the line count with texture -- freckles, blush, the folds of a
    stocking -- while leaving the very highlights it was meant to remove. The colour is therefore used only to veto: an
    edge that is extremely strong in tone and very weak in colour is a change of light, not of material, and it goes.
    `chroma_guard` at zero turns the veto off.

    **Two sides of one band become one line**, by removing the weaker of two structure pixels found across the gradient
    within `pair_distance`.
    """
    from scipy import ndimage
    rgb = rgb.astype(np.float32)
    tone = ndimage.gaussian_filter(rgb.mean(axis=2), blur)
    # **The two colour differences that carry hue**, green against red and blue against green. A pure brightness edge has
    # none of either; a change of material has both.
    rg = ndimage.gaussian_filter(rgb[:, :, 0] - rgb[:, :, 1], blur)
    gb = ndimage.gaussian_filter(rgb[:, :, 1] - rgb[:, :, 2], blur)
    ty, tx = np.gradient(tone)
    ay, ax = np.gradient(rg)
    by, bx = np.gradient(gb)
    gy, gx = ty, tx
    mag = np.hypot(gx, gy)
    chroma_mag = np.hypot(ax + bx, ay + by)
    angle = (np.rad2deg(np.arctan2(gy, gx)) + 180.0) % 180.0
    octant = ((angle + 22.5) // 45.0).astype(np.int32) % 4

    left = np.roll(mag, 1, axis=1)
    right = np.roll(mag, -1, axis=1)
    up = np.roll(mag, 1, axis=0)
    down = np.roll(mag, -1, axis=0)
    ul = np.roll(up, 1, axis=1)
    dr = np.roll(down, -1, axis=1)
    ur = np.roll(up, -1, axis=1)
    dl = np.roll(down, 1, axis=1)
    pairs = ((left, right), (ul, dr), (up, down), (ur, dl))

    keeps = np.zeros_like(mag, dtype=bool)
    for k, (a, b) in enumerate(pairs):
        # **Only where the gradient points this way, and only if it is a local maximum along it.** That is what turns a
        # ramp into a line; without it every edge is a band and the "line width" is the ramp's width.
        keeps |= (octant == k) & (mag >= a) & (mag >= b)
    thinned = np.where(keeps, mag, 0.0)

    positive = thinned[thinned > 0]
    if not positive.size:
        return np.zeros_like(mag, dtype=bool)
    # **`strong_pct` is where the threshold sits, not what it excludes.** It reads as "97" meaning the ninety-seventh
    # percentile, and the first version wrote `100 - 97` and took the third percentile -- so the threshold was at the
    # *weakest* three per cent of the gradient and almost every edge cleared it. That is why raising the number from
    # ninety-seven to ninety-nine point six changed the mask by 0.01 per cent: both settings were near the floor.
    hi = float(np.percentile(positive, strong_pct))
    lo = float(np.percentile(positive, weak_pct))
    strong = thinned >= hi
    weak = thinned >= lo
    if hysteresis:
        labels, count = ndimage.label(weak, structure=np.ones((3, 3), dtype=np.uint8))
        if not count:
            return strong
        # **An edge is kept if any part of its connected run is strong.** This is the hysteresis: it lets a contour
        # continue through the soft places instead of stopping wherever the paint got light.
        attached = np.zeros(count + 1, dtype=bool)
        attached[np.unique(labels[strong])] = True
        attached[0] = False
        kept = attached[labels]
    else:
        # **Threshold alone.** Measured on a painted reference: raising the strong percentile from ninety-seven to
        # ninety-nine point six left the mask at 2.82 per cent both times, because with hysteresis a run survives
        # whole as soon as one edge in it is strong -- and in a painted picture strong edges are everywhere, so
        # nothing is ever dropped. Thresholds that cannot change the answer are not thresholds.
        kept = strong

    if chroma_guard > 0 and kept.any():
        # **The veto.** Among the edges kept, those whose tone change is in the top tenth while their colour change is
        # among the smallest are changes of light, not of material -- the pale band down a thigh, the sheen on a
        # stocking. A silhouette crosses a change of material and always has colour under it.
        tone_top = float(np.percentile(mag[kept], 90.0))
        chroma_scale = float(chroma_mag.max()) or 1.0
        kept &= ~((mag >= tone_top) & (chroma_mag < chroma_guard * chroma_scale))

    if regions is not None:
        # **A structure line has to lie on a boundary between areas of colour.** Everything else -- a highlight inside one
        # material, a gradient on a cheek, the sheen along a stocking -- is a change of light within a form, and a form
        # with no boundary there does not have a line there.
        kept &= regions

    if faint_at > 0.0 and regions is not None:
        # **The lines an out-of-focus edge took away.** A painted background is blurred and a soft edge has a gradient
        # below any threshold that would keep a contour; the areas are still there and the boundary between them is
        # still a boundary. So a colour boundary carrying only a faint gradient is kept at `faint_at` of the strong
        # threshold -- which is where a window frame or a floral pattern in a defocused corner comes back.
        # **A fraction of the strong threshold, not of the median gradient.** Measured against the median it admitted
        # ten per cent of the page -- the median of a painted picture's gradient is near zero, so "half the median" is
        # almost no threshold at all. Against `hi` the number means what it says: half as strong as a contour.
        floor = hi * faint_at
        faint = regions & (mag < hi) & (mag >= floor)
        kept |= faint

    if pair_distance > 0:
        h, w = tone.shape
        ys, xs = np.mgrid[0:h, 0:w]
        ux = gx / (mag + 1e-6)
        uy = gy / (mag + 1e-6)
        drop = np.zeros_like(kept)
        for sign in (1, -1):
            sx = np.clip((xs + sign * pair_distance * ux).round().astype(np.int32), 0, w - 1)
            sy = np.clip((ys + sign * pair_distance * uy).round().astype(np.int32), 0, h - 1)
            # **A partner across the gradient that is stronger, and the two are near enough to be one band's two sides.**
            # Distance is measured against the gradient, so "across" means across the edge, not along it.
            partner = kept[sy, sx] & (mag[sy, sx] > mag)
            drop |= partner & kept
        kept &= ~drop
    return kept


def walks(mask, min_segment):
    """The mask's structure lines, walked the way a skeleton is walked."""
    import copy_linework as cl
    skel = cl.thin(mask.astype(np.uint8))
    segments = cl.trace(skel)
    out = []
    for seg in segments:
        if len(seg) < min_segment:
            continue
        pts = [(float(x), float(y)) for y, x in seg]
        out.append(silhouette.douglas_peucker(pts, 0.8))
    return out


def polyline_length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def end_direction(pts, at_start):
    """The direction a polyline leaves from one of its ends, pointing **outward**."""
    if len(pts) < 2:
        return (0.0, 0.0)
    if at_start:
        a, b = pts[0], pts[1]
    else:
        a, b = pts[-1], pts[-2]
    dx, dy = a[0] - b[0], a[1] - b[1]
    n = math.hypot(dx, dy) or 1.0
    return (dx / n, dy / n)


def is_closed(pts, tolerance=8.0):
    """Whether a polyline comes back to where it started -- **the one thing a break and an eye do not share**."""
    if len(pts) < 3:
        return False
    return math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= tolerance


def ring_regions(mask, min_area=120, max_area=20000, min_hole=20):
    """The small areas a closed run encloses: **a pupil is a hole, not a pair of nearby endpoints.**

    **Why this cannot be done on the polylines.** The walker cuts a ring open at the point where it starts, so a closed
    loop of pixels comes back as an open path whose two ends have drifted apart -- measured, only eleven of eighteen
    hundred strokes looked closed by their endpoints. The mask still knows: a ring is a connected component that
    encloses a hole, and its size says whether that hole is a feature or the inside of a contour.

    Returns the filled areas, not the rings themselves, so a stroke belonging to a feature can be recognised by lying in
    one of them.
    """
    from scipy import ndimage
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    keep = np.zeros(mask.shape, dtype=bool)
    # **Each component measured inside its own box.** Filling holes on the full page for every component is a full page
    # of work per component, and a structure mask has thousands; the box is the size of the stroke.
    for i, window in enumerate(ndimage.find_objects(labels), start=1):
        if window is None:
            continue
        blob = (labels[window] == i)
        filled = ndimage.binary_fill_holes(blob)
        enclosed = int(filled.sum()) - int(blob.sum())
        if enclosed < min_hole:
            continue
        if not (min_area <= int(filled.sum()) <= max_area):
            continue
        # **The ring itself, not what it encloses.** A stroke belonging to a pupil runs *along* the ring, so asking
        # whether a point is inside the enclosed area asks the wrong question -- the answer was six strokes in eighteen
        # hundred. The ring's own pixels are where the stroke is.
        keep[window] |= blob
    return keep


def local_support(lines, radius=30.0, min_support=0.0):
    """How much other stroke lies near each stroke: **support measured locally, because connectivity does not work.**

    **Why the group test failed.** A real drawing's lines touch each other -- a contour meets the hair that crosses it,
    which meets the shoulder -- so the connected groups of an honest structure mask are one group of twelve hundred and
    seventy-six strokes and three hundred small ones. Asking "is this stroke in a large group" is then asking "is this
    stroke in the drawing", and the answer is always yes.

    What separates a lash from a speck is not connectivity but **density**: within thirty pixels a lash has the rest of
    the eye around it, and a speck of noise has nothing. So for every stroke the total length of other strokes within
    `radius` of its middle is summed.

    Returns a list of supports, one per stroke, in the same order.
    """
    cell = max(radius, 1.0)
    buckets = {}
    for i, line in enumerate(lines):
        for x, y in line:
            buckets.setdefault((int(x // cell), int(y // cell)), set()).add(i)
    lengths = [polyline_length(l) for l in lines]
    supports = []
    for i, line in enumerate(lines):
        mx = sum(p[0] for p in line) / len(line)
        my = sum(p[1] for p in line) / len(line)
        total = 0.0
        seen = set()
        cx, cy = int(mx // cell), int(my // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in buckets.get((cx + dx, cy + dy), ()):
                    if j == i or j in seen:
                        continue
                    seen.add(j)
                    if any(math.hypot(p[0] - mx, p[1] - my) <= radius for p in lines[j]):
                        total += lengths[j]
        supports.append(total)
    return supports


def group_lines(lines, reach=20.0, angle_deg=35.0):
    """Which strokes belong to one form: **the level at which an eye can be told from a speck.**

    **A filter decides one stroke at a time, and that is the wrong unit for a face.** An eye is five to eight short runs
    -- a lash, both lids, the pupil's edge -- each five to ten pixels; a piece of noise is one run of the same length.
    So the strokes are the same size and the forms are not, and no threshold on a stroke can separate them. What
    separates them is how many strokes are joined to each other, which needs the strokes to be grouped before anything
    is judged.

    Two strokes are joined when an end of one is within `reach` of an end of the other and the two point opposite ways,
    the same test a continuation uses -- so a group is a set of strokes that would draw one connected figure. Grouping
    is by connected components over that relation, found through a grid so that thousands of strokes do not become
    millions of comparisons.
    """
    count = len(lines)
    parent = list(range(count))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    cell = max(reach, 1.0)
    buckets = {}
    for i, line in enumerate(lines):
        for x, y in line:
            key = (int(x // cell), int(y // cell))
            buckets.setdefault(key, set()).add(i)

    keep_long = math.cos(math.radians(angle_deg))
    for (cx, cy), members in buckets.items():
        neighbours = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbours |= buckets.get((cx + dx, cy + dy), set())
        for i in members:
            for j in neighbours:
                if j <= i or find(i) == find(j):
                    continue
                if linkable(lines[i], lines[j], reach, keep_long):
                    union(i, j)

    groups = {}
    for i in range(count):
        groups.setdefault(find(i), []).append(i)
    return groups


def linkable(a, b, reach, keep_long):
    """Whether two strokes would meet: an end near an end, with the two outward directions facing."""
    for at_start in (True, False):
        px, py = a[0] if at_start else a[-1]
        dx, dy = end_direction(a, at_start)
        for other_start in (True, False):
            qx, qy = b[0] if other_start else b[-1]
            if math.hypot(qx - px, qy - py) > reach:
                continue
            ox, oy = end_direction(b, other_start)
            if -(dx * ox + dy * oy) >= keep_long:
                return True
    return False


def prune_fragments(lines, long_length, reach=14.0, angle_deg=35.0, close_tolerance=8.0,
                    ring_min=20.0, ring_max=600.0, enclosures=None, support_radius=30.0, support_min=0.0):
    """Drop the short strokes that **neither continue anything, nor close, nor lie on a small ring.**

    **Three different questions, and the third is the one a face needs.** A length threshold cannot tell a lash from a
    speck, because both are thirty pixels. A continuation test keeps a lash that continues a hairline. A ring test keeps
    a pupil that closes on itself. **But an eye is none of those**: it is five to eight short runs, each five to ten
    pixels, none of them continuing a long stroke and none closing alone -- and together they are a face's most
    important feature.

    **`support_min` and the grouping path are kept and default off.** Measured on this reference, a connected group is
    the whole figure (twelve hundred of two thousand strokes) and local support is high for debris because debris comes
    in fields, so neither can tell a lash from a speck. They stay because the measurement may differ on another
    picture, and a tool that forgot why it stopped trying would try again for no reason.
    """
    supports = local_support(lines, support_radius) if support_min > 0 else None
    longs = [l for l in lines if polyline_length(l) >= long_length]
    keep_long = math.cos(math.radians(angle_deg))
    out = []
    for index, line in enumerate(lines):
        span = polyline_length(line)
        if supports is not None and supports[index] >= support_min:
            # **Supported locally**: the rest of a form lies within a thirty pixel radius, which a speck of noise
            # cannot say.
            out.append(line)
            continue
        if span >= long_length:
            out.append(line)
            continue
        if is_closed(line, close_tolerance) and ring_min <= span <= ring_max:
            # **A closed ring of feature size is kept on its own authority**, without needing to continue anything.
            out.append(line)
            continue
        if enclosures is not None:
            # **The mask's own answer about what is enclosed.** A stroke lying on a small ring is the edge of a feature
            # -- a pupil, a button -- and it is a feature whether or not it closes or continues.
            h, w = enclosures.shape
            inside = False
            for x, y in line:
                ix, iy = int(round(x)), int(round(y))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        jy, jx = iy + dy, ix + dx
                        if 0 <= jy < h and 0 <= jx < w and enclosures[jy, jx]:
                            inside = True
                            break
                    if inside:
                        break
                if inside:
                    break
            if inside:
                out.append(line)
                continue
        joined = False
        for at_start in (True, False):
            px, py = line[0] if at_start else line[-1]
            dx, dy = end_direction(line, at_start)
            for other in longs:
                for other_start in (True, False):
                    qx, qy = other[0] if other_start else other[-1]
                    if math.hypot(qx - px, qy - py) > reach:
                        continue
                    ox, oy = end_direction(other, other_start)
                    # **Facing each other**: the two outward directions are opposed, so the pieces would meet.
                    if -(dx * ox + dy * oy) >= keep_long:
                        joined = True
                        break
                if joined:
                    break
            if joined:
                break
        if joined:
            out.append(line)
    return out


def merge_fragments(lines, reach=18.0, angle_deg=35.0, merge_below=90.0, rounds=6):
    """Chain strokes whose ends face each other into one polyline, so a soft edge becomes a line.

    **Why joining is a separate step from keeping.** A defocused edge does not survive non-maximum suppression as an
    unbroken run: the gradient crosses the threshold repeatedly, so the mask comes back as a dotted trail and the walk
    returns it as a chain of small strokes. Keeping those strokes is correct -- they are the boundary -- but a drawing
    would have drawn one line. Joining them restores the line without re-admitting anything that was dropped.

    **Only short strokes are joined, in rounds.** A stroke already longer than `merge_below` is a line in its own right
    and merging it would fold two separate contours together; a short one is a piece. Each round rebuilds a grid of the
    current pool, so the cost follows the number of short strokes and their neighbours rather than the square of the
    pool, and it stops when a round changes nothing.
    """
    keep_long = math.cos(math.radians(angle_deg))
    pool = [list(line) for line in lines]
    for _ in range(rounds):
        cell = max(reach, 1.0)
        buckets = {}
        for i, line in enumerate(pool):
            for x, y in line:
                buckets.setdefault((int(x // cell), int(y // cell)), set()).add(i)
        absorbed = set()
        for i, line in enumerate(pool):
            if i in absorbed or polyline_length(line) >= merge_below:
                continue
            best = None
            for at_start in (True, False):
                px, py = line[0] if at_start else line[-1]
                dx, dy = end_direction(line, at_start)
                cx, cy = int(px // cell), int(py // cell)
                for ax in (-1, 0, 1):
                    for ay in (-1, 0, 1):
                        for j in buckets.get((cx + ax, cy + ay), ()):
                            if j == i or j in absorbed:
                                continue
                            for other_start in (True, False):
                                qx, qy = pool[j][0] if other_start else pool[j][-1]
                                gap = math.hypot(qx - px, qy - py)
                                if gap > reach:
                                    continue
                                ox, oy = end_direction(pool[j], other_start)
                                if -(dx * ox + dy * oy) < keep_long:
                                    continue
                                if best is None or gap < best[0]:
                                    best = (gap, j, at_start, other_start)
            if best is None:
                continue
            _gap, j, at_start, other_start = best
            head = list(reversed(line)) if at_start else list(line)
            tail = list(pool[j]) if other_start else list(reversed(pool[j]))
            pool[j] = head + tail
            absorbed.add(i)
        pool = [line for k, line in enumerate(pool) if k not in absorbed]
    return pool


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--png', default='')
    ap.add_argument('--min-long-side', type=int, default=2880)
    ap.add_argument('--canvas-side', type=float, default=0)
    ap.add_argument('--blur', type=float, default=BLUR)
    ap.add_argument('--strong', type=float, default=90.0)
    ap.add_argument('--weak', type=float, default=99.5)
    ap.add_argument('--min-segment', type=int, default=5)
    ap.add_argument('--prune-length', type=float, default=20.0,
                    help='strokes shorter than this must continue a longer one to be kept; 0 turns it off')
    ap.add_argument('--hysteresis', action='store_true',
                    help='grow strong edges through weak ones; measured to disable the threshold on painted pictures')
    ap.add_argument('--prune-reach', type=float, default=25.0,
                    help='how far across a gap a stroke may be to count as a continuation')
    ap.add_argument('--prune-angle', type=float, default=20.0,
                    help='how many degrees a continuation may deviate')
    ap.add_argument('--close-tolerance', type=float, default=8.0,
                    help='how near a stroke\'s two ends must be for it to count as a ring')
    ap.add_argument('--ring-min', type=float, default=20.0,
                    help='shortest ring kept for being a feature; below this a loop is a skeleton knot')
    ap.add_argument('--ring-max', type=float, default=600.0,
                    help='longest ring kept for being a feature; longer than this it is a contour')
    ap.add_argument('--rings', action='store_false', default=False,
                    help='keep strokes lying on a small enclosed area; measured to be a hole rather than a help')
    ap.add_argument('--ring-area-min', type=float, default=120.0,
                    help='smallest enclosed area treated as a feature')
    ap.add_argument('--ring-area-max', type=float, default=20000.0,
                    help='largest enclosed area treated as a feature')
    ap.add_argument('--group-min', type=int, default=0,
                    help='unused: connectivity groups the whole drawing, see local_support')
    ap.add_argument('--support-radius', type=float, default=30.0,
                    help='how near other strokes must be to support a short one')
    ap.add_argument('--support-min', type=float, default=0.0,
                    help='total length of neighbouring strokes needed to keep a short one; 0 off, and measured to fail')
    ap.add_argument('--pair-distance', type=float, default=4.0,
                    help='how far across the gradient to look for the other side of one band; 0 keeps both')
    ap.add_argument('--width', type=float, default=2.4, help='pen width on the page')
    ap.add_argument('--chroma-guard', type=float, default=0.0,
                    help='veto edges this strong in tone but this weak in colour; 0 turns the veto off')
    ap.add_argument('--regions', type=int, default=16,
                    help='keep only edges on a boundary between colour areas, quantised to this many levels; 0 off')
    ap.add_argument('--region-tolerance', type=int, default=1,
                    help='how far an edge may sit from the colour boundary and still count')
    ap.add_argument('--region-blur', type=float, default=3.0,
                    help='smoothing before the areas are cut; 0 follows the structure blur, larger cuts fewer areas')
    ap.add_argument('--dump-lines', default='',
                    help='write the pre-pruning strokes to this json file, for comparing two runs as data')
    ap.add_argument('--merge-reach', type=float, default=18.0,
                    help='how far across a gap two strokes may be and still be joined into one line; 0 off')
    ap.add_argument('--merge-angle', type=float, default=35.0,
                    help='how many degrees a join may deviate')
    ap.add_argument('--faint', type=float, default=0.6,
                    help='keep colour boundaries down to this fraction of the median gradient, for defocused areas; 0 off')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    from PIL import Image
    # **Colour, not grey.** The distinction between a contour and a highlight lives in hue; dropping to luminance at the
    # door is what makes the two indistinguishable for everything downstream.
    img = Image.open(args.src).convert('RGB')
    ref_size = img.size
    ref_long = float(max(ref_size))
    canvas_long = max(2880.0, ref_long * 1.2, args.canvas_side)
    work_long = max(float(args.min_long_side), ref_long)
    scale = work_long / ref_long
    work = (int(round(ref_size[0] * scale)), int(round(ref_size[1] * scale)))
    if work != ref_size:
        img = img.resize(work, Image.LANCZOS)
    rgb = np.asarray(img, dtype=np.float32)
    w, h = work
    s = canvas_long / float(max(w, h))
    # **Every pixel quantity is quoted at a standard working size and scaled from it.** Measured: the same reference at a
    # working long side of 1600 gives 1012 strokes and at 3541 gives 3931, on a mask of identical coverage -- one line
    # is cut into more pieces when there are more pixels to cut it in. So a length floor of forty pixels means one thing
    # at 1600 and another at 3541, and a default tuned at one size is wrong at the other. The reference size is 2880,
    # the floor this tool requires; everything in pixels is multiplied by how far the actual working size is from it.
    k = work_long / 2880.0
    if abs(k - 1.0) > 0.01:
        print('  pixel thresholds quoted at 2880, scaled by %.2f for this working size' % k)
    print('  %s  work %dx%d, page %dx%d'
          % (pathlib.Path(args.src).name, w, h, round(w * s), round(h * s)))

    edges = None
    if args.regions:
        edges = region_edges(rgb, args.regions, args.region_blur or args.blur * 1.5, args.region_tolerance)
        print('  colour area boundaries %d px (%.2f%% of the page)'
              % (int(edges.sum()), 100.0 * edges.sum() / edges.size))
    mask = structure(rgb, args.blur, args.strong, args.weak, args.pair_distance,
                     args.chroma_guard, edges, args.hysteresis, args.faint)
    print('  structure pixels %d (%.2f%% of the page)' % (int(mask.sum()), 100.0 * mask.sum() / (w * h)))
    lines = walks(mask, max(1, int(round(args.min_segment * k))))
    print('  %d structure lines, %d points'
          % (len(lines), sum(len(l) for l in lines)))
    if args.dump_lines:
        # **The strokes as data, so two runs can be compared rather than described.** A count that disagrees between the
        # tool and a direct call to the same function is not a matter of opinion; it is two different lists.
        import json as _json
        dump = pathlib.Path(args.dump_lines)
        dump.parent.mkdir(parents=True, exist_ok=True)
        with open(dump, 'w', encoding='utf-8') as handle:
            _json.dump([[list(p) for p in line] for line in lines], handle)
        print('  lines dumped to %s' % args.dump_lines)
    if args.prune_length:
        before = len(lines)
        enclosures = None
        if args.rings:
            enclosures = ring_regions(mask, args.ring_area_min * k * k, args.ring_area_max * k * k)
            print('  enclosed feature areas %d px in %d pieces'
                  % (int(enclosures.sum()), int(np.count_nonzero(np.diff(enclosures.astype(np.int8), axis=0)))))
        lines = prune_fragments(lines, args.prune_length * k, args.prune_reach * k, args.prune_angle,
                                args.close_tolerance * k, args.ring_min * k, args.ring_max * k, enclosures,
                                args.support_radius * k, args.support_min)
        print('  fragments: %d kept of %d, %d dropped as continuation of nothing'
              % (len(lines), before, before - len(lines)))
        long_count = sum(1 for l in lines if polyline_length(l) >= args.prune_length * k)
        print('    prune: length %.1f reach %.2f angle %.0f close %.1f rings %s long %d of %d'
              % (args.prune_length * k, args.prune_reach * k, args.prune_angle,
                 args.close_tolerance * k, args.rings, long_count, len(lines)))

    # **The dotted trail a soft edge leaves becomes a line here.** Joining changes no decision about what to keep, only
    # how many marks it takes to say it.
    if args.merge_reach:
        before_merge = len(lines)
        lines = merge_fragments(lines, args.merge_reach * k, args.merge_angle, 90.0 * k)
        print('  joined: %d strokes -> %d lines' % (before_merge, len(lines)))

    # **The debris figure the objective is measured on.** A speck is short and alone: under fifteen pixels with nothing
    # else within twenty-five, both quoted at the 2880 reference size and scaled like every other length.
    supports = local_support(lines, 25.0 * k)
    debris = sum(1 for line, support in zip(lines, supports)
                 if polyline_length(line) < 15.0 * k and support < 5.0 * k)
    print('  debris: %d of %d strokes are short and alone (%.2f%%)'
          % (debris, len(lines), 100.0 * debris / max(1, len(lines))))

    proj = project.Project(width=int(round(w * s)), height=int(round(h * s)),
                           title='structure of %s' % pathlib.Path(args.src).stem)
    for i, pts in enumerate(lines):
        if len(pts) < 2:
            continue
        scaled = [(x * s, y * s) for x, y in pts]
        # **No Catmull expansion on a structure line.** The polylines here already come from a skeleton and a finer walk
        # than a hand ever draws, so interpolating four points between every two adds marks and adds no shape -- and a
        # dozen thousand marks is minutes of rasterising. Resolution one means the stored centre line is the polyline.
        rec = core.stroke_record(scaled, 'fine', seed=i, resolution=1,
                                 width_profile=[args.width] * len(scaled))
        proj.add_stroke(rec, stage='line', layer='ink', note='structure %d' % i)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out))
    print('  written to %s' % out)
    if args.render:
        import subprocess
        png = args.png or str(out.with_suffix('.png'))
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', png],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
