"""Cel shading: a hard step, with the step's position and hardness taken from the art.

**What cel shading is here.** Not a shading model -- a *quantisation* of one. The art states its own numbers for
that, and they were read off 60 characters' materials rather than chosen:

| property | what it is | measured |
|---|---|---|
| `_LightValue` | where the lit-to-shadow step sits | mode **0.5** (40 of the bundles), range 0.09-0.6, 41 distinct |
| `_ShadowStrong` | how hard the shadow side is | mode **10.0**, range 4.7-29.2, 16 distinct |
| `_LightStrong` | how hard the lit side is | mode **10.0**, range 5-50, 22 distinct |
| `_BaseBrightness` | a floor on the lit side | **0.0** in 52 of 60 |
| `_SpecStrong` | the highlight's share | mode **0.1**, 42 distinct |

**A strong of 10 is a hard ramp**, which is what makes this cel-shaded art rather than soft-shaded art. So the
quantiser below is steep by default, and the constants are the art's rather than a taste.

## The bridge between the two conventions, derived and checked rather than quoted

MToon's normative pseudocode (`VRMC_materials_mtoon` 1.0) is `linearstep(-1 + toony, 1 - toony, N·L)`, and its own
prose says which property is the width: *"The width of the shading boundary is specified by the
`shadingToonyFactor`"*, shipped at **0.9**. Unity's shipped shader is
`clamp((hL - (Step - Feather)) / Feather, 0, 1)` on the half-Lambert `hL = (N·L + 1) / 2`. Expanding MToon in `hL`
gives `(hL - toony/2) / (1 - toony)`, so matching the two:

```
Feather = 1 - toony        Step = 1 - toony/2
```

**A published write-up of this bridge gave `Step = toony/2 + Feather/2`, and that is wrong** -- it is identically
0.5 for every `toony`, which cannot match a ramp whose *centre moves*. Checked numerically over 8000 samples per
setting: the corrected pair agrees to 1e-16 and the published one is off by up to 0.5. **A derivation is not
verified by being plausible**, and this one was quoted to me by a source that had done everything else well.

**What that does and does not establish.** `Step = 0.5` is Unity's shipped default and `hardness = 10` is MToon's,
**and they are two different engines whose steps differ by 0.05 at that setting** -- MToon at `toony = 0.9` has
`Step = 0.55`. So the corpus's pair `(0.5, 10)` is **Unity's parameterisation carrying MToon's width**
(`_BaseColor_Step = 0.5`, `_BaseShade_Feather = 0.1`), which UTS2 can express and which is what the materials
measure. **Two numbers from two specs is not one spec's default pair**, and saying otherwise would be the kind of
overclaim this file exists to avoid.

## Where the SHAPE comes from, which is not this module

Studio Ghibli's own production diary for 『ゲド戦記』 states the method outright -- 「この影は、まず、アニメーターが
線画で描き分けます」, *this shadow is first drawn out by the animator as line art* -- and NAFCA's animator
certification prescribes the medium: 影 in **blue** coloured pencil, ハイライト in red, the line production calls
**色トレス**. Five independent shader engines place the same shape in a texture the artist paints (UTS2's Position
Map, UE's `DiffuseRampOffsetTexture`, MToon's `shadingShiftTexture`, MMD's painted `toon01`-`toon10`, and SIGGRAPH's
UV offset textures). **So the shape is authored, and this library must not compute it.** A light vector may offer a
starting boundary that a caller overrides, and nothing more.

## And a correction, because the first claim about this was wrong

The materials census counted *presence*: `_AdjustiveFaceShadow` on 279 of 292 characters, `_AdjustiveHairShadow` on
281, `_CodeAddColor` and friends on 288. **That was reported as "shadow is per-part in this art, and the asset says so
through how it is parameterised".** Reading the values rather than the keys:

```
_AdjustiveFaceShadow    0.0  in all 62 material sets that have it
_AdjustiveHairShadow    0.0  in all 57
_AdjustiveShadow        0.0  in all 5
_CodeAddColor           (0,0,0,0)      -- identity, 460 of 460
_CodeMultiplyColor      (1,1,1,1)      -- identity, 460 of 460
_CodeAddRimColor        (0,0,0,0)      -- identity, 460 of 460
_OutlineZCorrection     ~0 in 239 of 243
```

**The capability is per-part; the value is zero.** The asset *can* adjust a face's shadow separately from a hair's,
and on these characters it does not. **"Declared" is not "used"**, and a presence count cannot tell them apart --
which is the same shape as the error this project recorded about a field the renderer ignores being a comment.

What *does* vary per material, and is therefore real: **`_OutlineTint`, 144 distinct values**, mostly greys between
0.31 and 0.6 -- the darkness of the line genuinely differs part by part.
"""

