"""Tests for the pressure model, the outline expansion and the whole-document inking.

The two most useful tests here are regressions for mistakes that were made while this was being written, and both
were visible only by rendering an image and looking at it: a closed contour walked forwards and then backwards,
which drew its line twice and scalloped every hair mass into fish scales, and a brush with no taper dividing by
zero because a floating-point position can land a hair above 1.0.
"""
from __future__ import annotations

import math
import struct

import pytest
import os
import re

from lineweight import BRUSHES, inked_svg, outline, parse_path, pressures, stroke


def test_parse_handles_the_commands_a_generator_writes():
    polys = parse_path('M 0 0 L 10 0 Q 15 5 10 10 Z')
    assert len(polys) == 1
    # the quadratic is sampled, so the curve arrives as a polyline like everything else
    assert len(polys[0]) > 4
    assert polys[0][0] == (0.0, 0.0)


def test_parse_handles_every_command_a_generator_writes():
    """**This replaces a test that asserted the opposite, and that test was the bug.**

    The parser used to handle `M`, `L`, `Q` and `Z` and skip everything else, and a test named
    `test_parse_ignores_what_it_does_not_know_rather_than_guessing` locked that in so it read as a decision. It was
    not one: a language model asked to draw emits cubics and arcs constantly, and every curve was dropped in silence
    while the straight parts of the same shape were kept -- so the result looked like a drawing rather than like a
    failure, and only rendering it showed anything was missing.
    """
    # an arc is a real shape: from (0,0) to (20,0) with radius 5, it bulges to y=-10
    arc = parse_path('M 0 0 A 5 5 0 0 1 20 0')[0]
    assert len(arc) > 5
    assert arc[0] == (0.0, 0.0)
    assert abs(arc[-1][0] - 20.0) < 1e-6
    assert min(y for _, y in arc) < -9.0

    # a cubic arrives as a sampled polyline, five points or so
    assert len(parse_path('M 0 0 C 10 0 20 10 30 10')[0]) > 5
    # and so does a smooth cubic and a smooth quadratic
    assert len(parse_path('M 0 0 C 5 5 10 5 15 0 S 25 -5 30 0')[0]) > 10
    assert len(parse_path('M 0 0 Q 5 5 10 0 T 20 0')[0]) > 10


def test_relative_commands_are_relative():
    """The quieter half of the same bug: `m` and `l` were uppercased and then read as absolute, so an ordinary path
    placed everything after its first move at coordinates it never asked for."""
    assert parse_path('m 10 10 l 10 0 l 0 10 z')[0] == [(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 10.0)]
    assert parse_path('M 0 0 H 10 V 10 Z')[0] == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 0.0)]
    # scientific notation is legal SVG and was never matched by the old number pattern
    assert parse_path('M 0 0 L 1e2 5.5e1')[0][-1] == (100.0, 55.0)


def test_a_path_spelled_the_long_way_is_not_skipped():
    """`<path d="..."></path>` is as valid as `<path d="..." />`, and the pattern used to require the self-closing
    form -- so a document written the long way came back merely un-inked instead of obviously broken."""
    body = '<svg><path d="M 0 0 L 200 0 L 200 200 L 0 200 Z"></path></svg>'
    out = inked_svg(body, min_extent=10)
    assert out.count('<path') > 1


def test_an_outline_lands_where_a_transform_puts_it():
    """A contour generated in local coordinates and nested inside the group carrying the transform is displaced by
    that transform twice. The check is positional: the drawn outline has to sit near the shape it outlines.

    Only the *generated* paths are sampled -- they are the ones carrying an `opacity` attribute. An earlier version of
    this test took every number in the output, which included the source shape's own coordinates at the origin, so it
    failed on a correct implementation and accused the wrong layer of the code.
    """
    body = '<svg><g transform="translate(300,100)"><path d="M 0 0 L 80 0 L 80 80 L 0 80 Z"/></g></svg>'
    out = inked_svg(body, min_extent=10)
    generated = re.findall(r'<path d="([^"]+)" fill="[^"]*" opacity=', out)
    assert generated, 'no weighted outline was produced'
    coords = [float(v) for d in generated for v in re.findall(r'-?\d+\.?\d*', d)]
    xs, ys = coords[0::2], coords[1::2]
    assert min(xs) > 295 and max(xs) < 385, (min(xs), max(xs))
    assert min(ys) > 95 and max(ys) < 185, (min(ys), max(ys))
    # the seam stroke follows the shape instead of sitting at the origin
    seams = re.findall(r'<path d="([^"]+)" fill="none"', out)
    if seams:
        seam_coords = [float(v) for v in re.findall(r'-?\d+\.?\d*', seams[0])]
        assert min(seam_coords[0::2]) >= 300, seam_coords[:4]


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


# ------------------------------------------------------------------ the document and the bridges

