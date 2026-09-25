"""Tests for the pressure model, the outline expansion and the whole-document inking.

The two most useful tests here are regressions for mistakes that were made while this was being written, and both
were visible only by rendering an image and looking at it: a closed contour walked forwards and then backwards,
which drew its line twice and scalloped every hair mass into fish scales, and a brush with no taper dividing by
zero because a floating-point position can land a hair above 1.0.
"""
from __future__ import annotations

import math

from lineweight import BRUSHES, inked_svg, outline, parse_path, pressures, stroke


def test_parse_handles_the_commands_a_generator_writes():
    polys = parse_path('M 0 0 L 10 0 Q 15 5 10 10 Z')
    assert len(polys) == 1
    # the quadratic is sampled, so the curve arrives as a polyline like everything else
    assert len(polys[0]) > 4
    assert polys[0][0] == (0.0, 0.0)


def test_parse_ignores_what_it_does_not_know_rather_than_guessing():
    # an arc is not handled; the line before it still is, and nothing raises
    polys = parse_path('M 0 0 L 10 0 A 5 5 0 0 1 20 0')
    assert polys and polys[0][0] == (0.0, 0.0)


def test_pressure_tapers_at_both_ends_of_an_open_stroke():
    path = [(x * 10.0, 0.0) for x in range(21)]
    ps = pressures(path, BRUSHES['ink'], seed=0)
    assert ps[0] < ps[len(ps) // 2]
    assert ps[-1] < ps[len(ps) // 2]
    assert all(0.0 < p <= 1.0 for p in ps)


def test_a_brush_with_no_taper_does_not_divide_by_zero():
    # regression: `t` accumulates from floating-point lengths and can exceed 1.0, so the taper test has to be
    # guarded by the taper being non-zero -- otherwise a legitimate brush setting crashes
    brush = dict(BRUSHES['ink'], taper_in=0.0, taper_out=0.0)
    path = [(x * 10.0, 0.0) for x in range(21)]
    ps = pressures(path, brush, seed=1)
    assert len(ps) == len(path)
    assert all(p > 0 for p in ps)


def test_pressure_is_lighter_through_a_sharp_turn():
    straight = [(x * 10.0, 0.0) for x in range(21)]
    turned = [(x * 10.0, 0.0) for x in range(10)] + [(90.0, y * 10.0) for y in range(1, 11)]
    a = pressures(straight, BRUSHES['ink'], seed=3)
    b = pressures(turned, BRUSHES['ink'], seed=3)
    assert min(b[8:13]) < max(a[8:13])


def test_the_outline_is_a_closed_shape_with_area():
    path = [(float(x), math.sin(x / 5.0) * 20.0) for x in range(40)]
    d = outline(path, [6.0] * len(path))
    assert d.startswith('M') and d.endswith('Z')
    xs = [float(v) for v in d.replace('M', '').replace('L', '').replace('Z', '').split()[0::2]]
    ys = [float(v) for v in d.replace('M', '').replace('L', '').replace('Z', '').split()[1::2]]
    assert max(xs) - min(xs) > 30
    assert max(ys) - min(ys) > 30


def test_a_wider_brush_produces_a_wider_outline():
    path = [(float(x), 0.0) for x in range(30)]
    thin = stroke(path, 'fine')[0]
    thick = stroke(path, 'ink')[0]
    def spread(d: str) -> float:
        ys = [float(v) for v in d.replace('M', '').replace('L', '').replace('Z', '').split()[1::2]]
        return max(ys) - min(ys)
    assert spread(thick) > spread(thin)


def test_inking_leaves_small_details_alone():
    # a heavy line around an eye is mud, so extent decides rather than a list of names
    svg = ('<svg><path d="M 0 0 L 100 0 L 100 80 L 0 80 Z" fill="#111"/>'
           '<path d="M 0 0 L 5 0 L 5 5 Z" fill="#222"/></svg>')
    out = inked_svg(svg)
    # each original, a seam stroke for each, and one contour for the big shape -- but no contour for the small one
    contours = [p for p in out.split('<path') if 'fill="#2A1E26"' in p]
    assert len(contours) == 1
    assert out.count('stroke="#111"') == 1
    assert out.count('stroke="#222"') == 1


def test_inking_keeps_every_element_it_does_not_understand():
    # **Regression for the most expensive defect in this library's short life.** `inked_svg` used to collect the
    # paths it matched into a new list and join that into the result, which deleted every element the pattern did
    # not match -- the ellipses carrying a figure's eye whites, irises and catchlights among them. What remained
    # still suggested a face, so the drawings looked plausible with no eyes in them for several rounds.
    svg = ('<svg><rect width="10" height="10" fill="#0f0"/>'
           '<ellipse cx="5" cy="5" rx="3" ry="2" fill="#fff"/>'
           '<g transform="translate(1 1)"><circle cx="2" cy="2" r="1"/></g>'
           '<path d="M 0 0 L 100 0 L 100 80 L 0 80 Z" fill="#111"/></svg>')
    out = inked_svg(svg)
    assert '<rect' in out, 'a rectangle the pattern does not match was dropped'
    assert '<ellipse' in out, 'an ellipse was dropped, which is how the eyes went missing'
    assert '<g transform' in out, 'a group was dropped'
    assert '<circle' in out
    assert out.count('<path') >= 2  # the original plus the contour it earned


def test_a_closed_contour_is_walked_once():
    # regression: walking a loop forwards and then backwards drew the line twice and scalloped the shapes it
    # outlined -- a defect that only a rendered image showed
    svg = '<svg><path d="M 0 0 L 100 0 L 100 80 L 0 80 Z" fill="#111"/></svg>'
    out = inked_svg(svg)
    contour = [p for p in out.split('<path') if 'fill="#2A1E26"' in p]
    assert len(contour) == 1
    # one walk of a four-point loop samples the same number of points as its perimeter, not twice that
    d = contour[0].split('d="')[1].split('"')[0]
    assert d.count('L') < 40


def test_a_stroke_record_round_trips_losslessly():
    """**The whole point of a record is that it can be expanded again.** Everything before this returned a filled
    outline -- right to render, useless to edit, because once a variable-width stroke is a polygon there is no way
    back to the line it came from. A record keeps the brush, the seed, the points and the pressure, so the outline
    can be regenerated at any resolution, the brush swapped, a point moved."""
    from lineweight import from_record, stroke, stroke_record

    points = [(40.0, 40.0), (140.0, 30.0), (240.0, 60.0)]
    a_d, a_opacity = stroke(points, 'ink', seed=3)
    record = stroke_record(points, 'ink', seed=3)
    b_d, b_opacity = from_record(record)

    assert a_d == b_d, 'the outline from a record differs from the one stroke() produced'
    assert abs(a_opacity - b_opacity) < 1e-9
    assert len(record['centre']) == len(record['pressure']) > 4
    for key in ('brush', 'seed', 'colour', 'resolution', 'control', 'centre', 'pressure'):
        assert key in record


def test_a_record_survives_a_trip_through_a_file(tmp_path):
    from lineweight import from_record, load_strokes, save_strokes, stroke, stroke_record

    points = [(10.0, 10.0), (80.0, 40.0)]
    record = stroke_record(points, 'pencil', seed=11)
    path = tmp_path / 'drawing.json'
    save_strokes([record], str(path))
    back = load_strokes(str(path))

    assert back == [record]
    assert from_record(back[0])[0] == stroke(points, 'pencil', seed=11)[0]


def test_a_gap_stops_an_exact_fill_and_closing_it_does_not():
    """**The problem a bucket fill has and an exact fill cannot solve.** Four strokes that almost meet enclose
    nothing, so nothing fills; weld their ends and the same four strokes are a region. The sweep is the point: at a
    tolerance below the gap there is no region, above it there is one, and it does not keep growing."""
    from lineweight import region_fill, weld_endpoints

    square = [
        [(0.0, 0.0), (100.0, 0.0)],
        [(102.0, 2.0), (102.0, 100.0)],
        [(100.0, 102.0), (0.0, 102.0)],
        [(-2.0, 100.0), (-2.0, 2.0)],
    ]
    # the corners are 2.83 apart, so nothing closes below that
    assert len(weld_endpoints(square, 0.0)) == 0
    assert len(weld_endpoints(square, 1.0)) == 0
    assert len(weld_endpoints(square, 3.0)) == 1
    assert len(weld_endpoints(square, 6.0)) == 1, 'a loose tolerance must not keep welding things together'

    regions = region_fill(square, 3.0)
    assert len(regions) == 1
    nums = [float(v) for v in regions[0].replace('M', '').replace('L', '').replace('Z', '').split()]
    points = list(zip(nums[0::2], nums[1::2]))
    area = abs(sum(points[i][0] * points[(i + 1) % len(points)][1]
                   - points[(i + 1) % len(points)][0] * points[i][1]
                   for i in range(len(points)))) / 2
    # the square drawn is about 104 on a side
    assert 9000 < area < 12000, 'the welded region is not the square that was drawn: %s' % area


def test_multiplying_with_nothing_gives_the_thing():
    """**The bug a probe found and looking would not have.** Blend combined against the base colour whatever its
    alpha, and a transparent base has a colour of zero, so a wash crossing a pencil line was painted black where
    there was no pencil line at all. Where the base is empty the top layer simply goes down."""
    from lineweight import stroke_record
    from lineweight.raster import Layer, blend, stroke_layer

    record = stroke_record([(20.0, 80.0), (200.0, 80.0)], 'wash', seed=4)
    record['colour_int'] = (110, 30, 60)
    layer = stroke_layer(record, 220, 160, 1.0)
    empty = Layer(220, 160)

    out = blend(empty, layer, 'multiply', 1.0)
    index = (80 * out.width + 110) * 4
    colour = tuple(out.data[index:index + 3])
    assert out.data[index + 3] > 0, 'the stroke vanished'
    # within two of the brush colour: the wash carries grain now, and grain legitimately settles the alpha a
    # little lower at any given pixel
    assert all(abs(colour[c] - (110, 30, 60)[c]) <= 2 for c in range(3)), (
        'multiplying over nothing gave %s, not the wash colour' % (colour,))


def test_a_straight_stroke_is_continuous_not_a_string_of_beads(tmp_path):
    """Spacing was measured against the brush width times a factor, which for a wide wash drew a dab every fifteen
    pixels. It is measured against the dab's own size, and the value in the brushes was swept: all four stay
    continuous to 0.8 of a diameter and break at 1.0."""
    from lineweight import BRUSHES, stroke_record
    from lineweight.raster import stroke_layer

    for name in ('fine', 'ink', 'pencil', 'wash'):
        record = stroke_record([(20.0, 80.0), (200.0, 80.0)], name, seed=5)
        record['colour_int'] = (40, 34, 48)
        layer = stroke_layer(record, 220, 160, 1.0)
        row = 80 * layer.width * 4
        runs, previous = 0, False
        for x in range(layer.width):
            lit = layer.data[row + x * 4 + 3] > 8
            if lit and not previous:
                runs += 1
            previous = lit
        assert runs == 1, '%s draws %d separate runs of ink along a straight line' % (name, runs)
        assert BRUSHES[name]['spacing'] <= 0.8, 'spacing %s is past the measured threshold' % BRUSHES[name]['spacing']


def test_clipping_is_one_alpha_multiply():
    """Clipping is a multiply of two alphas and nothing else, so it composes: clip a wash to a region, clip that to
    a silhouette, and each step is one multiply. Inverting is the case where the mask is really a hole."""
    from lineweight import stroke_record
    from lineweight.raster import Layer, clip, stroke_layer

    record = stroke_record([(60.0, 140.0), (150.0, 20.0)], 'wash', seed=2)
    record['colour_int'] = (110, 30, 60)
    wash = stroke_layer(record, 220, 160, 1.0)
    disc = Layer(220, 160)
    disc.dab(100, 80, 45, (255, 255, 255), 1.0)

    def alpha(layer, x, y):
        return layer.data[(y * layer.width + x) * 4 + 3]

    # **Find the ink rather than guessing where it is.** Three attempts to name a point by hand put it off the
    # stroke, because a diagonal line is not where it looks like it should be at a given row.
    lit = [(i // 4 % 220, i // 4 // 220) for i in range(3, len(wash.data), 4) if wash.data[i] > 0]
    assert lit, 'the wash drew nothing'
    def mask_alpha(x, y):
        return disc.data[(y * disc.width + x) * 4 + 3] / 255.0

    # near the middle, where the mask is solid; and well outside it, where the mask is nothing. An earlier version
    # called a point 39.4 pixels from the centre of a 45-pixel disc "inside" and expected ink there -- but the disc
    # has a soft edge, so at that distance the mask is only a fifth, and a fifth of an almost transparent edge pixel
    # rounds to nothing. The assertion was wrong, not the clip.
    inside = [p for p in lit if (p[0] - 100) ** 2 + (p[1] - 80) ** 2 < 15 ** 2 and mask_alpha(*p) > 0.9]
    outside = [p for p in lit if (p[0] - 100) ** 2 + (p[1] - 80) ** 2 > 55 ** 2]
    assert inside and outside, 'the disc does not divide the stroke: %d in, %d out' % (len(inside), len(outside))

    kept = clip(wash, disc)
    inverted = clip(wash, disc, invert=True)
    assert alpha(kept, *inside[0]) > 0 and alpha(inverted, *inside[0]) == 0
    assert alpha(kept, *outside[0]) == 0 and alpha(inverted, *outside[0]) > 0
    # the relationship itself: what was kept is the product of the two alphas, rounded
    for point in lit[:400]:
        x, y = point
        expected = int(alpha(wash, x, y) * mask_alpha(x, y))
        assert abs(alpha(kept, x, y) - expected) <= 1, 'clip is not a multiply at %s' % (point,)
    # and clipping never invents ink
    assert sum(1 for i in range(3, len(kept.data), 4) if kept.data[i] > 0) \
        <= sum(1 for i in range(3, len(wash.data), 4) if wash.data[i] > 0)


def test_a_wet_brush_picks_up_the_colour_it_crosses():
    """**The essence of wet mixing, and it is a lerp rather than a physics simulation.** A loaded brush crossing a
    wet wash carries some of that wash with it, so the colour it deposits is part way between the paint it holds and
    the paint it found.

    The first version sampled its own buffer, which includes the dabs the stroke laid down a moment ago -- so a red
    brush crossing a blue wash picked up its own red and stayed red, a difference of one unit out of 255. That is why
    this asserts a sweep rather than a value: the failure was invisible to the eye and obvious to a measurement.
    """
    from lineweight import stroke_record
    from lineweight.raster import composite, stroke_layer

    wash = stroke_record([(30.0, 100.0), (390.0, 100.0)], 'wash', seed=1)
    wash['colour_int'] = (40, 80, 170)
    red = stroke_record([(210.0, 20.0), (210.0, 150.0)], 'ink', seed=2)
    red['colour_int'] = (190, 40, 50)

    def sample(pickup):
        under = stroke_layer(wash, 420, 200, 1.0)
        over = stroke_layer(red, 420, 200, 1.0, wet=pickup, under=under if pickup else None)
        out = composite(420, 200, [(under, 'normal', 1.0), (over, 'normal', 1.0)])
        index = (110 * 420 + 210) * 4
        return tuple(out.data[index:index + 3])

    dry = sample(0.0)
    blues = [sample(p)[2] for p in (0.0, 0.3, 0.6, 1.0)]
    assert blues == sorted(blues) and blues[-1] > blues[0] + 50, \
        'the brush is not picking up the wash: %s' % (blues,)
    assert sample(1.0)[2] > sample(0.0)[2], 'a fully wet brush should carry the underlying colour'
    assert dry[0] > 100, 'the dry brush should still be the colour it was loaded with: %s' % (dry,)


def test_grain_belongs_to_the_paper_and_not_to_the_stroke():
    """**Grain sampled by position rather than by dab index.** A texture indexed by how many dabs have been stamped
    makes the speckle travel with the brush, which reads as a moving pattern instead of a rough surface. The test is
    the property that distinguishes them: draw the same line in both directions and the tooth must land in the same
    places, because the paper did not move.
    """
    import statistics

    from lineweight import stroke_record
    from lineweight.raster import BRUSHES, grain_at, stroke_layer

    # deterministic, and it varies at the scale of a pixel
    assert grain_at(120.5, 80.0, 0) == grain_at(120.5, 80.0, 0)
    samples = [grain_at(x, 80.0, 0) for x in range(40, 60)]
    assert max(samples) - min(samples) > 0.3, 'the paper has no tooth: %s' % (samples,)

    record = stroke_record([(20.0, 80.0), (400.0, 80.0)], 'ink', seed=7)
    record['colour_int'] = (40, 34, 48)

    def sigma(grain):
        BRUSHES['ink']['grain'] = grain
        layer = stroke_layer(record, 420, 160, 1.0)
        return statistics.pstdev([layer.data[(80 * 420 + x) * 4 + 3] for x in range(40, 380)])

    smooth, rough = sigma(0.0), sigma(0.7)
    BRUSHES['ink']['grain'] = 0.0
    assert rough > smooth * 1.5, 'grain did not roughen the line: %.1f -> %.1f' % (smooth, rough)

    # and the tooth is a function of *where*, not of how the stroke got there -- which is now true by construction,
    # because the sample is the absolute pixel. What this can assert is the statistical effect, since a pixel's
    # alpha is the blend of every dab that covered it and cannot be reduced to one dab's factor.
    BRUSHES['ink']['grain'] = 0.7
    grained = stroke_layer(record, 420, 160, 1.0)
    BRUSHES['ink']['grain'] = 0.0
    plain = stroke_layer(record, 420, 160, 1.0)
    with_grain = [grained.data[(80 * 420 + x) * 4 + 3] for x in range(40, 380)]
    without = [plain.data[(80 * 420 + x) * 4 + 3] for x in range(40, 380)]
    assert statistics.mean(with_grain) < statistics.mean(without) * 0.98, \
        'grain did not thin the line: %.1f vs %.1f' % (statistics.mean(with_grain), statistics.mean(without))
    # every grained pixel sits below the ungrained one at the same place, because the paper only ever takes away
    assert all(g <= p + 1 for g, p in zip(with_grain, without)), 'some pixel gained ink from the paper'


def test_a_zero_mesh_warp_returns_the_layer_unchanged():
    """**The identity property, which is the one that catches a transposed axis or an off-by-one corner.** Warping is
    inverse sampling and the grid holds displacements, so a grid of zeroes must reproduce the input exactly -- and
    both of the mistakes it catches still produce a picture that looks like a picture, which is why this is asserted
    rather than eyeballed."""
    from lineweight import stroke_record
    from lineweight.raster import stroke_layer, warp

    record = stroke_record([(40.0, 60.0), (200.0, 120.0), (340.0, 70.0)], 'ink', seed=3)
    record['colour_int'] = (40, 34, 48)
    layer = stroke_layer(record, 200, 150, 1.0)

    rows, cols = 3, 3
    zero = [[(0.0, 0.0) for _ in range(cols)] for _ in range(rows)]
    same = warp(layer, zero, (0.0, 0.0, 199.0, 149.0))
    assert same.data == layer.data, 'a zero displacement grid changed the picture'

    # and a bulge actually moves ink: the top row pushed up spreads the mark further up the canvas
    bulge = [[(0.0, 0.0) for _ in range(cols)] for _ in range(rows)]
    bulge[0] = [(0.0, -18.0) for _ in range(cols)]
    warped = warp(layer, bulge, (0.0, 0.0, 199.0, 149.0))

    def top_row(l):
        for y in range(l.height):
            if any(l.data[(y * l.width + x) * 4 + 3] > 8 for x in range(l.width)):
                return y
        return -1

    assert top_row(warped) < top_row(layer), \
        'the bulge did not move the ink upward: %d vs %d' % (top_row(warped), top_row(layer))