import math
from dataclasses import dataclass, field

#: Where the lit-to-shadow step sits: the mode of `_LightValue` over the corpus, and Unity Toon Shader's shipped
#: `_BaseColor_Step`. It is Unity's number rather than MToon's -- see the module docstring for the derivation.
LIGHT_VALUE = 0.5

#: **The width of the transition, which is the parameter the industry actually names.** Unity calls it Feather, MToon
#: calls the complement Toony, Blender calls it Smooth, and **no shipped shader calls anything "hardness"**. The
#: corpus's mode is 0.1 -- Unity's `_BaseShade_Feather` at MToon's default `toony = 0.9`, since `Feather = 1 - toony`.
FEATHER = 0.1

#: The convenience form, kept because the corpus was measured in it. **`hardness = 1 / feather`**, so the measured
#: hardness of 10 and this feather are the same statement written two ways.
SHADOW_STRONG = 1.0 / FEATHER
LIGHT_STRONG = 1.0 / FEATHER

#: **How many bands a figure may be drawn in, including none.** Ghibli's diary names the ordinary production range --
#: 「影無し」 (no shadow at all), ２段影, ３段影 -- so zero is a real choice rather than a degenerate one, and a
#: function that refuses it would be refusing a documented way to draw.
SHADOW_STEPS = (0, 1, 2, 3)

#: **The shadow ramp is LINEAR; only the HIGHLIGHT takes a power.** Unity Toon Shader's shadow mask is a clamped
#: linear expression while its specular is `pow(abs(spec), exp2(lerp(11, 1, _HighColor_Power)))`. Modelling the
#: terminator as a power curve would be a shape no shipped shader produces.
HIGHLIGHT_POWER = 11.0

#: The floor under the lit side, from `_BaseBrightness`, zero in most of the corpus.
BASE_BRIGHTNESS = 0.0

#: The highlight's share, from `_SpecStrong`.
SPEC_STRONG = 0.1


def ramp(value: float, at: float = LIGHT_VALUE, feather: float = FEATHER) -> float:
    """One shading value quantised to lit or shadow: **0.0 or 1.0, and as little in between as the art has.**

    The transition is `feather` wide in the units the value is in; at the corpus's 0.1 it is a step to the eye and at
    one it would be a soft gradient. **The width is not zero**, because a true step produces a hard aliased edge
    wherever the value crosses it and every renderer in this project anti-aliases -- so the honest form is a very
    steep ramp, and Unity's own default of 0.0001 is the same idea taken further.

    **This is the whole of "cel"**: the shading signal may be anything continuous, and what makes a drawing
    cel-shaded is that the signal is spent on a near-binary decision rather than shown as a gradient.

    **`at` is the CENTRE of the transition, which is not where Unity puts its `Step`.** Unity's ramp is
    `clamp((hL - (Step - Feather)) / Feather, 0, 1)`, so its transition runs from `Step - Feather` to `Step` and
    `Step` is its *upper* end. For the two to describe the same band:

        at = Step - feather / 2

    With the corpus's numbers that is `0.5 - 0.05 = 0.45`, so `LIGHT_VALUE = 0.5` and `_BaseColor_Step = 0.5` are
    **numerically equal and not the same quantity** -- they agree as positions only because Unity ships `Feather` at
    0.0001, where a tenth of a band is invisible. **This is the kind of thing that stays hidden until a feather wide
    enough to see is used**, which is why the test that checks the bridge uses the conversion rather than the
    number.

    **Renamed from `hardness` in the first version.** `hardness` appears in *no* shipped shader's parameter list --
    the industry names are Feather, Toony, Smooth and Width -- and a library inventing its own name for a universal
    quantity makes its own numbers uncheckable against the engines it is copying. `hardness = 1 / feather` is kept
    as the reading, and `FEATHER` and `SHADOW_STRONG` are the same statement written both ways.
    """
    if feather <= 0:
        raise ValueError('feather must be positive; a zero-width transition has no meaning on a sampled grid')
    edge = feather / 2.0
    if value <= at - edge:
        return 1.0          # shadow
    if value >= at + edge:
        return 0.0          # lit
    return 1.0 - (value - (at - edge)) / feather