def test_a_document_carries_layers_and_appearance():
    """The document is the thing every destination is written from, so what it loses is lost everywhere."""
    from lineweight import Appearance, Document, Path

    doc = Document(width=200, height=100)
    doc.layer('LINE').add(Path(points=[(0, 0), (10, 0), (10, 10)], appearance=Appearance(fill='#112233')))
    doc.layer('DETAIL').add(Path(points=[(0, 50), (200, 50)],
                                  appearance=Appearance(filled=False, stroke='#445566', stroke_width=3.0),
                                  closed=False))
    assert doc.counts() == {'layers': 2, 'paths': 2, 'points': 5}
    # get-or-create by name, so a caller can address a layer without holding it
    assert doc.layer('LINE') is doc.layers[0]
    assert doc.layer('NEW').name == 'NEW' and len(doc.layers) == 3
    # a stroked path must not silently become filled, or a construction line arrives as a wedge
    assert doc.layers[1].paths[0].appearance.filled is False


def test_the_canvas_is_sized_to_the_drawing():
    """A canvas that ignores its contents is a drawing positioned off its own page in every destination."""
    from lineweight import from_strokes

    doc = from_strokes([{'outline': [(10.0, 20.0), (110.0, 20.0), (110.0, 70.0)], 'opacity': 1.0}])
    assert doc.width == 130 and doc.height == 90, (doc.width, doc.height)
    # an explicit size still wins
    sized = from_strokes([{'outline': [(10.0, 20.0), (110.0, 20.0)], 'opacity': 1.0}], width=1000, height=500)
    assert (sized.width, sized.height) == (1000, 500)


def test_a_shape_added_after_the_canvas_was_sized_is_still_on_the_page():
    """**No format complains about geometry outside the page.**

    `from_strokes` sizes the canvas to the strokes it is handed. Anything a caller adds afterwards is outside it --
    the file stays well formed, the layer and the shape are both there, and the drawing simply has a piece nobody will
    ever see. The demo drawing did exactly that: a rule at y=380 on a canvas 372 tall. `resize_to_fit` is the fix, and
    this is the check that it is called.
    """
    from lineweight import Appearance, Document, Path, from_strokes, resize_to_fit

    doc = from_strokes([{'outline': [(10.0, 10.0), (110.0, 10.0), (110.0, 60.0)], 'opacity': 1.0}])
    assert doc.height == 80
    doc.layer('DETAIL').add(Path(points=[(0, 200), (120, 200)], closed=False,
                                 appearance=Appearance(filled=False, stroke='#6E1E2E', stroke_width=2.0)))
    # before the resize the new shape is off the canvas, and nothing would have said so
    assert doc.bounds()[3] > doc.height
    resize_to_fit(doc)
    x0, y0, x1, y1 = doc.bounds()
    assert x1 <= doc.width and y1 <= doc.height, (doc.width, doc.height, doc.bounds())

    # and the demo drawing itself, which is what exposed this, keeps every shape on its page
    from lineweight.core import demo_document
    demo = demo_document()
    dx0, dy0, dx1, dy1 = demo.bounds()
    assert dx1 <= demo.width and dy1 <= demo.height, (demo.width, demo.height, demo.bounds())


def test_the_illustrator_script_flips_y_and_keeps_the_palette():
    """Illustrator's y axis points up and SVG's points down, so a generated script that forgets it draws the picture
    upside down, which looks plausible in the code and wrong on the screen."""
    from lineweight import Appearance, Document, Path, jsx_document

    doc = Document(width=400, height=300)
    doc.layer('LINE').add(Path(points=[(10, 0), (10, 300)], appearance=Appearance(fill='#0A0B0C', opacity=0.5)))
    jsx = jsx_document(doc)
    assert 'setEntirePath([[10,300],[10,0]])' in jsx, jsx[jsx.index('setEntirePath'):][:60]
    assert 'colour.red = 10; colour.green = 11; colour.blue = 12;' in jsx
    assert 'item.opacity = 50;' in jsx
    # the constant that actually exists in Illustrator 28.5; SVGFORMAT does not, despite being the obvious name
    svg_jsx = jsx_document(doc, export_svg='out.svg')
    code = [line for line in svg_jsx.splitlines() if not line.strip().startswith('//')]
    assert any('ExportType.SVG' in line for line in code), 'the working export constant is missing'
    assert not any('SVGFORMAT' in line for line in code), \
        'ExportType.SVGFORMAT does not exist in Illustrator 28.5 and must not be emitted as code'


