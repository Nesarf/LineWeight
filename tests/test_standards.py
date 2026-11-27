"""One place that answers "is this stroke right", at three sizes.

The criteria were scattered: `core.is_uniform` knew a stroke's width variation, `invariants.check` knew a layer's
invariants, `learn/errors.jsonl` held ten seen mistakes, and the face's three-division/five-eye ratios lived inside the
script that drew the face. The last one is the reason this module exists: **a criterion that lives in the script that
uses it is not a criterion**, because the next subject needs it retyped and the retyped copy drifts.

These tests are about the answers and about the delegation. `standards` is not allowed to reimplement what
`invariants` and `core` already do -- two implementations drift, and this library has paid for that lesson twice.
"""
from __future__ import annotations

import pytest

from lineweight import core, standards


def a_flat_stroke():
    """**A record whose profile is one value throughout**, written by hand rather than taken from a brush.

    A brush's own pressure model tapers at the ends, so a stroke made with one is not flat even when nobody asked for
    variation -- which is the behaviour the library wants and not what this test is about.
    """
    return {'brush': 'ink', 'centre': [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)],
            'pressure': [1.0, 1.0, 1.0], 'width_profile': [5.0, 5.0, 5.0], 'seed': 1}


def a_varied_stroke():
    return core.stroke_record([(0.0, 0.0), (100.0, 40.0), (200.0, 0.0)], 'brush', seed=2,
                              width_profile=[2.0, 14.0, 3.0])


def test_a_flat_stroke_fails_the_variation_test():
    finding = standards.line(a_flat_stroke())
    assert finding.ok is False, 'a line with one width is the failure this library exists to prevent'
    assert finding.measured == pytest.approx(1.0, abs=1e-6)


def test_a_stroke_with_a_profile_passes_it():
    finding = standards.line(a_varied_stroke())
    assert finding.ok is True
    assert 0.0 < finding.measured < standards.UNIFORM_FLOOR


def test_a_record_with_no_widths_cannot_be_measured():
    """`ok is None` is not `ok is False`: a stroke nobody measured has not failed, it has not been checked."""
    finding = standards.line({})
    assert finding.ok is None
    assert finding.measured is None


def test_the_floor_is_the_one_the_library_already_used():
    assert standards.UNIFORM_FLOOR == core.UNIFORM_FLOOR == 0.95


def test_a_finding_prints_as_a_line_with_its_number_and_its_rule():
    text = standards.line(a_varied_stroke()).line()
    assert 'stroke variation' in text
    assert 'ok' in text


def test_the_face_ratios_put_the_eyes_below_the_centre_and_five_across():
    ratios = standards.face(250.0, 252.0)
    assert ratios['eye_dy'] < 0, 'the eyes sit below the crown/chin midpoint, not above it'
    assert ratios['eye_width'] == pytest.approx(2.0 * 250.0 * 0.80 / 5.0)
    assert ratios['eye_height'] == pytest.approx(ratios['eye_width'] * 0.34)
    assert ratios['eye_dx'] == pytest.approx(ratios['eye_width']), 'two eyes are one eye apart'


def test_five_eyes_across_the_visible_width():
    """The rule itself, stated as something a test can check rather than as a comment: five eye widths fill the face
    and two of them are the gap between the eyes."""
    ratios = standards.face(200.0, 240.0)
    assert 5.0 * ratios['eye_width'] == pytest.approx(ratios['visible_width'])
    assert ratios['eye_dx'] + 2.0 * ratios['eye_width'] == pytest.approx(3.0 * ratios['eye_width'])


def test_the_three_divisions_are_equal_and_the_mouth_sits_in_the_lower_third():
    """The three divisions as three measurable spans: hairline to brow, brow to nose, nose to chin are equal, and the
    mouth falls in the **upper** third of the last one -- so the space below it is twice the space above it.

    This is the criterion the mouth line is now derived from instead of placed by eye. Before it, `mouth_marks` wrote
    the mouth at 0.52 half-heights; 三停 puts it at 0.447, eighteen pixels higher on this face."""
    ratios = standards.face(250.0, 252.0)
    hairline, brow, nose, chin = (ratios['hairline_y'], ratios['brow_y'],
                                  ratios['nose_y'], ratios['chin_y'])
    assert brow - hairline == pytest.approx(nose - brow)
    assert nose - brow == pytest.approx(chin - nose)
    assert ratios['mouth_y'] - nose == pytest.approx((chin - nose) / 3.0)
    assert chin - ratios['mouth_y'] == pytest.approx(2.0 * (chin - nose) / 3.0)


def test_the_face_lines_come_down_in_one_order():
    """The sign convention written as an assertion: y grows downward, so hairline < brow < eyes < nose < mouth < chin.

    `eye_dy` sits between the brow line and the nose line, which is the only claim this makes about the eyes -- the
    eyes are not on a three-division line, they are below the brow line.
    """
    ratios = standards.face(250.0, 252.0)
    order = [ratios['hairline_y'], ratios['brow_y'], ratios['eye_dy'], ratios['nose_y'],
             ratios['mouth_y'], ratios['chin_y']]
    assert order == sorted(order)
    assert len(set(order)) == len(order)


def test_the_mouth_is_not_the_middle_of_the_lower_division():
    """The distinction that makes the mouth line worth deriving rather than half-waying: it is above the midpoint, so
    "halfway between nose and chin" is a different face, not a rounding of the same one."""
    ratios = standards.face(250.0, 252.0)
    middle = (ratios['nose_y'] + ratios['chin_y']) / 2.0
    assert ratios['mouth_y'] < middle


def test_the_hairline_is_a_parameter_because_three_equal_divisions_need_it():
    """Without a hairline the three divisions start at the crown and nothing divides equally; the parameter exists so
    that the crown and the hairline cannot be the same point by accident.

    A hairline lower on the face shortens all three divisions, which lifts the nose line and the mouth with it -- so
    the parameter is load-bearing rather than decorative.
    """
    default = standards.face(250.0, 252.0)
    lower = standards.face(250.0, 252.0, hairline=-0.60)
    assert lower['hairline_y'] == pytest.approx(252.0 * -0.60)
    assert lower['brow_y'] > default['brow_y']
    assert lower['nose_y'] > default['nose_y']
    assert lower['mouth_y'] > default['mouth_y']


def test_the_known_mistakes_come_from_the_library_that_holds_them():
    from lineweight import aesthetic

    assert standards.known() == aesthetic.errors()
    assert len(standards.known()) == 10


def test_a_stage_check_is_delegated_rather_than_reimplemented():
    from lineweight import invariants

    stage = {'role': 'line', 'invariants': [{'measure': 'coverage', 'op': '<', 'value': 0.9}]}
    current = {'coverage': 0.5, 'luminance': 0.2, 'saturation': 0.1, 'warmth': 0.1,
               'band_ref': 0.1, 'band_dark': 0.05}
    mine = standards.stage(stage, current)
    theirs = invariants.check(stage, current)
    assert [(f.name, f.ok) for f in mine] == [(f.name, f.ok) for f in theirs]


def test_the_thresholds_are_readable_without_going_into_core():
    values = standards.values()
    assert values['uniform_floor'] == standards.UNIFORM_FLOOR
    assert 'coverage' in values['measures']