def quantise(values, at: float = LIGHT_VALUE, feather: float = FEATHER) -> list[float]:
    """A field quantised the same way, one value per input."""
    return [ramp(v, at, feather) for v in values]


def levels(values, steps: int = 1) -> list[float]:
    """A field quantised into `steps` **shadow bands**, on Ghibli's own scale.

    The count is the number of bands *of shadow*, not the number of tones, because that is how the production states
    it -- 「影無し」 (no shadow at all), １段影, ２段影, ３段影 -- so the tones are `steps + 1`: the lit colour is
    always there and each band adds one darker level.

    | `steps` | tones | what it is |
    |---|---|---|
    | 0 | 1 | 影無し -- a flat figure, a documented choice and not a degenerate one |
    | 1 | 2 | the ordinary cel figure |
    | 2 | 3 | ２段影 -- two shadow levels |
    | 3 | 4 | ３段影 |

    **The first version took the number of tones and normalised by `count - 1`, which divided by zero at one tone**
    -- and it validated only `count < 2`, so it accepted a value whose own arithmetic it could not carry out. The
    range is now `SHADOW_STEPS` and the meaning is the production meaning.

    **This uses the value's magnitude alone; it does not call `ramp`.** Bands and a threshold are different
    quantisations of the same signal, and mixing them would give a two-band result whose boundary was at the
    threshold and a three-band one whose boundaries were not.
    """
    if steps not in SHADOW_STEPS:
        raise ValueError('shadow steps must be one of %s, got %d -- 0 is a real production choice, '
                         'not a degenerate one' % (', '.join(str(n) for n in SHADOW_STEPS), steps))
    tones = steps + 1
    if tones < 2:
        return [0.0] * len(values)          # 影無し: drawn with no shadow at all
    out = []
    for v in values:
        band = min(tones - 1, max(0, int(v * tones)))
        out.append(band / (tones - 1))
    return out


@dataclass
class Shading:
    """The art's own shading numbers, so a caller can use them or say they are using something else."""
    light_value: float = LIGHT_VALUE
    feather: float = FEATHER
    base_brightness: float = BASE_BRIGHTNESS
    spec_strong: float = SPEC_STRONG

    @property
    def shadow_strong(self) -> float:
        """The same statement as `feather`, in the form the corpus was measured in: `1 / feather`."""
        return 1.0 / self.feather if self.feather else float('inf')

    def shade(self, value: float) -> float:
        """One value to a shadow weight: 0 lit, 1 shadow."""
        return ramp(value, self.light_value, self.feather)

    def candidate(self) -> float:
        """What the lit side is worth: `_BaseBrightness` floors it and `_SpecStrong` sets a highlight above it."""
        return min(1.0, self.base_brightness + self.spec_strong)


def shadow_colour(base: tuple[int, int, int], weight: float, strength: float = SHADOW_STRONG) -> tuple[int, int, int]:
    """The shadow side of a colour, as a **multiply** -- which is what `_CodeMultiplyColor` is for.

    The multiply is not invented here: `_CodeMultiplyColor` is the property the asset uses to tint a part, it is set
    to the identity on every character in the corpus, and a cel shadow is exactly the thing it would carry. A
    `strength` of ten darkens to about half; a drawing that wants a lighter shadow passes a smaller one.
    """
    if weight <= 0:
        return base
    factor = 1.0 - weight * (1.0 / max(1.0, strength)) * 5.0
    factor = max(0.0, min(1.0, factor))
    return tuple(int(max(0, min(255, round(c * factor)))) for c in base)


