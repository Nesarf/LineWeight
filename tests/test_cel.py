"""Cel shading: the quantiser, with the art's own numbers.

Cel is not a shading model, it is a *quantisation* of one -- and the two things a quantiser needs, where the step
sits and how hard it is, are in the materials. These tests hold the constants to the measurement and the quantiser to
being a step.
"""

import pytest

from lineweight import cel


def test_the_constants_are_the_corpus_mode_not_a_taste():
    """`_LightValue` is 0.5 in 40 of the bundles that have it, `_ShadowStrong` and `_LightStrong` are 10.0."""
    assert cel.LIGHT_VALUE == 0.5
    assert cel.SHADOW_STRONG == 10.0
    assert cel.LIGHT_STRONG == 10.0
    assert cel.BASE_BRIGHTNESS == 0.0
    assert cel.SPEC_STRONG == 0.1


def test_the_corpus_hardness_is_a_step():
    """**Why this art is cel-shaded and not soft-shaded**: a strong of ten is a hard ramp, so a value either side of
    the threshold comes out at an end and not in between."""
    # **The transition is 1/hardness wide**, which at the corpus's ten is +/-0.05 about the threshold -- so the
    # ends of the range are exactly 0 and 1 and the middle tenth is not. The first version of this test asserted
    # 0.49 was already 1.0, which is inside the crossfade and was simply wrong about its own constant.
    assert cel.ramp(0.30) == 1.0
    assert cel.ramp(0.44) == 1.0
    assert cel.ramp(0.56) == 0.0
    assert cel.ramp(0.80) == 0.0
    assert cel.ramp(0.0) == 1.0 and cel.ramp(1.0) == 0.0
    assert 0.0 < cel.ramp(0.49) < 1.0, 'the crossfade is a tenth wide, not zero' 


def test_the_crossfade_is_as_wide_as_the_hardness_says_and_no_wider():
    """**Not a true step**, because a true step aliases wherever the value crosses it and every renderer here
    anti-aliases. The width is `1/hardness` in the units of the value, and it is the one thing a caller may vary."""
    soft = cel.Shading(shadow_strong=2.0)
    assert soft.shade(0.5) == pytest.approx(0.5)
    assert 0.0 < soft.shade(0.6) < 1.0, 'a soft ramp should have a visible transition'
    assert cel.ramp(0.5, hardness=2.0) == pytest.approx(0.5)
    assert cel.ramp(0.5, hardness=10.0) == pytest.approx(0.5)
    # the transition narrows as the hardness rises
    def width(h):
        xs = [i / 1000.0 for i in range(1001)]
        inside = [x for x in xs if 0.0 < cel.ramp(x, hardness=h) < 1.0]
        return max(inside) - min(inside) if inside else 0.0
    assert width(2.0) > width(10.0) > width(50.0)


def test_a_zero_hardness_is_refused_rather_than_silently_a_step():
    with pytest.raises(ValueError) as caught:
        cel.ramp(0.5, hardness=0.0)
    assert 'positive' in str(caught.value)


def test_quantise_and_levels():
    field = [0.1, 0.4, 0.6, 0.9]
    assert cel.quantise(field) == [1.0, 1.0, 0.0, 0.0]
    assert cel.levels(field, 2) == [0.0, 0.0, 1.0, 1.0]
    # `int(v * count)` picks the band and `count - 1` spreads them over 0..1, so three levels are 0, 0.5 and 1 --
    # **not thirds**, which is what the first version of this test expected and what the function does not do.
    assert cel.levels(field, 3) == [0.0, 0.5, 0.5, 1.0]
    with pytest.raises(ValueError):
        cel.levels(field, 1)


def test_the_shadow_is_a_multiply_and_the_identity_is_no_shadow():
    """**`_CodeMultiplyColor` is the property the asset uses to tint a part**, it is set to the identity on all 460
    materials in the corpus, and a cel shadow is exactly what it would carry. So an unshadowed part is the identity
    and the shadow is a multiply -- the same operation, and the corpus shows the neutral element of it."""
    base = (200, 160, 120)
    assert cel.shadow_colour(base, 0.0) == base
    dark = cel.shadow_colour(base, 1.0)
    assert all(d < b for d, b in zip(dark, base)), (dark, base)
    half = cel.shadow_colour(base, 0.5)
    assert all(d <= h <= b for d, h, b in zip(dark, half, base)), (dark, half, base)


def test_a_weaker_strength_gives_a_lighter_shadow():
    base = (200, 160, 120)
    light = cel.shadow_colour(base, 1.0, strength=20.0)
    heavy = cel.shadow_colour(base, 1.0, strength=4.0)
    assert all(l >= h for l, h in zip(light, heavy)), (light, heavy)


def test_the_shading_object_carries_the_art_numbers_and_can_be_told_to_differ():
    default = cel.Shading()
    assert default.shade(0.4) == 1.0 and default.shade(0.6) == 0.0
    other = cel.Shading(light_value=0.7)
    assert other.shade(0.6) == 1.0, 'moving the threshold must move the shadow'
    assert default.shade(0.6) == 0.0


def test_the_per_part_properties_are_declared_and_unused_which_is_not_the_same_thing():
    """**The correction a value-reading made to a presence-counting.**

    The materials census found `_AdjustiveFaceShadow` on 279 of 292 characters and `_AdjustiveHairShadow` on 281, and
    that was reported as *shadow is per-part in this art*. Reading the values: **every one of them is 0.0**, and
    `_CodeAddColor`, `_CodeMultiplyColor` and `_CodeAddRimColor` are the identity on all 460 materials.

    So nothing here may depend on a per-part adjustment being *in use*. What this test can hold is that the library's
    defaults do not assume one, and that the measured neutral values are what `cel` treats as no shadow.
    """
    # the neutral element of the multiply the asset would have used
    assert cel.shadow_colour((128, 128, 128), 0.0) == (128, 128, 128)
    # and the identity strength the corpus actually carries is not a shading decision
    assert cel.Shading().base_brightness == 0.0
    assert cel.Shading().spec_strong == 0.1
