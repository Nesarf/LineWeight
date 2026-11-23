"""The line, taken from the boundaries between colour areas instead of from the gradient.

**The two layers were deciding the same thing twice and disagreeing.** The fills say where the materials are: colour
areas covering the figure. The strokes say where the joins are -- but they are found from the gradient, so a cheek's
shading boundary is as strong an edge as a jaw, and on the reference measured here the result was twenty-odd strokes
across a face and none on an eye.

**A boundary between two colour areas is a place where something changes**, which is what a line in a cel drawing is. So
the candidate set becomes the set of label edges.

**What changes is not always the material, and that distinction is measurable.** The two areas on either side of a
boundary differ in lightness, in colour, or in both. Skin against hair differs in both; a cheek against its own shadow
differs in lightness alone while the hue stays put. A cel drawing keeps the first and either drops or draws thin the
second, so the question "should this line be here" becomes "which of these two quantities moved", and that is answered
from the median colour of two smoothed areas rather than from one pixel of gradient.

    python tools/line_from_shapes.py --reference "...jpg" --out E:\\DaShaoHuo\\cache\\edges.png
"""
import argparse
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, r'D:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import shape_pass
import value_pass

NEIGHBOURS = ((0, 1), (1, 0), (1, 1), (1, -1))

#: Long side the cut is made at when the reference is smaller. **The cut has to match the fills' cut**, or a line sits
#: beside the boundary it is supposed to describe; `shape_pass` enlarges a small reference to at most this.
UPSCALE_CAP = 2400.0


def label_edges(labels):
    """Every neighbouring pair of pixels that carries two different labels, as four long arrays.

    **Eight neighbours, not four.** A diagonal join has no side neighbour on either cell, so a four-connected test leaves
    the whole staircase of a diagonal boundary out -- and a diagonal boundary is what most contours are.

    **Four flat arrays rather than a list of tuples.** The join count on a two-and-a-half thousand wide reference is
    around three and a half million, and arithmetic done one pair at a time in Python takes fifteen minutes where the same
    arithmetic over the whole array takes under a second.
    """
    ys = []
    xs = []
    lows = []
    highs = []
    for dy, dx in NEIGHBOURS:
        a = labels[max(0, dy):labels.shape[0] + min(0, dy), max(0, dx):labels.shape[1] + min(0, dx)]
        b = labels[max(0, -dy):labels.shape[0] + min(0, -dy), max(0, -dx):labels.shape[1] + min(0, -dx)]
        same = a == b
        if not (~same).any():
            continue
        ya, xa = np.nonzero(~same)
        ys.append((ya + max(0, dy)).astype(np.int64))
        xs.append((xa + max(0, dx)).astype(np.int64))
        lows.append(np.minimum(a[~same], b[~same]).astype(np.int32))
        highs.append(np.maximum(a[~same], b[~same]).astype(np.int32))
    if not ys:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty, np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32)
    return (np.concatenate(ys), np.concatenate(xs),
            np.concatenate(lows), np.concatenate(highs))


def colour_table(labels, rgb):
    """The mean colour of every area. **The fills' own table, not a second one** -- if this computed its own the two
    layers would disagree about a boundary by whatever their averaging differs by, and the line would sit beside the
    shape it is supposed to describe."""
    table, _counts = shape_pass.colour_table(labels, rgb)
    return table


def rgb_stats(table):
    """Lightness, saturation and hue for every area colour.

    **Hue is circular and a mean of angles is wrong.** Red at 0.98 and red at 0.02 average to 0.5, which is cyan; a gap
    between two hues is therefore measured as the shorter way round the circle.
    """
    r, g, b = table[:, 0], table[:, 1], table[:, 2]
    light = 0.2126 * r + 0.7152 * g + 0.0722 * b
    mx = table.max(axis=1)
    mn = table.min(axis=1)
    span = np.maximum(mx - mn, 1e-6)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    hue = np.zeros_like(mx)
    top = mx == r
    mid = (mx == g) & ~top
    hue[top] = ((g[top] - b[top]) / span[top]) % 6.0
    hue[mid] = (b[mid] - r[mid]) / span[mid] + 2.0
    low = ~(top | mid)
    hue[low] = (r[low] - g[low]) / span[low] + 4.0
    return light, sat, hue / 6.0