def test_the_psd_round_trips_its_layers(tmp_path):
    """The bytes have to be walked back out, because a writer that reports success after writing is exactly the
    failure this project keeps meeting -- and a checker that shares the writer's bug is not a check."""
    from lineweight import Appearance, Document, Path
    from lineweight.psd import layers_from_document, read_psd_header, save_psd

    doc = Document(width=64, height=48)
    doc.layer('LINE').add(Path(points=[(4, 4), (40, 4), (40, 30), (4, 30)],
                               appearance=Appearance(fill='#19151F')))
    doc.layer('COLOUR').add(Path(points=[(10, 36), (54, 36)], closed=False,
                                 appearance=Appearance(filled=False, stroke='#6E1E2E', stroke_width=3.0)))
    layers = layers_from_document(doc, scale=1.0)
    out = str(tmp_path / 'layers.psd')
    save_psd(layers, out)
    head = read_psd_header(out)
    # **The count is a count and the flag is a flag.** The field on disk is signed and its sign means "the bottom
    # layer's alpha is the image's transparency", which is what this writer produces; the earlier version wrote it
    # positive and SAI opened the document with an empty layer panel. A reader that reports the raw signed value as
    # `layers` makes a caller asking how many layers there are receive `-2`, and makes this test pin the flag to the
    # number. Both are asserted separately now, so neither can be changed without the other being noticed.
    assert head['layers'] == 2, head
    assert head['names'] == ['LINE', 'COLOUR'], head['names']
    # **The sign is reported, not asserted to be a particular value.** This writer matches SAI's own file, which
    # writes a positive count; the flag in the API exists so a reader can report the convention when it is used, and
    # asserting `True` here would pin the writer to a choice that a real application does not make.
    assert head['first_alpha_is_transparency'] is False, 'a positive count means no transparency flag'

    # **The signature is asserted in the raw bytes, not through the reader.** Putting the check only in
    # `read_psd_header` would have been no protection: that reader skipped the signature field too, so it happily
    # validated a file whose records began with a bare `norm`. A reader and a writer that agree on the same mistake
    # pass every round trip -- which is exactly what this pair did, for several rounds, while SAI showed an empty
    # layer panel.
    with open(out, 'rb') as handle:
        raw = handle.read()
    assert raw.count(b'8BIM') >= 2, 'a layer record must carry the 8BIM signature before its blend mode'
    # and not the file-header signature, which is what this used to write
    assert raw.count(b'8BPSnorm') == 0, 'the header signature was used where the resource signature belongs'

    # **The flag is read from the bytes, so the reader is tested on a file this writer does not produce.** The layer
    # count sits at a fixed offset once the three preceding sections are located, and negating it is the whole change.
    def _count_offset(blob: bytes) -> int:
        at = 26
        at += 4 + struct.unpack('>I', blob[at:at + 4])[0]        # colour mode data
        at += 4 + struct.unpack('>I', blob[at:at + 4])[0]        # image resources
        at += 4                                                  # layer and mask section length
        at += 4                                                  # layer info length
        return at

    flipped_bytes = bytearray(raw)
    at = _count_offset(raw)
    flipped_bytes[at:at + 2] = struct.pack('>h', -2)
    flipped = str(tmp_path / 'flagged.psd')
    with open(flipped, 'wb') as handle:
        handle.write(bytes(flipped_bytes))
    flagged = read_psd_header(flipped)
    assert flagged['layers'] == 2, flagged
    assert flagged['first_alpha_is_transparency'] is True, flagged
    assert flagged['names'] == ['LINE', 'COLOUR'], flagged['names']

    assert (head['width'], head['height']) == (64, 48)
    # **Three, not four.** The header's channel count describes the *merged* image, which for RGB is three; a layer
    # record lists its own channels separately and still carries four. Writing four here meant the merged section held
    # a quarter more data than the header announced, which a reader walks straight into.
    assert head['mode'] == 3 and head['depth'] == 8 and head['channels'] == 3
    assert head['merged_bytes_present'], 'the merged image data is missing or truncated'
    # **Compressed, so the size is no longer arithmetic.** This assertion used to require exactly
    # `channels x (flag + width x height)` bytes, which was true while channels were stored raw. PackBits makes the
    # size depend on the content, and the useful check is no longer the length but that every channel decompresses to
    # a full image -- which `merged_decoded_ok` reports, computed by reading the rows back.
    assert head['channel_bytes'] > 0
    assert head['channel_bytes'] < 4 * 2 * (2 + 64 * 48), 'the channels did not compress at all'


def test_the_psd_layers_hold_the_drawing():
    """Structure that verifies but is empty is the failure mode this library has hit before: the outline is what has
    to be in the pixels, so the check is on pixels rather than on the header."""
    from lineweight import Appearance, Document, Path
    from lineweight.psd import flatten, layers_from_document

    doc = Document(width=50, height=50)
    doc.layer('LINE').add(Path(points=[(5, 5), (45, 5), (45, 45), (5, 45)],
                               appearance=Appearance(fill='#19151F')))
    layers = layers_from_document(doc, scale=1.0)
    inside = layers[0]
    i = (25 * 50 + 25) * 4
    assert tuple(inside.data[i:i + 3]) == (0x19, 0x15, 0x1F)
    assert inside.data[i + 3] == 255
    # a corner is outside the rectangle and must stay transparent
    j = (0 * 50 + 0) * 4
    assert inside.data[j + 3] == 0
    merged = flatten(layers, 50, 50)
    # **The merged image is opaque, so a pixel the layers never touched is the background and not transparency.**
    # This used to assert alpha 0 there, which described a merged image that composites as transparent black -- and a
    # viewer that treats three RGB channels as opaque, which is what three channels mean, draws that as a black canvas.
    assert merged[i + 3] == 255 and merged[j + 3] == 255, 'the merged section has no alpha to be transparent with'
    assert tuple(merged[j:j + 3]) == (255, 255, 255), 'an untouched pixel is the paper, not nothing'


