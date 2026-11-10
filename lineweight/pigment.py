"""Oil paint as a material: how a colour is changed, and why mixing two tubes is not a half-and-half average.

**Why this belongs in the library and not in a brush script.** An earlier version of every painting script carried its
own four-line `mix(a, b, t)` -- a straight interpolation of three numbers. That is arithmetic, not knowledge, and it is
wrong in a specific way: it assumes two tubes of paint contribute to the mixture in proportion to how much of each was
scooped out. They do not. **A little of one pigment can move a mixture further than a lot of another**, and the amount
of paint involved is not the quantity that decides it. Every colour on the fish, the apple and the pair was built on
that equal-parts assumption, which is why adding "a touch" of a dark always behaved exactly like adding "a quarter".

`opacity` and `strength` are separate axes and it is easy to conflate them, so the table keeps two columns and the
tests keep two pigments that disagree about the order (cadmium yellow is opaque and weak; ultramarine is transparent
and strong). Both columns are material facts in the same sense that a line's role is a convention: they describe what
the paint does, not what a picture should look like.

## What is sourced, and what is approximated

**Sourced: which pigments cover and which ones let the ground through.** Winsor & Newton's masterclass demonstrates
the test by pulling each colour down a white board and across a solid black line; the opaque colour obliterates the
line, the transparent one lets it show. Their six examples are in the table below with their verdicts unchanged.

**Sourced: that strength is not pigment load.** Phoenix Art Materials states the two as different quantities, that
tinting strength depends on pigment type, particle properties, dispersion and the white it is mixed into, and that a
strong tint is efficient in a large mixture and hard to control in a delicate passage.

**Approximated: the numbers.** The opacity column is a three-valued class rather than a measurement, and the strength
column is a rank on nought to one, not a ratio anyone measured. The mass tones are display approximations with no
authority behind them at all -- they exist so the table can be looked at. **A script that needs a pigment's real
spectrum is not served by this module**, and the module says so rather than implying otherwise.

**Not attempted: subtractive mixing.** Blending two pigments is a Kubelka-Munk problem, and this is an RGB pipeline.
`mix_by_strength` corrects the equal-parts assumption and nothing else; the interpolation underneath stays linear, in
the same colours the rest of the library already speaks. Naming that limit is the point -- a corrected weighting on an
uncorrected model is a real improvement, and it is not a colour model.

## Three operations, not one

A painter does not mix two arbitrary tubes; the handbooks describe three named moves, and the distinction is worth
keeping because each one changes a different property of the colour:

| operation | added | what it moves |
|---|---|---|
| `tint` | white | lightness up, chroma down |
| `shade` | black | lightness down, chroma down |
| `tone` | grey | lightness and chroma pulled toward the middle together, which keeps the value the shade would spend |

Gamblin's glossary defines all three in one line each. `MIX_OPERATIONS` is that list, and `tools/check_learn.py`
refuses a difference between it and `learn/facts.json`.
"""
from __future__ import annotations

#: The three named ways to change a colour. Gamblin, *Painting Glossary*: a tint is a hue mixed with white, a shade is
#: a colour mixed with black, a tone is a colour mixed with grey.
MIX_OPERATIONS = ('tint', 'shade', 'tone')

#: Opacity classes. `opaque` obliterates a black line pulled under it, `transparent` lets the line show through, and
#: `semi` is the middle band Winsor & Newton's own symbol set also carries. **Not a measurement** -- a three-valued
#: class, which is the resolution their demonstration can settle.
OPAQUE = 'opaque'
SEMI = 'semi'
TRANSPARENT = 'transparent'
OPACITY_CLASSES = (OPAQUE, SEMI, TRANSPARENT)

