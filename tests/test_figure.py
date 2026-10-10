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


# ------------------------------------------------------------------------------------------------------------
# The figure carries the colour specification, because the production hands the three over together.

def test_a_figure_carries_the_colour_specification_for_its_parts():
    """J.C.STAFF's 仕上げ department describes a 色指定表 naming the colour *"for each character part and each
    shadow"*, and Ghibli's diary has the animator draw the boundary and the colour designer specify what goes inside
    it. So the specification belongs to the character, not to the drawing."""
    from lineweight import cel
    f = figure.standard()
    assert f.palettes == {}, 'nothing is specified until someone specifies it'
    assert f.shadow_steps == 1
    f.palettes['face'] = cel.Palette(lit=(240, 225, 215), shades=[(190, 180, 205)])
    assert f.errors() == [], f.errors()


def test_the_step_count_is_the_works_and_the_shades_are_the_parts_and_they_must_agree():
    """**The check that makes the two worth having together.** A figure drawn in two bands whose face carries one
    shade would leave the second band with nothing to paint, and that is caught here rather than at the first missing
    colour."""
    from lineweight import cel
    f = figure.standard()
    f.palettes['face'] = cel.Palette(lit=(240, 225, 215), shades=[(190, 180, 205)])
    f.shadow_steps = 2
    problems = f.errors()
    assert any('the face has 1 shade(s) and the figure is drawn in 2 band(s)' in p for p in problems), problems


def test_a_shadowless_work_and_a_part_with_shades_are_inconsistent():
    """影無し is an ordinary production choice, so declaring it is legal -- and a palette with shades under it is
    then a contradiction rather than a preference."""
    from lineweight import cel
    f = figure.standard()
    f.shadow_steps = 0
    f.palettes['face'] = cel.Palette(lit=(240, 225, 215), shades=[(190, 180, 205)])
    problems = f.errors()
    assert any('has shades but the figure is 影無し' in p for p in problems), problems

    bare = figure.standard()
    bare.shadow_steps = 0
    bare.palettes['face'] = cel.Palette(lit=(240, 225, 215))
    assert bare.errors() == [], bare.errors()


def test_a_part_outside_the_vocabulary_is_refused():
    from lineweight import cel
    f = figure.standard()
    f.palettes['tail'] = cel.Palette(lit=(1, 2, 3))
    assert any('is not a part' in p for p in f.errors()), f.errors()


def test_the_palette_is_looked_up_through_the_class_to_material_mapping():
    """**A drawing has twenty-one draw classes and a colour specification has eight parts.** `back_hair` and
    `front_hair` are one material, `eye` and `mouth` are another -- so a layer's colour is its part's, not its own,
    and asking for one by draw class has to go through the mapping."""
    from lineweight import cel
    f = figure.standard()
    f.palettes['hair'] = cel.Palette(lit=(200, 180, 160), shades=[(150, 140, 165)])
    assert f.palette_for_class('back_hair') is f.palettes['hair']
    assert f.palette_for_class('front_hair') is f.palettes['hair']
    assert f.palette_for_class('torso') is None, 'the body has no palette in this figure'
    assert f.palette_for_class('scenery') is None, 'a scene element belongs to no part'


def test_the_specification_survives_a_round_trip():
    from lineweight import cel
    f = figure.standard()
    f.shadow_steps = 2
    f.palettes['face'] = cel.Palette(lit=(240, 225, 215), shades=[(190, 180, 205), (150, 145, 170)])
    f.palettes['hair'] = cel.Palette(lit=(200, 180, 160), shades=[(150, 140, 165), (110, 105, 130)])
    back = figure.Figure.from_dict(f.to_dict())
    assert back.shadow_steps == 2
    assert sorted(back.palettes) == ['face', 'hair']
    assert back.palettes['face'].colour_for(2) == (150, 145, 170)
    assert back.errors() == [], back.errors()
