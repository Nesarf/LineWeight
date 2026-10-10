"""Cel shading: the quantiser, with the art's own numbers and the specs' own names.

Cel is not a shading model, it is a *quantisation* of one. The two things a quantiser needs -- where the step sits
and how wide the transition is -- were measured from 60 characters' materials, and both turn out to be shipped
defaults of documented engines. These tests hold the constants to the measurement, the quantiser to being a step, and
the derivation that connects the two conventions to arithmetic rather than to a quotation.
"""

import random

import pytest

from lineweight import cel


def test_the_constants_are_the_corpus_mode_not_a_taste():
    """`_LightValue` is 0.5 in 40 of the bundles that have it; `_ShadowStrong` and `_LightStrong` are 10."""
    assert cel.LIGHT_VALUE == 0.5
    assert cel.SHADOW_STRONG == pytest.approx(10.0)
    assert cel.LIGHT_STRONG == pytest.approx(10.0)
    assert cel.BASE_BRIGHTNESS == 0.0
    assert cel.SPEC_STRONG == 0.1


def test_the_corpus_width_is_a_step():
    """**Why this art is cel-shaded and not soft-shaded**: the transition is 0.1 wide out of 1, so a value either
    side of the threshold comes out at an end and not in between."""
    assert cel.ramp(0.30) == 1.0
    assert cel.ramp(0.44) == 1.0
    assert cel.ramp(0.56) == 0.0
    assert cel.ramp(0.80) == 0.0
    assert cel.ramp(0.0) == 1.0 and cel.ramp(1.0) == 0.0
    assert 0.0 < cel.ramp(0.5) < 1.0, 'the transition is a tenth wide, not zero'


def test_the_transition_is_as_wide_as_the_feather_says_and_no_wider():
    """**Not a true step**, because a true step aliases wherever the value crosses it and every renderer here
    anti-aliases. The width is the `feather` in the units of the value, and it is the one thing a caller may vary.

    **The parameter is named `feather` and not `hardness`**, because `hardness` appears in no shipped shader's
    parameter list -- the industry names are Feather, Toony, Smooth and Width -- and a library that invents its own
    name for a universal quantity makes its own numbers uncheckable against the engines it copies.
    """
    assert cel.Shading(feather=0.5).shade(0.5) == pytest.approx(0.5)
    assert 0.0 < cel.Shading(feather=0.5).shade(0.6) < 1.0, 'a wide feather should show a transition'
    assert cel.ramp(0.5, feather=0.5) == pytest.approx(0.5)
    assert cel.ramp(0.5, feather=0.1) == pytest.approx(0.5)

    def width(f):
        xs = [i / 1000.0 for i in range(1001)]
        inside = [x for x in xs if 0.0 < cel.ramp(x, feather=f) < 1.0]
        return max(inside) - min(inside) if inside else 0.0

    assert width(0.5) > width(0.1) > width(0.02)
    # and the two names are one statement
    assert cel.Shading(feather=0.1).shadow_strong == pytest.approx(10.0)


def test_a_zero_feather_is_refused_rather_than_silently_a_step():
    with pytest.raises(ValueError) as caught:
        cel.ramp(0.5, feather=0.0)
    assert 'positive' in str(caught.value)


def test_quantise_and_levels():
    field = [0.1, 0.4, 0.6, 0.9]
    assert cel.quantise(field) == [1.0, 1.0, 0.0, 0.0]
    # **`steps` counts shadow BANDS, on Ghibli's own scale**, so the tones are one more than it
    assert cel.levels(field, 0) == [0.0, 0.0, 0.0, 0.0], '影無し -- a documented way to draw, not an error'
    assert cel.levels(field, 1) == [0.0, 0.0, 1.0, 1.0]
    assert cel.levels(field, 2) == [0.0, 0.5, 0.5, 1.0]
    assert cel.levels(field, 3) == [0.0, 1 / 3, 2 / 3, 1.0]


def test_an_impossible_step_count_is_refused_rather_than_computed():
    """**The first version divided by zero at one tone.** It took the number of *tones*, normalised by `count - 1`,
    and validated only `count < 2` -- so it accepted a value whose own arithmetic it could not carry out."""
    field = [0.1, 0.9]
    with pytest.raises(ValueError) as caught:
        cel.levels(field, 7)
    assert 'production choice' in str(caught.value)
    with pytest.raises(ValueError):
        cel.levels(field, -1)


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
    assert cel.shadow_colour((128, 128, 128), 0.0) == (128, 128, 128)
    assert cel.Shading().base_brightness == 0.0
    assert cel.Shading().spec_strong == 0.1


