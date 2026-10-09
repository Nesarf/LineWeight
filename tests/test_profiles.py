"""Tests for the per-stroke style record: the four knobs pressure decomposes into, made expressible.

In a tablet application pen pressure moves **width** (the dominant effect), **opacity**, **dab spacing** and a little
**colour jitter**. A record that can only express the first cannot stand in for the hand, which is the whole reason
this library exists. These tests are about the two that were missing -- an explicit width profile and an alpha
profile -- and about the rule that decides whether adding a field was worth anything at all: **a field the renderer
ignores is a comment.**
"""

import pytest

from lineweight import Project, raster, save_project, load_project
from lineweight.core import (BRUSHES, collapses_alpha, record_opacity, stroke_record, stroke_widths)


def a_stroke(**extra):
    return stroke_record([(20, 60), (90, 30), (160, 80), (230, 40)], 'ink', seed=11, **extra)


def a_layer(record, width=260, height=120):
    """The raster renderer's own view of a record, so the renderer is what is being tested rather than a helper."""
    return raster.stroke_layer({'brush': record['brush'], 'centre': record['centre'],
                                'pressure': record['pressure'], 'seed': record.get('seed', 0),
                                'width_profile': record.get('width_profile') or [],
                                'alpha_profile': record.get('alpha_profile') or [],
                                'colour_int': (26, 26, 26)}, width, height, 1.0)


def ink_and_shape(layer):
    """Ink as alpha summed over pixels, and the number of pixels touched at all.

    **Two numbers because the two profiles move different ones**, and a test that only measured one of them could not
    tell an alpha profile from a width profile -- which is the mistake this pair exists to make impossible.
    """
    data = layer.data
    return sum(data[3::4]) / 255.0, sum(1 for i in range(3, len(data), 4) if data[i] > 0)


# ------------------------------------------------------------------------------ absent means the old behaviour

def test_absent_profiles_are_exactly_the_old_behaviour():
    """The compatibility guarantee, and the reason both fields default to empty rather than to a computed list.

    Every project file written before these fields existed has neither. If "absent" meant "fill in the derived
    values" the expansion would be the same but the file would claim a caller had supplied something they never
    mentioned -- the same trap as defaulting a missing role to `contour`.
    """
    record = a_stroke()
    assert record['width_profile'] == []
    assert record['alpha_profile'] == []
    brush = BRUSHES['ink']
    expected = [brush['width'] * (p ** brush['curve']) for p in record['pressure']]
    assert stroke_widths(record) == pytest.approx(expected)
    mean_p = sum(record['pressure']) / len(record['pressure'])
    assert record_opacity(record) == pytest.approx(brush['opacity'] * (0.55 + 0.45 * mean_p))
    assert not collapses_alpha(record)


# -------------------------------------------------------------------------------------- the width profile

def test_a_width_profile_replaces_the_derived_one():
    """A supplied profile is used as given, which is what lets a *measured* profile land here.

    `ref.py` measures width distributions out of real artwork, and the brush table is per-brush -- so without this
    field a per-stroke measurement has nowhere to go except a table that cannot hold it.
    """
    record = a_stroke()
    n = len(record['pressure'])
    flat = dict(record, width_profile=[6.0] * n)
    assert stroke_widths(flat) == pytest.approx([6.0] * n)
    assert stroke_widths(flat) != pytest.approx(stroke_widths(record))

    doubled = dict(record, width_profile=[12.0] * n)
    assert sum(stroke_widths(doubled)) == pytest.approx(2 * sum(stroke_widths(flat)))

    # and it reaches the picture, not just the accessor
    plain_ink, plain_shape = ink_and_shape(a_layer(record))
    wide_ink, wide_shape = ink_and_shape(a_layer(doubled))
    assert wide_shape > plain_shape * 1.5, 'the width profile did not reach the renderer'


def test_a_role_still_rescales_a_supplied_profile():
    """**The second pass has to reach the strokes that need it most.**

    A measured or hand-authored profile is the one a caller cares about, so the role's multiplier is applied *to* it
    rather than being overridden by it. The alternative -- role ignored when a profile is present -- would make
    assigning `silhouette` a no-op on exactly the lines the hierarchy is about.
    """
    from lineweight import roles

    record = a_stroke(width_profile=[4.0] * len(a_stroke()['pressure']))
    plain = stroke_widths(record)
    heavy = stroke_widths(dict(record, role='silhouette'))
    assert heavy == pytest.approx([w * roles.ROLES['silhouette'].width for w in plain])


# -------------------------------------------------------------------------------------- the alpha profile

