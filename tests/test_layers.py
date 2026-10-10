"""The layering of a drawing, as an ordered list that can be checked.

Layering is a property of an order, and the rig states its order because Spine stores slots in draw order. So the
checks here are the ones an order makes possible: a tier in the wrong place, a part with no outline, and a cast
shadow drawn after the thing casting it.
"""

import pytest

from lineweight import layers


def a_good_stack():
    s = layers.Stack()
    s.add('bg', 'background')
    s.add('blossom', 'scenery')
    s.add('handkerchief.shadow', 'cast_shadow', casts_for='handkerchief')
    s.add('handkerchief', 'character', part='prop')
    s.add('prop.outline', 'character')
    s.add('torso', 'character', part='body')
    s.add('sweat', 'overlay', part='')
    return s


def test_a_well_ordered_stack_has_no_errors():
    assert layers.layer_errors(a_good_stack()) == []


def test_the_tier_order_is_the_rigs_own():
    """Background, scenery, the painting's cast shadows, the character, then overlays -- which is the order the
    Spine slots are actually stored in."""
    assert layers.TIERS == ('background', 'scenery', 'cast_shadow', 'character', 'overlay')


def test_scenery_drawn_over_the_character_is_caught():
    s = a_good_stack()
    s.add('foreground_branch', 'scenery')          # a scenery layer above the character
    problems = layers.layer_errors(s)
    assert any('foreground_branch is scenery but comes after' in p for p in problems), problems


def test_a_shadow_drawn_after_its_caster_is_caught():
    """**Measured rather than assumed**: in the rig the shadow is the lower slot, so a stack that darkens the
    handkerchief *after* drawing it is built the other way round from the art."""
    s = layers.Stack()
    s.add('handkerchief', 'character', part='prop')
    s.add('handkerchief.shadow', 'cast_shadow', casts_for='handkerchief')
    problems = layers.layer_errors(s)
    assert any('drawn after handkerchief' in p for p in problems), problems


def test_a_part_drawn_without_its_line_is_caught():
    """**An attribute rather than a layer, and getting that wrong is why this test says what it says.**

    The first version of this module modelled the outline as an extra `<part>.outline` layer, because the material
    carries `_OutlineTint`. Building the standard figure showed the error: **the 2D rig's 174 slots contain no
    `*_Outline` slot at all** and the 3D asset has **`_OutlineTex` = 0 across the corpus**. The line is what a part is
    drawn *with* -- painted into each slot's own artwork in 2D, a parameter per material in 3D -- so it is an attribute
    here, and a part drawn without it is a part the art does not have.
    """
    s = layers.Stack()
    s.add('torso', 'character', part='body', outline=True)
    assert layers.layer_errors(s) == [], layers.layer_errors(s)

    s2 = layers.Stack()
    s2.add('torso', 'character', part='body', outline=False)
    problems = layers.layer_errors(s2)
    assert any('drawn without an outline' in p for p in problems), problems


def test_a_part_split_across_tiers_is_caught():
    """A part drawn in two places is what makes a drawing come apart when something moves."""
    s = a_good_stack()
    # the hair is already drawn on the character; this draws it *again* in the scenery tier
    s.layers.insert(1, layers.Layer('front_hair', 'character', part='hair'))
    s.add('hair_again', 'scenery', part='hair')
    problems = layers.layer_errors(s)
    assert any('the hair is drawn in 2 tiers' in p for p in problems), problems


def test_an_unknown_tier_is_refused_rather_than_ignored():
    with pytest.raises(ValueError) as caught:
        layers.Stack().add('mystery', 'midground')
    assert 'unknown tier' in str(caught.value)
    assert 'scenery' in str(caught.value)


def test_every_part_the_asset_has_is_in_the_vocabulary():
    """The eight parts are the 3D asset's material list, so a part outside it is a part with no evidence."""
    assert 'eye_mouth' in layers.PARTS, 'the asset gives the eyes and mouth their own material'
    assert set(layers.OUTLINED) == set(layers.PARTS)


def test_the_order_the_nine_rigs_agree_on_is_satisfied_by_the_derived_order():
    """**Derived rather than written out.** `standard_order()` is topologically sorted from `ORDER_CONSTRAINTS`, so it
    cannot drift from them: a constraint added there changes the order, and constraints that contradict each other
    raise rather than quietly producing an order that breaks one."""
    order = layers.standard_order()
    index = {c: i for i, c in enumerate(order)}
    broken = [(a, b) for a, b in layers.ORDER_CONSTRAINTS if a in index and b in index and index[a] > index[b]]
    assert broken == [], broken


def test_the_halo_is_drawn_behind_the_character():
    """**A fact this project did not have**, and it is the same halo that inflated every bounding box attempted
    earlier. `halo` before `back_hair`, `collar`, `leg` and `skirt` in every rig that has both."""
    order = layers.standard_order()
    for after in ('back_hair', 'collar', 'leg', 'skirt'):
        assert order.index('halo') < order.index(after), after