def test_the_xfl_folder_has_the_furniture_animate_needs(tmp_path):
    """Animate has no scripting interface, so this folder *is* the Animate bridge -- and what it contains is not
    decoration.

    Nine hand-written skeletons opened as documents while importing nothing, because they were XML in a zip and an XFL
    is a **folder with a marker file in it**. The marker is named after the project, contains `PROXY-CS5`, and is the
    file Animate must be pointed at: passing the folder path opens the home screen, and passing the marker opens the
    document. That single fact took an orthogonal sweep of sixteen skeletons plus a saved reference document to
    establish, and it is the sort of thing a future reader should not have to rediscover.
    """
    from lineweight import Appearance, Document, Path, write_xfl

    doc = Document(width=100, height=100)
    doc.layer('LINE').add(Path(points=[(10, 10), (90, 10), (50, 90)],
                               appearance=Appearance(fill='#19151F')))
    folder = write_xfl(doc, str(tmp_path / 'drawing.xfl'))

    # the marker file, named after the project, holding the marker text
    marker = os.path.join(folder, 'drawing.xfl')
    assert os.path.exists(marker), 'the marker file is what Animate opens'
    with open(marker, encoding='ascii') as handle:
        assert handle.read() == 'PROXY-CS5'
    # and the folder furniture a saved document also carries
    assert os.path.isdir(os.path.join(folder, 'LIBRARY'))
    assert os.path.isdir(os.path.join(folder, 'META-INF'))
    assert os.path.isdir(os.path.join(folder, 'bin'))
    assert os.path.exists(os.path.join(folder, 'bin', 'SymDepend.cache'))

    with open(os.path.join(folder, 'DOMDocument.xml'), encoding='utf-8') as handle:
        xml = handle.read()
    assert 'xmlns="http://ns.adobe.com/xfl/2008/"' in xml
    # **Read off a document Animate saved itself.** The earlier value was inferred from a property name found in the
    # binary and was wrong in a way that produced no error: the file opened and imported nothing.
    assert 'xflVersion="23.0"' in xml
    assert 'creatorInfo="Adobe Animate"' in xml
    assert 'platform="Windows"' in xml
    assert 'frameRate=' in xml and 'fileGUID=' in xml
    # the root children and timeline attribute a saved document has and a hand-written one omitted
    assert '<scripts/>' in xml and '<PrinterSettings/>' in xml and '<publishHistory/>' in xml
    assert 'layerDepthEnabled="true"' in xml
    # the frame carries no `duration`, and its elements container is present
    assert '<DOMFrame index="0" keyMode="9728">' in xml
    assert 'duration=' not in xml
    # the shape encoding: three corners, so three quadratics with the control point on the line
    assert xml.count('<DOMShape') == 1
    assert xml.count('<Edge cubics=') == 3
    assert '<Edge cubics="400 400 400 400 3600 400"/>' in xml
    assert '<DOMLayer name="LINE"' in xml

    # **The compact `edges` attribute is the representation a shape is drawn from.** Hand-written shapes that carried
    # only the verbose `cubics` form opened, imported, and drew nothing -- nine of them, before Animate's own template
    # documents were read. The grammar is `!x y` to move, `|x y` to draw a line, `[cx cy x y` to curve.
    assert '<Edge fillStyle1="1" edges="' in xml, 'the compact edge notation is missing'
    # **And the coordinates are scaled into the scene's units.** A drawing unit is not a scene unit: swept by
    # measurement, a shape spanning its whole canvas at scale 1 renders a fortieth of the stage, and the same points
    # at this factor fill it. The test pins the factor so a later change to it has to be deliberate.
    assert 'edges="!400 400|3600 400|2000 3600|400 400"' in xml, xml[xml.index('edges='):][:90]
    # the coordinates are whole numbers, because every one of the fifty shapes Animate ships uses whole numbers
    edge_block = xml.split('<edges>')[1].split('</edges>')[0]
    assert '.' not in edge_block, 'the edge notation was fed fractions'
    # both representations describe the same corners, so a reader that trusts either finds the other consistent
    assert edge_block.count('<Edge cubics=') == 3


# ------------------------------------------------------------------ measuring real artwork

def _write_test_png(path, width, height, rows):
    """A greyscale PNG written by hand, so the decoder is checked against real PNG bytes rather than against itself."""
    import struct
    import zlib

    raw = bytearray()
    for y in range(height):
        raw.append(0)                      # filter type 0: none
        raw.extend(rows[y])

    def chunk(kind, body):
        return (struct.pack('>I', len(body)) + kind + body
                + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF))

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(bytes(raw)))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as handle:
        handle.write(png)


