"""A described figure, validated before anything is drawn.

This is the path the whole body-and-layers line exists for: **describe a body, check it, and only then draw.** The
headline case is the one this project started from -- a figure with three arms must not be drawable.
"""

import json

import pytest

from lineweight import body, figure
from lineweight.core import stroke_record
from lineweight.project import Project, load_project, save_project


def a_record():
    return stroke_record([(10, 10), (100, 100)], 'ink', seed=1)


def test_the_standard_figure_is_valid():
    f = figure.standard()
    assert f.errors() == [], f.errors()
    assert len(f.joints) == 34
    assert f.layer_names(), 'a figure with a body needs somewhere to be drawn'


def test_a_figure_with_three_arms_cannot_be_declared():
    """**The headline case, and the reason this module exists.** A generator that draws a third arm has no
    representation in which that is wrong; here it has one, and the drawing does not start."""
    f = figure.standard()
    f.joints['Bip001 L UpperArm2'] = 'Bip001 Spine1'
    project = Project()
    with pytest.raises(ValueError) as caught:
        project.set_figure(f)
    assert 'cannot be drawn on' in str(caught.value)
    assert 'extra limb' in str(caught.value)
    assert project.figure is None, 'an invalid figure must not be stored'


def test_a_body_with_nowhere_to_be_drawn_is_refused():
    """The other half: a correct body wearing nothing is not a drawable figure either. Refused at declaration rather
    than surfacing as "no such layer" on the first stroke, because that would describe the symptom."""
    f = figure.Figure(joints=dict(body.JOINT_PARENT), name='bare')
    assert any('no layers to draw it in' in p for p in f.errors())
    with pytest.raises(ValueError) as caught:
        Project().set_figure(f)
    assert 'no layers to draw it in' in str(caught.value)


def test_a_declared_figure_makes_every_mark_name_its_layer():
    p = Project()
    p.set_figure(figure.standard())
    # **The layer names are the drawing's own vocabulary, not the materials':** a material is `hair`, a drawing has
    # `back_hair` and `front_hair` drawn at opposite ends of the stack. The tests said `body` until the standard
    # figure started being built from the census, and then they were naming a layer that no longer exists.
    mark = p.add_stroke(a_record(), layer='torso')
    assert mark.layer == 'torso'
    with pytest.raises(ValueError) as caught:
        p.add_stroke(a_record())
    assert 'must name its layer' in str(caught.value)
    with pytest.raises(ValueError) as caught:
        p.add_stroke(a_record(), layer='somewhere')
    assert 'no such layer' in str(caught.value)


def test_a_project_with_no_figure_still_draws_the_way_it_always_did():
    """**Every project file written before this existed has no figure**, and none of them may start failing."""
    p = Project()
    mark = p.add_stroke(a_record())
    assert mark.layer == ''
    assert p.figure is None


def test_the_figure_and_the_layers_survive_a_round_trip(tmp_path):
    p = Project()
    p.set_figure(figure.standard())
    p.add_stroke(a_record(), layer='torso')
    p.add_stroke(a_record(), layer='front_hair')
    path = str(tmp_path / 'p.json')
    save_project(p, path)
    back = load_project(path)
    assert back.figure is not None
    assert back.figure.name == 'standard'
    assert back.figure.layer_names() == p.figure.layer_names()
    assert [m.layer for m in back.marks] == ['torso', 'front_hair']


def test_the_error_report_says_which_limb_kind_is_wrong():
    """A person reading the refusal should not have to count bones."""
    f = figure.standard()
    f.joints['Bip001 R Clavicle2'] = 'Bip001 Spine1'
    text = figure.describe(f)
    assert 'problem' in text
    assert 'extra limb' in text
    assert 'body:' in text and 'arm' in text


def test_the_limb_counts_summarise_the_body():
    counts = figure.standard().limb_counts()
    # **Read off `kind()` rather than assumed**: a toe is its own kind, so the legs are six bones and the toes two,
    # and the axis is four (Bip001, Pelvis, Spine, Spine1) rather than three. The first version of this test counted
    # toes as legs and the axis as three, and was simply wrong about a table it had not read.
    assert counts == {'arm': 8, 'leg': 6, 'toe': 2, 'finger': 12, 'head': 2, 'axis': 4}, counts
    assert sum(counts.values()) == 34


def test_what_the_drawing_actually_used_is_reported():
    p = Project()
    p.set_figure(figure.standard())
    p.add_stroke(a_record(), layer='torso')
    p.add_stroke(a_record(), layer='torso')
    p.add_stroke(a_record(), layer='front_hair')
    assert p.layers_in_use() == {'torso': 2, 'front_hair': 1}