def test_hair_is_two_layers_and_the_back_one_is_behind():
    """A material is `hair`; a drawing has `back_hair` and `front_hair` at opposite ends of the stack, which is what
    makes hair read as hair rather than as one shape."""
    order = layers.standard_order()
    assert order.index('back_hair') < order.index('front_hair')
    assert order.index('back_hair') < order.index('torso')
    assert order.index('frontal' if False else 'front_hair') > order.index('face')


def test_moving_a_layer_breaks_specific_constraints_and_names_them():
    """The check has to bite, and its message has to say which pair is the wrong way round.

    **The first version of this check did nothing at all and said nothing**: it keyed layers by their material, so
    `back_hair` and `front_hair` both indexed as `hair`, `setdefault` kept the first, and every hair constraint
    compared a layer with itself. Moving the back hair to the top reported no violation.
    """
    from lineweight import figure
    f = figure.standard()
    assert layers.order_errors(f.layers) == []
    f.layers.layers.append(f.layers.layers.pop(4))          # back_hair to the very top
    problems = layers.order_errors(f.layers)
    # **The expectation follows the constraint set, and the set has been rebuilt twice.** It was 99 pairs from nine
    # rigs, then 73, and now the pairs that co-occurred in ten or more rigs and agreed in ninety per cent of them. A
    # test asserting particular violations here is asserting the table, so it asserts the shape instead: something is
    # caught, and the message names both layers.
    assert problems, 'moving the back hair to the top broke nothing'
    assert all('back_hair' in p and 'the rigs draw it before' in p for p in problems), problems


def test_the_draw_vocabulary_is_finer_than_the_material_one():
    """Eight materials against twenty-one draw classes, and the mapping between them is data rather than a guess."""
    assert len(layers.PARTS) == 8
    assert len(layers.DRAW_CLASSES) == 21
    assert layers.PART_OF_CLASS['back_hair'] == 'hair'
    assert layers.PART_OF_CLASS['front_hair'] == 'hair'
    assert layers.PART_OF_CLASS['eye'] == 'eye_mouth'
    assert layers.PART_OF_CLASS['mouth'] == 'eye_mouth'
    assert layers.PART_OF_CLASS['torso'] == 'body'


def test_every_constraint_carries_its_sample_and_its_rate():
    """**The numbers are the claim.** A pair is kept only if it co-occurred in ten or more rigs and went the same way
    in ninety per cent of them, and both numbers are in the data rather than in a comment."""
    for pair in layers.ORDER_CONSTRAINTS:
        rigs, rate = layers.ORDER_EVIDENCE[pair]
        assert rigs >= layers.MIN_RIGS, pair
        assert rate >= layers.MIN_RATE, pair
    assert len(layers.ORDER_CONSTRAINTS) == 46


def test_the_failure_bucket_is_not_a_class():
    """**`other` is the classifier's failure bucket, not a kind of thing**, so nothing may be constrained against it.
    It appeared in six of the fifty-two majority pairs, and those six were dropped.

    **And leaving an unknown class in the set is not harmless**: the sort could never place anything that had to come
    after it, so `eyebrow` -- which had `other` and `hair` among its predecessors -- was pushed to the very end, past
    the overlays. `hair` was a real class the vocabulary was missing and is now in `DRAW_CLASSES`; `other` is not."""
    sides = {c for pair in layers.ORDER_CONSTRAINTS for c in pair}
    assert 'other' not in sides
    assert sides <= set(layers.DRAW_CLASSES), sorted(sides - set(layers.DRAW_CLASSES))


def test_one_total_order_satisfies_all_of_them_and_puts_the_overlays_last():
    """`unsatisfiable()` is worth having even when it returns nothing: an earlier version of the sort raised
    `ValueError` claiming the constraints contradict each other, and that was a bug in the sort, not in the data."""
    assert layers.unsatisfiable() == []
    order = layers.standard_order()
    assert order[-1] == 'overlay', 'the tier rule is seeded in, so overlays come last'
    assert order[0] == 'background'
    assert order.index('eye') < order.index('face') < order.index('eyebrow')


def test_the_halo_is_drawn_behind_the_character():
    """**A fact this project did not have**, and it is the same halo that inflated every bounding box attempted
    earlier. The evidence is in the data: the rigs place it before the character, and by how much."""
    order = layers.standard_order()
    assert order.index('halo') < order.index('back_hair')
    assert order.index('halo') < order.index('torso')
    assert layers.ORDER_EVIDENCE.get(('halo', 'neck'), (0, 0))[1] >= 0.9


def test_hair_is_two_layers_and_the_back_one_is_behind():
    """A material is `hair`; a drawing has `back_hair` and `front_hair` at opposite ends of the stack."""
    order = layers.standard_order()
    assert order.index('back_hair') < order.index('front_hair')
    assert order.index('back_hair') < order.index('torso')
    assert order.index('front_hair') > order.index('face')