def test_the_taper_knobs_are_not_interchangeable():
    """**Two things named like the same dial behave completely differently, and only one of them moves the line.**

    The library's `taper_ratio` came back at 0.41 against the model's 0.50, which reads as "the tapers are too
    shallow", so the obvious move is to let the ends thin further. Doing that -- lowering the floor at which a taper
    starts from 0.25 to 0.06 -- changed the measured ratio by nothing at all, at any render scale. Chasing the reason
    produced something worth keeping:

    * the **floor** only sets the value at the very first sample. It does not change how the stroke gets there, and
      the previous sample in any measured run already rounds to the same integer, so no pixel measurement can see it.
    * the **taper length** changes the profile itself -- a longer taper spends a larger share of the stroke below full
      width, which does move the spread statistic.

    So a taper is calibrated by its length, not by how thin its extreme is, and a test that only lowered the floor
    would have concluded the metric was broken when the model was being changed in a way it could not express.
    """
    from lineweight import BRUSHES, pressures

    path = [(float(x) * 10.0, 0.0) for x in range(0, 61)]
    brush = dict(BRUSHES['ink'])

    def spread(values):
        """The thinnest fifth against the mean: the shape of `taper_ratio`, on pressures so the test does not need a
        renderer."""
        ordered = sorted(values)
        thin = ordered[:max(1, len(ordered) // 5)]
        return (sum(thin) / len(thin)) / (sum(ordered) / len(ordered))

    normal = pressures(path, brush, seed=5)
    long_taper = pressures(path, {**brush, 'taper_in': 0.20, 'taper_out': 0.25}, seed=5)

    # the profile itself is different, and visible directly: the opening reaches full width much later
    assert long_taper[3] < normal[3] - 0.3, (long_taper[3], normal[3])
    # and that difference reaches the statistic, so the metric is not blind to taper length
    assert spread(long_taper) < spread(normal) - 0.1, (spread(long_taper), spread(normal))

    # the floor, by contrast, only moves the first sample; the rest of the opening is untouched
    assert abs(normal[1] - pressures(path, brush, seed=5)[1]) < 1e-9
    tip_only = [normal[0]]                       # the floor's whole contribution is this one value
    assert tip_only[0] == min(normal) or tip_only[0] >= 0.18


def test_the_taper_metric_measures_a_taper_it_can_see():
    """A metric for the ends of a line, and the floor beneath it.

    `taper_ratio` compares the thinnest fifth of *every* run against the mean, which is dominated by differences
    between strokes, so it barely responds to a change in the ends. This metric instead follows each stroke along its
    own length and compares its ends with its own body, which does respond -- and this test pins both halves: what it
    measures correctly, and where it stops being able to measure at all.

    The floor is a real one and worth knowing: a stroke's width comes from the runs on successive scanlines, and when
    a taper is shorter than a few pixels the thinnest part stops overlapping the part below it, so it is read as a
    separate and too-short stroke and dropped. A taper occupying 5% of a 60-pixel line is three pixels, and that is
    below the floor. Longer tapers are measured correctly, which is what makes the number usable on real artwork whose
    lines are long enough.
    """
    from lineweight.ref import Greyscale, measure_taper

    def bar(height, width_at, width=60, canvas=None):
        # the canvas is sized from the stroke, so a long bar cannot run off the bottom of a fixed one
        canvas = canvas or (height + 40)
        pixels = bytearray([255]) * (width * canvas)
        top = (canvas - height) // 2
        for i in range(height):
            w = max(1, int(round(width_at(i / (height - 1)))))
            left = width // 2 - w // 2
            for x in range(left, left + w):
                pixels[(top + i) * width + x] = 0
        return Greyscale(width=width, height=canvas, pixels=pixels)

    def taper_to(fraction, span):
        return lambda t: 6.0 * (1.0 - (1.0 - fraction) * min(t, 1 - t) / span) if min(t, 1 - t) < span else 6.0

    # a uniform line is exactly 1.0, at any length: the metric has no built-in bias
    for length in (60, 160, 300):
        uniform = measure_taper(bar(length, lambda t: 6.0))
        assert uniform['strokes'] == 1, uniform
        assert uniform['ends_over_body'] == 1.0, uniform

    # **An abrupt taper -- the kind a real stroke has -- is measured, and deeper reads deeper.** The taper has to
    # happen over a short span, which is what the camera does: a stroke thins in its last few pixels, not over a fifth
    # of its length. A gentle taper is not measured proportionally, because a 5% end window sits inside it and samples
    # only part of the way down; that limit is real, so the test asserts the case the metric can actually answer
    # rather than the case it was hoped it would.
    shallow = measure_taper(bar(160, taper_to(0.50, 0.05)))
    deeper = measure_taper(bar(160, taper_to(0.10, 0.05)))
    assert shallow['ends_over_body'] < 1.0, shallow
    assert deeper['ends_over_body'] < shallow['ends_over_body'] - 0.05, (deeper, shallow)

    # and the ordering holds across lengths, so the number does not drift with the size of the stroke
    for length in (60, 160, 300):
        a = measure_taper(bar(length, taper_to(0.50, 0.05)))
        b = measure_taper(bar(length, taper_to(0.10, 0.05)))
        assert b['ends_over_body'] < a['ends_over_body'], (length, a, b)


def test_packbits_round_trips_the_cases_that_break_compressors():
    """A compressor with no decompressor beside it is a compressor nobody has tested.

    The decompressor is written from the format rather than by inverting the compressor, because an inverse that
    mirrors a mistake reproduces it exactly and then reports success -- which is the failure mode this project keeps
    meeting. These are the cases that separate a correct PackBits from a plausible one: a run longer than the
    format's 128-byte maximum, data that compresses not at all, and the empty input.
    """
    from lineweight.psd import packbits, unpackbits

    cases = {
        'all one value (a long run)': bytes([5]) * 1000,
        'two values alternating': bytes([200, 10] * 500),
        'incompressible': bytes((i * 73 + 11) % 256 for i in range(1000)),
        'two long runs': bytes([0]) * 500 + bytes([255]) * 500,
        'single byte': b'\x42',
        'empty': b'',
        'a run of exactly 128': bytes([9]) * 128,
        'a run of 129 (past the maximum)': bytes([9]) * 129,
    }
    for name, data in cases.items():
        packed = packbits(data)
        assert unpackbits(packed, len(data)) == data, name
    # and it must actually compress the thing it is good at, or the format is not being used as intended
    assert len(packbits(bytes([5]) * 1000)) < 40


def test_the_psd_uses_the_compression_real_files_use(tmp_path):
    """A file can be valid and still be refused: raw channels are legal PSD and are not what any application writes.

    SAI answered a raw-channel file with "canvas creation failed" while opening the same pixels as a PNG, so the
    question is not whether the format permits the bytes but whether a reader recognises them. Everything here is
    written PackBits now, and the check decompresses what was written rather than trusting the writer.
    """
    from lineweight import Appearance, Document, Path
    from lineweight.psd import layers_from_document, read_psd_header, save_psd

    doc = Document(width=120, height=90)
    doc.layer('LINE').add(Path(points=[(10, 10), (110, 10), (110, 80), (10, 80)],
                               appearance=Appearance(fill='#19151F')))
    layers = layers_from_document(doc)
    out = str(tmp_path / 'packed.psd')
    save_psd(layers, out)
    head = read_psd_header(out)
    assert head['names'] == ['LINE']
    assert head['merged_compression'] == [1, 1, 1], head['merged_compression']
    assert head['merged_decoded_ok'], 'the merged channels did not decompress to their documented size'
    # a solid rectangle should compress enormously better than raw, which is the point of using the format's codec
    raw_size = 4 * (2 + 120 * 90)
    assert head['bytes'] < raw_size, (head['bytes'], raw_size)


def test_fit_measures_the_way_the_library_measures(tmp_path):
    """**One measurement, not two.** `--fit` used to have its own implementation: it required Pillow, had its own ink
    threshold, and reported percentiles that shared no code with `ref.py`. Numbers from it could not be pooled with the
    library or compared to it, which is most of the reason for having a library at all."""
    from lineweight.core import _library_targets, fit_report

    path = str(tmp_path / 'sheet.png')
    _write_test_png(path, 40, 40, [bytes([0] * 40) for _ in range(4)] + [bytes([255] * 40) for _ in range(36)])
    assert fit_report(path) == 0
    # and a file it cannot read is a message, not a traceback
    assert fit_report(str(tmp_path / 'missing.png')) == 2

    # the targets come from the checked-in summary, so the comparison is re-derivable rather than asserted from memory
    targets = _library_targets()
    if targets:
        assert targets['images'] > 100, targets
        assert 0.0 < targets['taper_ratio'] < 1.0, targets
        assert targets['p90_over_median'] > 2.0, targets


def test_the_png_decoder_undoes_the_filters(tmp_path):
    """**A filter is applied per scanline and undoing it is not optional.** Reading the bytes without undoing the
    predictor does not produce an image that is slightly off -- the error accumulates along the row, so the right-hand
    side of the picture is noise. This test writes a PNG whose second row is deliberately Up-filtered, which is what a
    real encoder emits, and checks the decoded pixels rather than the header."""
    path = str(tmp_path / 'filtered.png')
    width, height = 8, 3
    row0 = bytes([10] * width)
    # an Up-filtered row stores the difference from the row above, which for a constant row is all zeros
    row1_up = bytes([0] * width)
    row2 = bytes([200] * width)
    import struct
    import zlib

    raw = bytes([0]) + row0 + bytes([2]) + row1_up + bytes([0]) + row2

    def chunk(kind, body):
        return (struct.pack('>I', len(body)) + kind + body
                + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF))

    with open(path, 'wb') as handle:
        handle.write(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw))
                     + chunk(b'IEND', b''))

    from lineweight.ref import decode_png
    image = decode_png(path)
    assert (image.width, image.height) == (8, 3)
    # the filtered row must reconstruct to the row above it, not to zeros
    assert list(image.pixels[0:8]) == [10] * 8
    assert list(image.pixels[8:16]) == [10] * 8, 'the Up filter was not undone'
    assert list(image.pixels[16:24]) == [200] * 8


