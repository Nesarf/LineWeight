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
from dataclasses import dataclass

#: Where the lit-to-shadow step sits, from `_LightValue`. The mode over the corpus.
LIGHT_VALUE = 0.5

#: How hard the ramp is, from `_ShadowStrong` and `_LightStrong`. Ten is a hard step, and the art's mode is exactly
#: that -- which is what "cel" means here.
SHADOW_STRONG = 10.0
LIGHT_STRONG = 10.0

#: The floor under the lit side, from `_BaseBrightness`, zero in most of the corpus.
BASE_BRIGHTNESS = 0.0

#: The highlight's share, from `_SpecStrong`.
SPEC_STRONG = 0.1


def ramp(value: float, at: float = LIGHT_VALUE, hardness: float = SHADOW_STRONG) -> float:
    """One shading value quantised to lit or shadow: **0.0 or 1.0, and as little in between as the art has.**

    The crossfade is `hardness` wide in the units the value is in, so at the corpus's ten it is a step and at one it
    would be a soft gradient. **The width is not zero**, because a true step produces a hard aliased edge wherever the
    value crosses it, and every renderer in this project anti-aliases -- so the honest form is a very steep ramp and
    the caller can say how steep.

    **This is the whole of "cel"**: the shading signal may be anything continuous, and what makes a drawing
    cel-shaded is that the signal is spent on a near-binary decision rather than shown as a gradient.
    """
    if hardness <= 0:
        raise ValueError('hardness must be positive; a zero-width step has no meaning on a sampled grid')
    edge = 0.5 / hardness
    if value <= at - edge:
        return 1.0          # shadow
    if value >= at + edge:
        return 0.0          # lit
    return 1.0 - (value - (at - edge)) / (2 * edge)


def quantise(values, at: float = LIGHT_VALUE, hardness: float = SHADOW_STRONG) -> list[float]:
    """A field quantised the same way, one value per input."""
    return [ramp(v, at, hardness) for v in values]


def levels(values, count: int = 2, hardness: float = SHADOW_STRONG) -> list[float]:
    """`count` bands instead of two. **Two is what this art uses** (`_LightValue` is a single threshold); the
    parameter exists because a drawing may want a terminator, and it is honest about not having evidence for more.
    """
    if count < 2:
        raise ValueError('a cel ramp needs at least two levels, got %d' % count)
    out = []
    for v in values:
        band = min(count - 1, max(0, int(v * count)))
        out.append(band / (count - 1))
    return out


@dataclass
class Shading:
    """The art's own shading numbers, so a caller can use them or say they are using something else."""
    light_value: float = LIGHT_VALUE
    shadow_strong: float = SHADOW_STRONG
    light_strong: float = LIGHT_STRONG
    base_brightness: float = BASE_BRIGHTNESS
    spec_strong: float = SPEC_STRONG

    def shade(self, value: float) -> float:
        """One value to a shadow weight: 0 lit, 1 shadow."""
        return ramp(value, self.light_value, self.shadow_strong)

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