def test_an_alpha_profile_changes_opacity_and_leaves_the_shape_alone():
    """**The signature that distinguishes it from a width profile**, asserted as the pair of numbers.

    An alpha profile must move the ink and *not* the touched-pixel count: a stroke that fades is the same shape, only
    lighter somewhere. Measuring one number alone would let a width change pass as an alpha change, which is exactly
    how a field ends up being read by nobody and noticed by nobody.
    """
    record = a_stroke()
    n = len(record['pressure'])
    plain_ink, plain_shape = ink_and_shape(a_layer(record))

    fading = dict(record, alpha_profile=[1.0 - 0.8 * i / (n - 1) for i in range(n)])
    fade_ink, fade_shape = ink_and_shape(a_layer(fading))
    # **Within a percent, not exactly.** The faintest rim pixels of a fading stroke round to an alpha of zero and
    # stop counting as painted -- three pixels of 1236 here. That is a rounding effect at the bottom of the range and
    # not a shape change; asserting equality would be asserting the rounding.
    assert abs(fade_shape - plain_shape) <= plain_shape * 0.01, 'an alpha profile changed the shape'
    assert fade_ink < plain_ink * 0.9, 'the alpha profile did not reach the renderer'

    rising = dict(record, alpha_profile=[0.2 + 0.8 * i / (n - 1) for i in range(n)])
    rise_ink, rise_shape = ink_and_shape(a_layer(rising))
    assert abs(rise_shape - plain_shape) <= plain_shape * 0.01
    assert rise_ink != pytest.approx(fade_ink), 'a fade and a rise rendered identically'


def test_the_brush_opacity_is_still_the_medium():
    """The profile is the stroke's opacity along its length; the brush's opacity is what the medium is.

    A wash at 0.35 with a full profile is still a wash. If the profile replaced the brush's opacity instead of
    scaling it, writing an alpha profile would silently turn every wash into an ink line.
    """
    record = stroke_record([(20, 60), (90, 30), (160, 80)], 'wash', seed=3)
    full = dict(record, alpha_profile=[1.0] * len(record['pressure']))
    assert BRUSHES['wash']['opacity'] < 0.5
    # the exact statement: a full profile times the medium's opacity is the medium's opacity
    assert record_opacity(full) == pytest.approx(BRUSHES['wash']['opacity'])
    ink, _ = ink_and_shape(a_layer(full))
    plain, _ = ink_and_shape(a_layer(record))
    assert ink > plain, 'the profile should raise a wash toward its medium opacity'
    assert ink < plain * 3.0, 'a full alpha profile overwhelmed the wash'


# ------------------------------------------------------------------- the vector export, and what it cannot carry

def test_a_varying_alpha_is_collapsed_by_the_vector_export_and_that_is_detectable():
    """**SVG cannot carry a variable alpha any more than it can carry a variable width.**

    A filled path takes one `fill-opacity` and there is no way to vary it along a curve; the width becomes an outline
    because of that, and this cannot become anything. So the vector export uses the profile's mean -- and
    `collapses_alpha` is the detectable form of the loss, because a caller who wrote a fade and got a flat export
    back would otherwise have no way to tell that from a fade too subtle to see.
    """
    record = a_stroke()
    n = len(record['pressure'])
    assert not collapses_alpha(record)

    fading = dict(record, alpha_profile=[1.0 - 0.8 * i / (n - 1) for i in range(n)])
    assert collapses_alpha(fading)
    # the mean of the profile, times the medium's opacity -- ink's is 1.0 so the profile's mean is the whole story
    assert record_opacity(fading) == pytest.approx(sum(fading['alpha_profile']) / n)
    # the mean is what a flat profile of the same average would give -- the export is not wrong, it is lossy
    flat = dict(record, alpha_profile=[record_opacity(fading)] * n)
    assert record_opacity(flat) == pytest.approx(record_opacity(fading))

    # a constant profile is not a loss and must not be reported as one
    constant = dict(record, alpha_profile=[0.5] * n)
    assert not collapses_alpha(constant)
    assert record_opacity(constant) == pytest.approx(0.5)


# ---------------------------------------------------------------------------------------- through the document

def test_both_profiles_survive_the_project_file(tmp_path):
    """They are document content, so they round-trip -- including the empty case, which must stay empty."""
    n = len(a_stroke()['pressure'])
    project = Project(width=300, height=140)
    project.add_stroke(a_stroke())
    project.add_stroke(a_stroke(width_profile=[4.0] * n,
                                alpha_profile=[1.0 - i / (n - 1) for i in range(n)]))
    path = str(tmp_path / 'profiles.json')
    save_project(project, path)
    again = load_project(path)

    plain, profiled = again.by_id('m0001'), again.by_id('m0002')
    assert plain.geometry['width_profile'] == []
    assert plain.geometry['alpha_profile'] == []
    assert profiled.geometry['width_profile'] == pytest.approx([4.0] * n)
    assert len(profiled.geometry['alpha_profile']) == n
    assert collapses_alpha(profiled.geometry)
    assert stroke_widths(profiled.geometry) == pytest.approx([4.0] * n)