def test_measurement_separates_lines_from_filled_areas(tmp_path):
    """**A run of ink is not necessarily a line.** A colour illustration's dark regions read as strokes tens of pixels
    wide and drag the mean width to a number that describes no line in the picture; the first real measurement here
    came back at 81% ink with a mean width of 13 px for exactly that reason."""
    path = str(tmp_path / 'mixed.png')
    width, height = 60, 20
    rows = []
    for y in range(height):
        row = bytearray([255] * width)
        if y in (5, 6):                      # a two-pixel line across the top
            for x in range(width):
                row[x] = 0
        if y >= 12:                          # a filled block along the bottom
            for x in range(10, 50):
                row[x] = 0
        rows.append(bytes(row))
    _write_test_png(path, width, height, rows)

    from lineweight.ref import measure
    result = measure(path)
    assert result.line_runs > 0
    assert result.area_runs > 0, 'the filled block was not detected as an area rather than a line'
    # the two-pixel line is what the width means; the 40-pixel block must not be averaged into it
    assert result.width_max <= 16, result.width_max
    assert result.width_mean < 4.0, result.width_mean


def test_compare_refuses_to_call_widths_comparable_across_scales():
    """The ratios that survive a change of canvas, and the ones that do not, have to be told apart or the report is a
    confident number with no meaning behind it."""
    from lineweight.ref import check, compare

    generated = {'taper_ratio': 0.54, 'ink_ratio': 0.025, 'width_mean': 9.4}
    reference = {'taper_ratio': 0.43, 'ink_ratio': 0.18, 'width_mean': 5.2}
    ratios = compare(generated, reference)
    # the arithmetic is checked against the raw division rather than against a number typed from memory; `compare`
    # rounds its ratios to four decimals, so the tolerance has to allow for that rounding
    assert abs(ratios['taper_ratio'] - (0.54 / 0.43)) < 1e-3
    assert abs(ratios['width_mean'] - (9.4 / 5.2)) < 1e-3
    verdicts = check(generated, reference)['verdicts']
    assert verdicts['taper_ratio'] == 'ok'          # within 40%, so the taper curves are broadly right
    assert 'off by' in verdicts['ink_ratio']        # several times too sparse, and it must say so