# --------------------------------------------------------------------------------------------------------------
# The shape is an INPUT. Everything below exists so a caller can hand this library a boundary someone drew.
#
# **Why an input and not a computation, stated once and with sources.** Studio Ghibli's production diary for
# 『ゲド戦記』: 「この影は、まず、アニメーターが線画で描き分けます」 -- *this shadow is first drawn out by the
# animator as line art* -- and the medium is prescribed by NAFCA's animator certification, 影 in blue coloured pencil,
# the line production calls 色トレス. J.C.STAFF's 仕上げ department page describes the same hand-off: a 色指定表 that
# names the colour "for each character part and each shadow", and a scan step that separates the 実線 from the
# 色トレス線. Five shader engines put the same shape in a texture the artist paints. **Nothing in that chain computes
# the boundary, and no source describes a geometric silhouette-offset algorithm for it** -- that construction is
# documented for cast and ground shadows, which are a different thing and are handled by perspective.
#
# So there is deliberately **no `shadow_from_light()` here.** A function that produced a boundary from a light vector
# would be a shape no source describes and no measurement in this project supports, and it would be the second time
# this module invented a formula where the art had a decision.
# --------------------------------------------------------------------------------------------------------------


@dataclass
class Palette:
    """A part's colours, in the production's own shape: **通常色 and then the shade colours.**

    Unity's official Japanese manual names exactly this stack -- 「通常色」, 「1影色」, 「2影色」 -- and calls an
    authored shadow 固定影, "fixed shadow". The number of shades is the step count, so a palette with one shade is
    a 1段影 figure and one with none is 影無し.
    """

    lit: tuple[int, int, int]
    shades: list = field(default_factory=list)

    def __post_init__(self):
        if len(self.shades) > max(SHADOW_STEPS):
            raise ValueError('%d shades is more than this art uses (%s); the steps are bands of shadow, not tones'
                             % (len(self.shades), ', '.join(str(n) for n in SHADOW_STEPS)))

    @property
    def steps(self) -> int:
        return len(self.shades)

    def colour_for(self, step: int) -> tuple[int, int, int]:
        """Step 0 is the lit colour; 1 is 1影色, 2 is 2影色, and so on."""
        if step <= 0:
            return self.lit
        if step > len(self.shades):
            raise ValueError('this palette has %d shade(s); asked for shadow step %d' % (len(self.shades), step))
        return self.shades[step - 1]


@dataclass
class Shadow:
    """**A shadow someone drew**, as a closed region, plus which band it belongs to.

    The region is used **verbatim**. This is the point of the class: the library's job is to paint what it is given,
    and a boundary is an artistic decision the sources place with the animator and the colour designer rather than
    with the renderer.

    `offset` is a translation and is documented as one -- **not a light model**. The sources say the light direction
    is fixed per cut and recorded (Ghibli's 作打ち meeting, Yonebayashi's arrow on the layout) and that it *moves* the
    boundary; none of them says how far, and a translation is the only motion this library can make without inventing
    a shape. A caller who wants the light to matter passes a different region.
    """

    region: list = field(default_factory=list)
    step: int = 1
    offset: tuple[float, float] = (0.0, 0.0)

    def moved(self) -> list:
        """The region translated by `offset`. A translation, and nothing is inferred from it."""
        dx, dy = self.offset
        return [(x + dx, y + dy) for x, y in self.region]

    def is_closed(self) -> bool:
        return len(self.region) >= 3


def paint_shadow(layer, shadow: 'Shadow', palette: 'Palette', colour: tuple[int, int, int] | None = None) -> int:
    """Fills an authored shadow region with its band's colour. Returns the pixels touched.

    **`palette.colour_for(shadow.step)` by default**, so the colour comes from the part's specification rather than
    from a formula over the lit colour -- which is how the production does it and is also why 影色 can be a cool blue
    against a warm base rather than a darkened version of it.

    Passing `colour` overrides that, for the case the sources name explicitly: 「也有部分画师坚持自己选色，而非图层效果
    直接叠加阴影上去」 -- some illustrators insist on choosing the shadow colour themselves. **A library that offered
    only the derived colour would be implementing half of what the sources describe.**
    """
    from . import raster
    if not shadow.is_closed():
        raise ValueError('a shadow region needs at least three points, got %d' % len(shadow.region))
    fill = colour if colour is not None else palette.colour_for(shadow.step)
    before = layer.data[3::4]
    raster.fill_polygon(layer, shadow.moved(), fill, 1.0)
    after = layer.data[3::4]
    return sum(1 for a, b in zip(before, after) if a != b)
