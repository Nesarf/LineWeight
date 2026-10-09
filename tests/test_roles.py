"""Tests for the line-role model.

The model's job is to make a line's *purpose* a thing the document carries, so that the hierarchy a drawing needs is
something the caller states rather than something the widths happen to be. Most of these tests are therefore about the
two properties that keep it honest: **a role must not be able to change anything silently**, and **the trade it makes
must be printed rather than implied**.
"""

import colorsys
import random

import pytest

from lineweight import Project, save_project, load_project
from lineweight import roles
from lineweight.core import BRUSHES, mark_ink, stroke_record, stroke_widths


def a_drawing(mix, strokes=60, seed=5):
    """A drawing whose role mix is stated as a ratio, so a test can ask about a plausible drawing."""
    rng = random.Random(seed)
    names = [name for name, weight in mix.items() for _ in range(weight)]
    samples = []
    for i in range(strokes):
        control = [(rng.uniform(0, 700), rng.uniform(0, 500))]
        for _ in range(rng.randint(3, 5)):
            control.append((control[-1][0] + rng.uniform(-80, 80), control[-1][1] + rng.uniform(-60, 60)))
        samples.extend(stroke_widths(stroke_record(control, 'ink', seed=i, role=names[i % len(names)])))
    ordered = sorted(samples)
    return ordered, ordered[len(ordered) // 2]


# ------------------------------------------------------------------------------- a role must not change anything silently

def test_no_role_changes_nothing():
    """The compatibility guarantee, and the reason the missing role is not simply `contour`.

    Every project file written before roles existed has no role on its marks. Defaulting that to a real role would
    rescale every stroke in every one of them -- and `contour` happens to be exactly 1.0, so it would look as though
    nothing had happened while the record claimed something it never said.
    """
    assert roles.width_scale('') == 1.0
    assert roles.ink('') == roles.DEFAULT_INK
    assert roles.trade('') == 'no role: the brush width exactly as given, no trade declared'
    control = [(0, 0), (50, 10), (100, 0)]
    plain = stroke_record(control, 'ink', seed=1)
    assert plain['role'] == ''
    assert stroke_widths(plain) == stroke_widths(stroke_record(control, 'ink', seed=1, role=''))
    # and the widths are exactly what the brush and the pressure model say, with no factor in between
    brush = BRUSHES['ink']
    expected = [brush['width'] * (p ** brush['curve']) for p in plain['pressure']]
    assert stroke_widths(plain) == pytest.approx(expected)


def test_a_role_scales_the_profile_without_changing_its_shape():
    """**A role multiplies the width profile; it does not replace it.**

    This is the line the model must not cross. The whole point of this library is that a line has weight variation --
    the drawing convention names forgetting it on hair as the recurring failure -- so a role that flattened the
    profile would be removing the thing the project exists to produce. Scaling keeps `max/min` exactly, which is what
    "the same line, drawn heavier" means.
    """
    control = [(20, 60), (90, 30), (160, 80), (230, 40)]
    plain = stroke_widths(stroke_record(control, 'ink', seed=11))
    for name in roles.names():
        scaled = stroke_widths(stroke_record(control, 'ink', seed=11, role=name))
        factor = roles.width_scale(name)
        assert scaled == pytest.approx([w * factor for w in plain])
        assert max(scaled) / min(scaled) == pytest.approx(max(plain) / min(plain))


def test_an_unknown_role_is_refused_and_the_message_names_the_known_ones():
    """A typo must not produce a drawing. The name is the claim being made about the line, so guessing at it would
    mean the drawing silently says something the caller did not."""
    with pytest.raises(ValueError) as caught:
        roles.role('outline')
    message = str(caught.value)
    assert 'outline' in message
    for name in roles.names():
        assert name in message, 'the error should list %r as available' % name


def test_roles_are_data_and_adding_one_is_adding_a_row():
    """The registry is a dict of rows, and nothing in the code branches on a role's name.

    The P0-2 lesson applied to content: build the mechanism, not a hardcoded set. A caller with a fifth kind of line
    -- ベタ fill edges, speed lines -- adds a row and gets width, ink, the report and the trade for free.
    """
    added = roles.ROLES['__test_role__'] if '__test_role__' in roles.ROLES else None
    try:
        roles.ROLES['__test_role__'] = roles.Role('__test_role__', '試験', '--', 1.5, '#123456',
                                                  'a test, not a measurement', 'buys nothing, costs nothing')
        assert roles.width_scale('__test_role__') == 1.5
        assert roles.ink('__test_role__') == '#123456'
        assert '__test_role__' in roles.names()
        widths = stroke_widths(stroke_record([(0, 0), (50, 10)], 'ink', seed=1, role='__test_role__'))
        plain = stroke_widths(stroke_record([(0, 0), (50, 10)], 'ink', seed=1))
        assert widths == pytest.approx([w * 1.5 for w in plain])
    finally:
        roles.ROLES.pop('__test_role__', None)
        assert added is None


# ------------------------------------------------------------------------------------------------ the measured axis

def test_the_measured_axis_separates_a_brown_from_a_red():
    """**The colour test has to be saturation, and this is why.**

    KEER2014 measured reddish-brown as *positive* on naturalness and red as *negative*. They are about twenty-five
    degrees apart in hue, so a hue test -- the obvious implementation, and the one this project would reach for by
    habit -- puts them on the same side and reports the exact opposite of the finding. What separates them is
    saturation: 0.07 against 0.31.
    """
    brown, red = roles.ROLES['silhouette'].ink, '#6E1E2E'
    hue_brown = colorsys.rgb_to_hsv(*(int(brown.lstrip('#')[i:i + 2], 16) / 255.0 for i in (0, 2, 4)))[0]
    hue_red = colorsys.rgb_to_hsv(*(int(red.lstrip('#')[i:i + 2], 16) / 255.0 for i in (0, 2, 4)))[0]
    degrees = abs(hue_brown - hue_red) * 360.0
    assert min(degrees, 360.0 - degrees) < 40.0, 'these are meant to be close in hue for the test to mean anything'
    assert roles.chroma(brown) * 3 < roles.chroma(red)
    assert roles.measured_natural(brown) and not roles.measured_natural(red)


def test_black_is_positive_and_the_three_saturated_hues_are_not():
    """The rest of the measured axis, including the part that is easy to get backwards: black scored positive."""
    assert roles.measured_natural('#000000')
    assert roles.measured_natural('#1A1620'), 'the library\'s own default ink'
    for name, colour in (('green', '#00FF00'), ('blue', '#0000FF'), ('red', '#FF0000')):
        assert not roles.measured_natural(colour), '%s scored negative on naturalness' % name
    assert 'NEGATIVE' in roles.ink_verdict('#FF0000')
    assert 'positive' in roles.ink_verdict('#000000')


def test_every_role_ink_is_on_the_measured_positive_side():
    """A role whose default ink scored negative would be the model contradicting its own evidence."""
    for name in roles.names():
        assert roles.measured_natural(roles.ROLES[name].ink), \
            '%s is drawn in %s, which is not on the measured axis' % (name, roles.ROLES[name].ink)


# ------------------------------------------------------------------------------------------------- the magnitudes

def test_the_role_widths_sit_inside_the_corpus_envelope():
    """**The numbers come from the corpus, and the test says which ones.**

    `silhouette` is the corpus's own p90/median, because in a finished drawing the p90 *is* the outer contour. The
    full spread across roles has to stay inside the corpus's max/median, or the model would claim a dynamic range no
    real drawing has. The two middle roles are a *placement rule* rather than a measurement, and the module says so.
    """
    widths = [roles.ROLES[name].width for name in roles.names()]
    assert roles.ROLES['silhouette'].width == roles.WIDTH_P90_OVER_MEDIAN
    assert roles.ROLES['contour'].width == 1.0, 'the anchor is the brush width, which is the corpus median line'
    assert max(widths) / min(widths) <= roles.WIDTH_MAX_OVER_MEDIAN
    # `shadow` and `detail` are placed geometrically either side of the anchor
    step = roles.ROLES['shadow'].width
    assert roles.ROLES['detail'].width == pytest.approx(1.0 / step)


def test_a_drawing_with_a_plausible_role_mix_lands_near_the_corpus_ratio():
    """The end-to-end claim, and the one that could have failed.

    A drawing that is mostly interior lines with a minority of contour -- which is what a face is -- should come out
    near the corpus's p90/median of 2.75. It does, at 2.73, and **that is a coincidence worth not leaning on**: the
    library reached 2.67 with no roles at all, so the role multipliers are adding to a ratio already near target, and
    the check that matters is the report on a real drawing rather than this number.

    The other half of the test is the negative control: with no roles the same drawing is flat, at about 1.07. If that
    were also near 2.75 then this test would be measuring the pressure model and not the roles.
    """
    flat, flat_median = a_drawing({'': 1})
    assert flat[int(0.9 * (len(flat) - 1))] / flat_median < 1.5, 'a drawing with no roles should have no width spread'
    mixed, median = a_drawing({'contour': 30, 'silhouette': 40, 'shadow': 10, 'detail': 20})
    ratio = mixed[int(0.9 * (len(mixed) - 1))] / median
    assert 2.0 < ratio < 3.5, 'a face-like role mix came out at p90/median %.2f' % ratio


def test_a_drawing_that_overshoots_is_visible_rather_than_prevented():
    """The model reports a bad role assignment; it does not refuse one.

    Putting every stroke in `silhouette` is a real choice -- it is the chibi/sticker look, and the drawing convention
    says so explicitly rather than treating it as a mistake. What must not happen is that it is *silent*, which is why
    `--roles` prints the drawing's own ratios beside the corpus reference.
    """
    all_heavy, median = a_drawing({'silhouette': 1})
    assert all_heavy[int(0.9 * (len(all_heavy) - 1))] / median < 1.5, \
        'one role for every stroke is uniform, so it must not read as spread'
    # the spread only appears when roles differ, and that is the quantity the report puts beside the corpus
    mixed, mixed_median = a_drawing({'contour': 10, 'silhouette': 10})
    assert mixed[int(0.9 * (len(mixed) - 1))] / mixed_median > 2.0


# ---------------------------------------------------------------------------------------- through the document

def test_a_role_and_its_ink_survive_the_project_file(tmp_path):
    """The role is document content, so it has to round-trip -- and the ink it brought with it."""
    project = Project(width=200, height=200)
    project.add_stroke(stroke_record([(10, 10), (100, 40), (180, 20)], 'ink', seed=1, role='silhouette'))
    project.add_stroke(stroke_record([(10, 60), (100, 90), (180, 70)], 'ink', seed=2, role='detail'))
    path = str(tmp_path / 'roles.json')
    save_project(project, path)
    again = load_project(path)
    assert [m.geometry.get('role') for m in again.live()] == ['silhouette', 'detail']
    # **The ink is not written down when it was only defaulted.** An absent colour is the answer "the role decides",
    # and storing the resolved colour instead is what would make a later role assignment silently not change the ink.
    for mark_id, name in (('m0001', 'silhouette'), ('m0002', 'detail')):
        mark = again.by_id(mark_id)
        assert 'colour' not in mark.appearance
        assert mark_ink(mark.to_dict()) == roles.ROLES[name].ink


def test_the_role_supplies_the_ink_and_an_explicit_colour_wins():
    """**This was broken and the report is what caught it.**

    `stroke_record`'s colour parameter defaulted to a literal, so resolving `colour or role_ink(role)` never reached
    the role: every mark in a four-role drawing came back `#1A1620` and the per-role ink column was identical four
    times. A default that is always present makes the fallback after it dead code.
    """
    control = [(0, 0), (50, 10), (100, 0)]
    project = Project(width=200, height=200)
    project.add_stroke(stroke_record(control, 'ink', seed=1, role='silhouette'))
    project.add_stroke(stroke_record(control, 'ink', seed=2, role='silhouette', colour='#123456'))

    implicit, explicit = project.by_id('m0001'), project.by_id('m0002')
    assert 'colour' not in implicit.appearance, 'a defaulted ink must not be written down'
    assert mark_ink(implicit.to_dict()) == roles.ROLES['silhouette'].ink
    assert explicit.appearance['colour'] == '#123456', "a chosen colour is the mark's own"

    # and the difference is exactly what a later role assignment acts on
    for mark in (implicit, explicit):
        project.assign_role(mark.id, 'detail')
    assert mark_ink(project.by_id('m0001').to_dict()) == roles.ROLES['detail'].ink
    assert mark_ink(project.by_id('m0002').to_dict()) == '#123456', (
        'an explicitly chosen colour must not be overwritten by a role')


def test_the_report_is_reachable_and_prints_the_trade():
    """`--roles` is the model examining itself, so it has to run on a real project rather than on a dict."""
    import io
    import contextlib
    from lineweight.core import roles_report

    project = Project(width=200, height=200)
    project.add_stroke(stroke_record([(10, 10), (100, 40), (180, 20)], 'ink', seed=1, role='silhouette'))
    project.add_stroke(stroke_record([(10, 60), (100, 90), (180, 70)], 'ink', seed=2, role='contour'))
    import tempfile
    import os
    handle, path = tempfile.mkstemp(suffix='.json')
    os.close(handle)
    try:
        save_project(project, path)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert roles_report(path) == 0
        text = buffer.getvalue()
    finally:
        os.unlink(path)
    assert 'silhouette' in text and 'contour' in text
    assert 'potency' in text and 'naturalness' in text, 'the trade must be printed, not implied'
    assert '%.2f' % roles.WIDTH_P90_OVER_MEDIAN in text, 'the corpus reference must be beside the drawing\'s ratio'
    assert 'outer/inner' in text, 'the checklist item this model exists to answer'