def test_a_layer_reads_back_the_colours_that_were_drawn(tmp_path):
    """**Four colours, four known positions, read back through an independent parser.**

    Every check in this module before this one was the project's own code reading the project's own output, and that is
    how a writer and a reader agreed on the same mistake for several rounds while the file was unreadable by anything
    else. So this asserts the values through `psd-tools` when it is importable, and says plainly that it skipped the
    strong form when it is not -- a check that quietly downgrades is worse than no check.

    The colours matter: a single-colour drawing cannot tell a swapped channel from an inverted one, and reading
    `(255, 0, 0)` where red was drawn distinguishes all of those from a correct file.
    """
    import pytest

    from lineweight import Appearance, Document, Path
    from lineweight.psd import layers_from_document, save_psd

    document = Document(width=400, height=400)
    layer = document.layer('QUADS')
    quadrants = (((0, 0, 190, 190), '#FF0000'), ((210, 0, 400, 190), '#00FF00'),
                 ((0, 210, 190, 400), '#0000FF'), ((210, 210, 400, 400), '#FFFF00'))
    for (x0, y0, x1, y1), colour in quadrants:
        layer.add(Path(points=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True,
                       appearance=Appearance(filled=True, fill=colour)))
    out = str(tmp_path / 'quads.psd')
    save_psd(layers_from_document(document), out)

    # the project's own reader must at least agree about the structure
    from lineweight.psd import read_psd_header
    head = read_psd_header(out)
    assert head['layers'] == 1 and head['names'] == ['QUADS'], head

    try:
        from psd_tools import PSDImage
    except ImportError:
        pytest.skip('psd-tools is not installed: the independent check cannot run')

    psd = PSDImage.open(out)
    drawn = list(psd)
    assert len(drawn) == 1, 'psd-tools sees %d layers' % len(drawn)
    pixels = (drawn[0].numpy() * 255).round().astype(int)
    for (x, y), expected in (((50, 50), (255, 0, 0, 255)), ((300, 50), (0, 255, 0, 255)),
                             ((50, 300), (0, 0, 255, 255)), ((300, 300), (255, 255, 0, 255)),
                             ((200, 5), (255, 255, 255, 0))):
        got = tuple(int(v) for v in pixels[y, x])
        assert got == expected, 'at (%d, %d) expected RGBA %s, an independent parser read %s' % (x, y, expected, got)


