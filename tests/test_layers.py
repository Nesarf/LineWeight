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
    s.add('body', 'character', part='body')
    s.add('body.outline', 'character')
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
    s.add('prop.outline', 'character')
    s.add('handkerchief.shadow', 'cast_shadow', casts_for='handkerchief')
    problems = layers.layer_errors(s)
    assert any('drawn after handkerchief' in p for p in problems), problems


def test_a_part_without_an_outline_is_caught():
    """Every material in the 3D asset carries `_OutlineTint`, so an outlined part is not optional."""
    s = layers.Stack()
    s.add('body', 'character', part='body')
    problems = layers.layer_errors(s)
    assert any('the body has no outline layer' in p for p in problems), problems


def test_a_part_split_across_tiers_is_caught():
    """A part drawn in two places is what makes a drawing come apart when something moves."""
    s = a_good_stack()
    # the hair is already drawn on the character; this draws it *again* in the scenery tier
    s.layers.insert(1, layers.Layer('hair', 'character', part='hair'))
    s.layers.insert(2, layers.Layer('hair.outline', 'character'))
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
