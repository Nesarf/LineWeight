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