def scatter_max(index, values, size):
    """The largest value at each index, in one pass.

    **`np.maximum.at` is the obvious call and it is slow** -- an unbuffered ufunc over millions of elements runs at a
    fraction of the speed of a sort. Sorting by index and taking the maximum of each run is a second for the same answer.
    """
    order = np.argsort(index, kind='stable')
    ordered_index = index[order]
    ordered_value = values[order]
    starts = np.flatnonzero(np.r_[True, ordered_index[1:] != ordered_index[:-1]])
    out = np.zeros(size, dtype=np.float32)
    out[ordered_index[starts]] = np.maximum.reduceat(ordered_value, starts)
    return out


def material_classes(table, k):
    """Group area colours by where they sit in the colour plane, ignoring how light they are.

    **This is the distinction the lightness gap could not make.** A lock of hair runs from violet shadow to white
    highlight; quantised, that becomes a dozen areas, and every join between two of them moves the saturation a little,
    so a threshold on the colour difference calls each one a material change -- which is what put twenty lines across a
    face. Dropped into a plane whose axes are saturation times the cosine and sine of hue, those dozen areas land close
    together, because they *are* one material at different lightnesses; a join between hair and skin lands far apart.

    The clustering is plain k-means over that plane, with the areas weighted by their pixel count so a handful of specks
    cannot pull a centre.
    """
    light, sat, hue = rgb_stats(table)
    angle = 2.0 * np.pi * hue
    points = np.stack([sat * np.cos(angle), sat * np.sin(angle)], axis=1)
    weight = np.maximum(light, 0.0) * 0.0 + 1.0        # every area counts once; see below
    labels = np.zeros(len(table), dtype=np.int32)
    if k <= 1 or len(table) < 3:
        return labels
    # **Seeded from the colours that are actually present**, spaced out across the plane, so the result does not depend on
    # an unlucky start.
    present = np.arange(1, len(table))
    present = present[weight[present] > 0]
    if present.size < k:
        return labels
    order = np.argsort(-np.hypot(points[present, 0], points[present, 1]))
    centres = points[present[order[:k]]].copy()
    for _ in range(24):
        distance = ((points[present, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        chosen = distance.argmin(axis=1)
        moved = False
        for c in range(k):
            part = present[chosen == c]
            if part.size:
                new = points[part].mean(axis=0)
                if np.abs(new - centres[c]).max() > 1e-4:
                    moved = True
                centres[c] = new
        if not moved:
            break
    labels[present] = chosen
    return labels


def coarse_boundary(rgb, person, levels, blur, min_area, downsample=1):
    """The boundaries between areas that survive a much coarser cut, widened a little.

    **A feature's scale is the range over which it is still there.** A lock of hair, a fold in cloth and the shading
    across a cheek are all made of areas too, and at fine quantisation every join between them is a boundary -- which is
    what put twenty lines across a face. Cut the same picture three times blurrier and four times coarser and those joins
    merge into one area and stop being boundaries, while the join between hair and skin does not: it is a change of
    material at any scale.

    So the coarse cut answers "is this a real edge" and the fine cut answers "where exactly". The coarse set is widened
    because the two cuts place a boundary a pixel or two apart.

    **`downsample` is kept and defaults to one because shrinking the picture was tried and it changes the answer.** It
    does make this stage cheaper -- 31.6 seconds to 10.6 on a two-thousand-four-hundred-wide reference, the largest single
    item in the line pass. But a picture shrunk by four is not the same picture viewed more coarsely: it has lost the
    detail the fine cut is compared against, so the coarse cut keeps far more boundaries (76 per cent of them against 35)
    and everything downstream doubles -- pruning 31 to 103 seconds, records 19 to 56. The net was 83 seconds *slower*.
    **An optimisation that changes what the stage decides is not an optimisation**, and the numbers are here so the idea is
    not tried again casually.
    """
    from scipy import ndimage
    h, w = person.shape
    if downsample > 1:
        from PIL import Image
        sw, sh = max(1, w // downsample), max(1, h // downsample)
        small_rgb = np.stack([
            np.asarray(Image.fromarray(rgb[:, :, c]).resize((sw, sh), Image.BILINEAR), dtype=np.float32)
            for c in range(3)], axis=2)
        small_person = np.asarray(Image.fromarray(person.astype(np.uint8) * 255).resize((sw, sh), Image.NEAREST)) > 127
    else:
        small_rgb, small_person = rgb, person

    key = np.where(small_person, shape_pass.quantise(small_rgb, max(2, levels // 2), blur * 3.0 / max(1, downsample)),
                   -1)
    labels = shape_pass.equal_components(key)
    labels = np.where(small_person, labels, 0)
    labels = shape_pass.absorb(labels, max(1, int(round(min_area * 4 / float(downsample * downsample)))))
    edge = np.zeros(labels.shape, dtype=bool)
    for dy, dx in NEIGHBOURS:
        a = labels[max(0, dy):labels.shape[0] + min(0, dy), max(0, dx):labels.shape[1] + min(0, dx)]
        b = labels[max(0, -dy):labels.shape[0] + min(0, -dy), max(0, -dx):labels.shape[1] + min(0, -dx)]
        edge[max(0, dy):labels.shape[0] + min(0, dy), max(0, dx):labels.shape[1] + min(0, dx)] |= a != b
    areas = int(np.count_nonzero(np.bincount(labels.ravel())[1:]))
    if downsample > 1:
        edge = np.asarray(Image.fromarray(edge.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127
    return ndimage.binary_dilation(edge, iterations=2 * max(1, downsample)), areas


def area_thickness(labels):
    """How thick each area is: the largest distance from a pixel inside it to anything outside it.

    **The shape of the area is the thing none of the colour measures could see.** A lock of hair at one lightness, a fold
    across cloth, a blush on a cheek -- each is a *strip*, and a strip is a couple of pixels thick however long it runs.
    An eye, a button, a bow is a *patch*: small, but as thick as it is wide. Colour cannot separate those two, because a
    strip of hair is a genuine change of colour from the strip beside it; thickness can, because it is measured on the
    area, not on the pair.

    Computed in each area's own bounding box, so the cost follows the areas rather than the canvas.
    """
    from scipy import ndimage
    count = int(labels.max())
    boxes = ndimage.find_objects(labels)
    out = np.zeros(count + 1, dtype=np.float32)
    for i in range(1, count + 1):
        box = boxes[i - 1] if i - 1 < len(boxes) else None
        if box is None:
            continue
        ys, xs = box
        local = labels[ys, xs] == i
        if not local.any():
            continue
        out[i] = float(ndimage.distance_transform_edt(local).max())
    return out


def edge_quantities(labels, table, materials, thickness):
    """For every boundary pixel, the lightness gap, the colour gap and whether the material class changes.

    **All of them are taken from the two areas, not from the boundary.** Hundreds of pixels of two smoothed areas give a
    stable number, where a single pixel of gradient gives whichever side of the anti-aliasing it happens to land on.
    """
    light, sat, hue = rgb_stats(table)
    shape = labels.shape
    ya, xa, low, high = label_edges(labels)
    if ya.size == 0:
        zero = np.zeros(shape, dtype=np.float32)
        return zero, zero, zero, zero, zero.ravel(), zero.ravel(), zero.ravel()
    dl = np.abs(light[low] - light[high]).astype(np.float32)
    dh = np.abs(hue[low] - hue[high])
    dh = np.minimum(dh, 1.0 - dh) * 2.0            # the shorter way round the circle, 0 .. 1
    ds = np.abs(sat[low] - sat[high])
    # **A hue difference only counts where the colour is present.** Two nearly grey areas have a hue that is noise, so the
    # hue term is weighted by the smaller of the two saturations; a change of saturation counts on its own.
    dc = (dh * np.minimum(sat[low], sat[high]) + 0.5 * ds).astype(np.float32)
    # **Crossing a material class is a yes or no**, where the two gaps above are continuous. The class comes from the
    # colour plane alone, so the dozen levels of one lock of hair land in one class and their joins stop being lines.
    dm = (materials[low] != materials[high]).astype(np.float32)
    # **How thin the thinner side is.** A join between a patch and the wide area around it is a contour; a join between
    # two strips is a change of surface along one of them.
    dt = np.minimum(thickness[low], thickness[high]).astype(np.float32)
    size = int(shape[0]) * int(shape[1])
    flat = ya * shape[1] + xa
    gap_light = scatter_max(flat, dl, size).reshape(shape)
    gap_colour = scatter_max(flat, dc, size).reshape(shape)
    gap_material = scatter_max(flat, dm, size).reshape(shape)
    gap_thin = scatter_max(flat, dt, size).reshape(shape)
    return gap_light, gap_colour, gap_material, gap_thin, dl, dc, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--levels', type=int, default=20)
    ap.add_argument('--blur', type=float, default=1.0)
    ap.add_argument('--min-area', type=int, default=150)
    ap.add_argument('--cut-side', type=float, default=0.0)
    ap.add_argument('--faint', type=float, default=0.06)
    ap.add_argument('--heavy', type=float, default=0.30)
    ap.add_argument('--ink', type=float, default=1.0)
    ap.add_argument('--light-ink', type=float, default=0.35,
                    help='how dark a join gets when only its lightness moves, as a fraction of full ink')
    ap.add_argument('--materials', type=int, default=8,
                    help='how many materials the areas are grouped into by their place in the colour plane')
    ap.add_argument('--thin-min', type=float, default=3.0,
                    help='thickness, in cut pixels, that separates a strip from a patch')
    args = ap.parse_args()

    image = Image.open(args.reference).convert('RGB')
    reference_long = float(max(image.size))
    target = args.cut_side or max(reference_long, UPSCALE_CAP)
    scale = target / reference_long
    work = image
    if abs(scale - 1.0) > 1e-6:
        work = image.resize((max(1, int(round(image.size[0] * scale))), max(1, int(round(image.size[1] * scale)))),
                            Image.LANCZOS)
    rgb = np.asarray(work, dtype=np.float32) / 255.0
    w, h = rgb.shape[1], rgb.shape[0]
    gray = (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)
    person = value_pass.person_mask(gray)
    area_threshold = max(1, int(round(args.min_area * scale * scale)))

    key = np.where(person, shape_pass.quantise(rgb, args.levels, args.blur * scale), -1)
    labels = shape_pass.equal_components(key)
    labels = np.where(person, labels, 0)
    labels = shape_pass.absorb(labels, area_threshold)
    table = colour_table(labels, rgb)
    materials = material_classes(table, args.materials)
    thickness = area_thickness(labels)
    gap_light, gap_colour, gap_material, gap_thin, all_light, all_colour, all_thin = edge_quantities(
        labels, table, materials, thickness)
    coarse, coarse_areas = coarse_boundary(rgb, person, args.levels, args.blur * scale, area_threshold)

    areas = np.count_nonzero(np.bincount(labels.ravel())[1:])
    drawn = gap_light > 0
    used = np.count_nonzero(np.bincount(materials[1:], minlength=args.materials))
    print('  cut at %dx%d: %d colour areas in %d materials, %d boundary pixels (%.2f%% of the page)'
          % (w, h, areas, used, int(drawn.sum()), 100.0 * float(drawn.mean())))
    print('  the coarser cut keeps %d areas, so the figure is %d%% of its fine area count'
          % (coarse_areas, int(round(100.0 * coarse_areas / max(1, areas)))))
    print('  lightness gap: median %.3f  p90 %.3f      colour gap: median %.3f  p90 %.3f'
          % (float(np.median(all_light)), float(np.percentile(all_light, 90)),
             float(np.median(all_colour)), float(np.percentile(all_colour, 90))))
    # **The number that decides whether this is worth drawing.** A join inside one material is the same surface at two
    # lightnesses: a lock of hair, a shadow on a cheek. Only a join between two materials is what a cel line marks.
    crossing = gap_material > 0
    stable = drawn & coarse
    print('  joins that cross a material:      %d of %d (%.1f%%)'
          % (int(crossing.sum()), int(drawn.sum()), 100.0 * float(crossing.sum()) / max(1, int(drawn.sum()))))
    print('  joins that survive a coarser cut: %d of %d (%.1f%%)'
          % (int(stable.sum()), int(drawn.sum()), 100.0 * float(stable.sum()) / max(1, int(drawn.sum()))))
    print('  thickness of the thinner side: median %.1f  p10 %.1f  p90 %.1f cut pixels'
          % (float(np.median(all_thin)), float(np.percentile(all_thin, 10)),
             float(np.percentile(all_thin, 90))))
    patch = drawn & (gap_thin >= args.thin_min)
    print('  joins with a patch on one side:    %d of %d (%.1f%%)'
          % (int(patch.sum()), int(drawn.sum()), 100.0 * float(patch.sum()) / max(1, int(drawn.sum()))))
    # **The cross table says which quantity carries the change.** It is what decides whether dropping the "only light
    # moved" group would cost a contour, and on an earlier reference that group turned out to be 1.7 per cent.
    light_hi = all_light > 0.15
    colour_hi = all_colour > 0.08
    print('  material only (colour moved, light held): %5.1f%%' % (100.0 * float((~light_hi & colour_hi).mean())))
    print('  light only (light moved, colour held):    %5.1f%%' % (100.0 * float((light_hi & ~colour_hi).mean())))
    print('  both:                                     %5.1f%%' % (100.0 * float((light_hi & colour_hi).mean())))
    print('  neither (below both floors):              %5.1f%%' % (100.0 * float((~light_hi & ~colour_hi).mean())))

    span = args.heavy - args.faint
    total = np.clip((gap_light + gap_colour - args.faint) / max(1e-6, span), 0.0, 1.0)
    by_colour = np.clip((gap_colour - args.faint) / max(1e-6, span), 0.0, 1.0)
    # **A join that only moves the lightness is drawn at a fraction of the weight.** It is the same rule the taxonomy
    # states: the outline carries the form, the shadow line carries the surface, and only one of them may be heavy.
    by_light = np.clip((gap_light - args.faint) / max(1e-6, span), 0.0, 1.0) * args.light_ink
    # **A join inside one material is drawn not at all.** Where a material changes the line is at least half weight and
    # rises with the colour gap, so a hair against skin is darker than a sleeve against its own lining.
    by_material = gap_material * np.clip(0.45 + (gap_colour - args.faint) / max(1e-6, span), 0.0, 1.0)
    # **The line the two cuts agree on.** A join the coarser cut also sees is a change of shape or material; a join only
    # the fine cut sees is a change of surface within one of them, and that belongs to the shading, not to the ink.
    by_stable = stable * np.clip(0.45 + (gap_colour - args.faint) / max(1e-6, span), 0.0, 1.0)
    # **The line around a patch.** Every join is drawn faintly, and the joins that have a patch on one side are drawn
    # at full weight -- so a face keeps its eye and its jaw and loses the stripes inside its hair.
    by_patch = np.clip(0.30 + (gap_colour - args.faint) / max(1e-6, span), 0.0, 1.0) * (
        0.35 + 0.65 * (gap_thin >= args.thin_min))

    stem = pathlib.Path(args.out)
    stem.parent.mkdir(parents=True, exist_ok=True)
    for name, strength in (('both', total), ('colour', by_colour), ('light', by_light), ('material', by_material),
                           ('stable', by_stable), ('patch', by_patch)):
        out = 1.0 - args.ink * strength
        target_path = stem.with_name('%s-%s%s' % (stem.stem, name, stem.suffix or '.png'))
        Image.fromarray((np.clip(np.repeat(out[:, :, None], 3, axis=2), 0.0, 1.0) * 255.0).astype(np.uint8)
                        ).save(target_path)
        print('  wrote %s' % target_path)

    # **The fills' own cut is written out too**, so a later stage can draw lines from the exact same areas instead of
    # cutting again and landing half a pixel away.
    cache = stem.with_name('%s-labels.npy' % stem.stem)
    np.save(cache, labels)
    meta = stem.with_name('%s-meta.json' % stem.stem)
    meta.write_text(json.dumps({'cut': [w, h], 'scale': scale, 'levels': args.levels,
                                'blur': args.blur * scale, 'min_area': area_threshold}), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