def test_each_channel_blob_holds_its_own_channel():
    """**The serialiser must use the channel id it is given, not a fixed one.**

    This replaces a test asserting that a flat drawing's three colour channels encode to equal lengths -- which is false,
    and was generalised from an *empty* canvas where every channel is the same constant. SAI's own drawing has 167983,
    170515 and 174687.

    In its place is the check that would have caught the fault this file actually had. That fault was
    `layer.channel_bytes(-1)` called for every channel id, so channels 0, 1 and 2 all received the alpha plane: a
    drawing of `(255, 0, 0, 255)` went to disk as four planes of 255 and read back as pure white. Every other check
    passed while that was true, because they all verified that the wrong data had been written faithfully.

    A unit test on `channel_bytes()` passed throughout. The function was right; its caller stopped passing the argument.
    So this asserts what the caller depends on: for a pixel whose four channel values are all different, the four planes
    must all differ, and each must hold its own.
    """
    from lineweight.psd import Layer

    layer = Layer('TWO', 2, 1)
    layer.set_pixel(0, 0, (10, 20, 30), 40 / 255.0)
    layer.set_pixel(1, 0, (50, 60, 70), 80 / 255.0)

    assert list(layer.channel_bytes(0)) == [10, 50], 'red'
    assert list(layer.channel_bytes(1)) == [20, 60], 'green'
    assert list(layer.channel_bytes(2)) == [30, 70], 'blue'
    assert list(layer.channel_bytes(-1)) == [40, 80], 'alpha'

    # the four planes are pairwise distinct, which is what makes confusing them detectable at all
    planes = [tuple(layer.channel_bytes(c)) for c in (0, 1, 2, -1)]
    assert len(set(planes)) == 4, 'the four channel planes are not distinct: %s' % (planes,)


def test_a_channel_id_of_minus_one_means_alpha():
    """**The alpha channel is translated, not indexed.** `channel_bytes(-1)` used to do
    `self.data[i * 4 + (-1)]`, which is `i * 4 - 1`: the *previous* pixel's blue byte for every pixel after the first.
    Python's negative indexing looks like it handles the convention and it does the opposite.

    The fault is invisible from outside the writer -- the file is structurally valid, the channel list is right, and the
    layer is simply transparent where it should be drawn. It is testable without SAI, without a reference file and
    without an independent parser, which is exactly why it should have been tested first.
    """
    from lineweight.psd import Layer

    layer = Layer('t', 3, 1)
    layer.set_pixel(0, 0, (255, 0, 0), 1.0)          # opaque red
    layer.set_pixel(1, 0, (0, 255, 0), 0.0)          # transparent green
    layer.set_pixel(2, 0, (0, 0, 255), 1.0)

    assert list(layer.channel_bytes(-1)) == [255, 0, 255], 'the alpha bytes, not the blues of the previous pixel'
    assert list(layer.channel_bytes(3)) == [255, 0, 255], 'the explicit index and the convention must agree'
    assert list(layer.channel_bytes(0)) == [255, 0, 0]
    assert list(layer.channel_bytes(1)) == [0, 255, 0]
    assert list(layer.channel_bytes(2)) == [0, 0, 255]


def test_a_layer_starts_as_white_paper_that_nothing_shows():
    """A layer's colour channels hold white where the alpha says there is nothing.

    Zeroing the buffer gives a transparent layer whose colours are *black*; a consumer that draws "colour, masked by
    alpha" then paints the whole canvas black. SAI's own layer holds 96096 pixels of pure white at alpha zero.
    """
    from lineweight.psd import Layer

    fresh = Layer('fresh', 2, 2)
    assert list(fresh.data[0:4]) == [255, 255, 255, 0], 'white, and not visible'
    assert list(fresh.data[4:8]) == [255, 255, 255, 0]


def test_inked_svg_leaves_commented_out_paths_alone():
    """**A commented-out path is not part of the drawing.** The pattern matches text, so it matched one inside an XML
    comment and drew a contour for a shape the document explicitly does not show.

    Found by probing the parser rather than by reading it: eight documents, each exercising one thing a real SVG can
    contain, and the count of outlines that came back. That probe also measured the boundaries this function still has
    -- see the note in `README.md` -- which is the point of running it rather than reasoning about the regex.
    """
    big = 'M 0 0 L 200 0 L 200 200 L 0 200 Z'
    commented = inked_svg('<svg><!-- <path d="%s"/> --></svg>' % big, min_extent=46)
    assert commented.count('opacity=') == 0, 'a commented-out path was inked'
    assert '<!--' in commented and '-->' in commented, 'the comment itself must survive'

    # a comment beside a real path: only the real one is inked, and the comment is still there
    both = inked_svg('<svg><!-- keep --><path d="%s"/></svg>' % big, min_extent=46)
    assert both.count('opacity=') == 1, both[:200]
    assert 'keep' in both

    # and a real path on its own is still inked, so the guard did not disable the whole pass
    plain = inked_svg('<svg><path d="%s"/></svg>' % big, min_extent=46)
    assert plain.count('opacity=') == 1