def test_the_mtoon_bridge_holds_by_arithmetic():
    """**The derivation this module's two constants rest on, checked rather than quoted.**

    MToon's normative pseudocode is `linearstep(-1 + toony, 1 - toony, N.L)`, whose output is the *lit* fraction;
    Unity's shipped shader is `clamp((hL - (Step - Feather)) / Feather, 0, 1)`. Expanding MToon in the half-Lambert
    `hL` gives `(hL - toony/2) / (1 - toony)`, which matches with **`Feather = 1 - toony`** and
    **`Step = 1 - toony/2`**.

    **A published write-up of this bridge gave `Step = toony/2 + Feather/2`, and that is wrong** -- it is
    identically 0.5 for every `toony`, which cannot match a ramp whose centre moves. This test is what caught it.

    **And the second thing it caught is this module's own anchoring.** `cel.ramp`'s `at` is the *centre* of the
    transition while Unity's `Step` is its *upper end*, so reproducing Unity needs `at = Step - feather/2`. Using
    `at = Step` agreed at the corpus's feather only by luck -- 0.05 of a band -- and diverged by up to 0.5 at a
    feather of 1, which is what the first version of this test hit.
    """

    def shadow_mtoon(nl, toony):
        a, b = -1.0 + toony, 1.0 - toony
        return 1.0 - min(1.0, max(0.0, (nl - a) / (b - a)))

    random.seed(3)
    for toony in (0.0, 0.3, 0.5, 0.9, 0.95, 0.99):
        feather = 1.0 - toony
        step = 1.0 - toony / 2
        for _ in range(2000):
            nl = random.uniform(-1, 1)
            hl = 0.5 * nl + 0.5
            # **Unity's `Step` is the upper end of the band; `cel.ramp`'s `at` is its centre.** Using `at = Step`
            # agreed at the corpus's feather by luck -- 0.05 of a band -- and diverged by up to 0.5 at a feather of
            # 1, which is what the first version of this test hit.
            centre = step - feather / 2
            assert shadow_mtoon(nl, toony) == pytest.approx(cel.ramp(hl, at=centre, feather=feather), abs=1e-9), \
                'toony %.2f at N.L %.3f' % (toony, nl)


def test_the_shipped_defaults_are_the_two_numbers_that_were_measured():
    """`0.5` is Unity's `_BaseColor_Step` and `hardness 10` is MToon's `shadingToonyFactor = 0.9` -- **and they are
    two different engines whose steps differ by 0.05 at that setting**, so the pair is not one spec's default pair.
    MToon at toony 0.9 has `Step = 1 - 0.45 = 0.55`. Saying otherwise would be an overclaim."""
    assert cel.LIGHT_VALUE == pytest.approx(0.5)
    assert cel.FEATHER == pytest.approx(1.0 - 0.9)
    assert cel.SHADOW_STRONG == pytest.approx(10.0)
    assert (1.0 - 0.9 / 2) == pytest.approx(0.55)


def test_the_shadow_ramp_is_linear_and_only_the_highlight_takes_a_power():
    """Unity Toon Shader's shadow mask is a clamped linear expression; its specular is
    `pow(abs(spec), exp2(lerp(11, 1, _HighColor_Power)))`. Modelling the terminator as a power curve would be a
    shape no shipped shader produces, so the constant exists to be pointed at rather than used."""
    assert cel.HIGHLIGHT_POWER == 11.0
    # linear means equal steps in the input give equal steps in the output, across the transition
    f = 0.4
    a, b, c = (cel.ramp(x, feather=f) for x in (0.35, 0.45, 0.55))
    assert (a - b) == pytest.approx(b - c, abs=1e-9), (a, b, c)


# ------------------------------------------------------------------------------------------------------------
# The shape is an INPUT. These hold the library to painting what it is given and to NOT computing a boundary.

def test_a_palette_is_the_productions_colour_specification():
    """通常色 then the shade colours -- Unity's official Japanese manual names exactly this stack, 「通常色」,
    「1影色」, 「2影色」, and calls an authored shadow 固定影."""
    p = cel.Palette(lit=(230, 210, 190), shades=[(180, 170, 200), (140, 135, 175)])
    assert p.steps == 2
    assert p.colour_for(0) == (230, 210, 190)
    assert p.colour_for(1) == (180, 170, 200)
    assert p.colour_for(2) == (140, 135, 175)
    with pytest.raises(ValueError):
        p.colour_for(3)
    # 影無し is a palette with no shades, which Ghibli names as an ordinary choice
    assert cel.Palette(lit=(200, 200, 200)).steps == 0
    with pytest.raises(ValueError):
        cel.Palette(lit=(200, 200, 200), shades=[(1, 1, 1)] * 5)