#: name -> (mass tone, opacity class, tinting strength)
#:
#: The six named in Winsor & Newton's opaque/transparent masterclass keep its verdicts; the rest are the pigments a
#: still life actually reaches for, classified the same way. Strength is a rank: 0 would not move a mixture at all and
#: 1 would take it over completely.
PIGMENTS = {
    'titanium_white': ((250, 248, 242), OPAQUE, 0.95),
    'zinc_white': ((252, 250, 245), SEMI, 0.25),
    'cadmium_yellow': ((255, 200, 40), OPAQUE, 0.30),
    'transparent_yellow': ((250, 210, 60), TRANSPARENT, 0.44),
    'yellow_ochre': ((196, 148, 84), OPAQUE, 0.40),
    'naples_yellow': ((240, 214, 150), OPAQUE, 0.30),
    'cadmium_red': ((208, 62, 38), OPAQUE, 0.45),
    'permanent_rose': ((226, 96, 140), TRANSPARENT, 0.72),
    'alizarin_crimson': ((140, 40, 60), TRANSPARENT, 0.78),
    'cerulean_blue': ((58, 154, 190), OPAQUE, 0.55),
    'ultramarine_blue': ((54, 66, 152), TRANSPARENT, 0.80),
    'viridian': ((30, 110, 96), TRANSPARENT, 0.70),
    'burnt_umber': ((94, 62, 44), TRANSPARENT, 0.62),
    'raw_umber': ((110, 88, 54), TRANSPARENT, 0.50),
    'ivory_black': ((36, 34, 32), OPAQUE, 0.85),
    'mars_black': ((28, 26, 26), OPAQUE, 0.88),
}

#: The white a tint uses and the black a shade uses. Titanium rather than zinc because a tint made with zinc white is
#: weak enough to need a second application before it reads as the same step; the two are in the table so the choice is
#: visible and can be overridden.
DEFAULT_WHITE = 'titanium_white'
DEFAULT_BLACK = 'mars_black'
#: The grey a tone uses. Mid, slightly warm, because a dead-neutral grey desaturates faster than a painter's grey does.
DEFAULT_GREY = (128.0, 124.0, 118.0)


def pigment(name):
    """The mass tone, opacity class and strength of a named pigment."""
    try:
        tone, opacity, strength = PIGMENTS[name]
    except KeyError:
        raise KeyError('unknown pigment %r; known: %s' % (name, ', '.join(sorted(PIGMENTS)))) from None
    return tone, opacity, strength


def mass_tone(name):
    """Just the colour, as three floats."""
    return tuple(float(c) for c in pigment(name)[0])


def opacity_of(name):
    """Just the class."""
    return pigment(name)[1]


def strength_of(name):
    """Just the rank."""
    return pigment(name)[2]


def mix_by_strength(first, second, t, first_strength=1.0, second_strength=1.0):
    """Mix two colours by how strongly each one tints, rather than by how much of each was scooped.

    `t` is still the ratio of the two tubes -- nought is all `first`, one is all `second` -- and the strengths decide
    how far into the mixture each one reaches. With equal strengths this is a straight interpolation and reproduces
    the four-line `mix` every script used to carry, which is the reason it is safe to swap in: **the new behaviour
    appears exactly where the strengths differ, and nowhere else.**
    """
    amount = max(0.0, min(1.0, float(t)))
    reach_first = (1.0 - amount) * max(0.0, float(first_strength))
    reach_second = amount * max(0.0, float(second_strength))
    total = reach_first + reach_second
    if total <= 0.0:
        return tuple(float(c) for c in first)
    share = reach_second / total
    return tuple(float(first[i]) + (float(second[i]) - float(first[i])) * share for i in range(3))


def mix_pigments(first_name, second_name, t):
    """`mix_by_strength` with both strengths read from the table."""
    return mix_by_strength(mass_tone(first_name), mass_tone(second_name), t,
                           strength_of(first_name), strength_of(second_name))


def tint(colour, t, white=DEFAULT_WHITE):
    """Add white: lightness up, chroma down."""
    return mix_by_strength(colour, mass_tone(white), t, 1.0, strength_of(white))


def shade(colour, t, black=DEFAULT_BLACK):
    """Add black: lightness down, chroma down."""
    return mix_by_strength(colour, mass_tone(black), t, 1.0, strength_of(black))


def tone(colour, t, grey=None):
    """Add grey: lightness and chroma pulled toward the middle together, so the value survives better than a shade."""
    grey = DEFAULT_GREY if grey is None else grey
    return mix_by_strength(colour, tuple(float(c) for c in grey), t, 1.0, 1.0)


def operate(colour, operation, t):
    """One of the three named operations, for a caller that has the operation as a value rather than as a call."""
    try:
        function = {'tint': tint, 'shade': shade, 'tone': tone}[operation]
    except KeyError:
        raise KeyError('unknown operation %r; known: %s' % (operation, ', '.join(MIX_OPERATIONS))) from None
    return function(colour, t)