def test_a_shadow_region_is_used_verbatim():
    """**The point of the class.** The library's job is to paint what it is given; a boundary is an artistic
    decision the sources place with the animator and the colour designer rather than with the renderer."""
    drawn = [(10.0, 10.0), (90.0, 14.0), (86.0, 60.0), (12.0, 55.0)]
    s = cel.Shadow(region=drawn, step=1)
    assert s.moved() == drawn, 'no offset means the region is untouched'
    assert s.is_closed()
    assert not cel.Shadow(region=[(0, 0), (1, 1)]).is_closed()


def test_the_offset_is_a_translation_and_is_documented_as_one():
    """**Not a light model.** The sources say the light direction is fixed per cut and recorded, and that it *moves*
    the boundary; none says how far. A translation is the only motion this library can make without inventing a
    shape, and a caller who wants the light to matter passes a different region."""
    s = cel.Shadow(region=[(0, 0), (10, 0), (10, 10)], offset=(5.0, -2.5))
    assert s.moved() == [(5.0, -2.5), (15.0, -2.5), (15.0, 7.5)]
    # and the original is not disturbed
    assert s.region == [(0, 0), (10, 0), (10, 10)]


def test_there_is_no_shadow_computed_from_a_light_vector():
    """**A negative test, and the most important one in this file.**

    Studio Ghibli's production diary says the shadow 「まず、アニメーターが線画で描き分けます」 -- first drawn by the
    animator as line art -- and NAFCA prescribes the medium (影 in blue coloured pencil, the line production calls
    色トレス). Five shader engines put the shape in a texture the artist paints. **No source describes a geometric
    silhouette-offset algorithm for a character's terminator**; that construction is documented for cast and ground
    shadows, which are a different thing.

    So the library must not have one. This test exists so that adding one is a deliberate act that breaks a test
    rather than a plausible-looking helper someone adds on the way past.
    """
    for forbidden in ('shadow_from_light', 'terminator_from_light', 'shadow_region_from'):
        assert not hasattr(cel, forbidden), '%s would be a shape no source describes' % forbidden


def test_painting_an_authored_shadow_uses_the_palette_and_can_be_overridden():
    """The colour comes from the part's specification rather than from a formula over the lit colour -- which is how
    the production does it, and why 影色 can be a cool blue against a warm base rather than a darkened version of it.

    **And it can be overridden**, for the case the sources name explicitly: 「也有部分画师坚持自己选色，而非图层效果
    直接叠加阴影上去」. A library offering only the derived colour would implement half of what they describe.
    """
    from lineweight import raster
    p = cel.Palette(lit=(230, 210, 190), shades=[(180, 170, 200)])
    region = [(20.0, 20.0), (120.0, 20.0), (120.0, 90.0), (20.0, 90.0)]
    s = cel.Shadow(region=region, step=1)

    layer = raster.Layer(160, 130)
    touched = cel.paint_shadow(layer, s, p)
    assert touched > 5000, touched
    # **a pixel inside the region, not (0, 0)** -- the region starts at (20, 20) and the first version of this test
    # read the corner, which is outside it and black, and would have passed for any colour the fill used
    inside = (50 * 160 + 60) * 4
    outside = (5 * 160 + 5) * 4
    # **`list()` matters**: `layer.data` is a `bytearray`, so a slice of it is a `bytearray` and comparing one to a
    # list is False however the bytes read. The first version of this test compared the two and failed on a fill that
    # was correct.
    assert list(layer.data[inside:inside + 3]) == [180, 170, 200], 'the palette 1影色'
    assert layer.data[outside + 3] == 0, 'outside the region must be untouched'

    other = raster.Layer(160, 130)
    cel.paint_shadow(other, s, p, colour=(10, 20, 30))
    assert list(other.data[inside:inside + 3]) == [10, 20, 30], 'an explicit colour must win'


def test_a_shadow_region_with_too_few_points_is_refused():
    from lineweight import raster
    with pytest.raises(ValueError) as caught:
        cel.paint_shadow(raster.Layer(20, 20), cel.Shadow(region=[(0, 0), (5, 5)]), cel.Palette(lit=(1, 2, 3)))
    assert 'three points' in str(caught.value)
