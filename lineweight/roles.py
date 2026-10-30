"""Line roles: what a line is *for*, and the measured evidence for what each one costs.

A drawing has one brush per stroke and no notion of a line's role -- every line is drawn by whatever the caller
passed. That is a large part of why output reads flat, and it is not a geometry problem. A line drawing is not a set
of lines of assorted widths; it is a set of lines that **mean** different things, and the convention that assigns the
meanings is old and explicit:

| role | drawing convention | formal term |
|---|---|---|
| `silhouette` | 輪郭線, the outer contour | **silhouette** -- where the surface turns away from the viewer |
| `shadow` | 陰影線, the shadow or form line | **suggestive contour** -- where the surface is about to turn away |
| `contour` | 内部線, an interior line | **contour** -- a depth or orientation discontinuity |
| `detail` | 補助線, fine hair tips and auxiliary lines | -- |

The formal column is why this is a model rather than a habit: the NPR taxonomy is defined on a surface, so a proposed
輪郭線 is in principle **checkable** -- it either lies on a silhouette or it does not. Which lines *should exist* is
the question this project's original complaint was about (2.5D modelling produces silhouettes and nothing else, which
is why it looks unintentional).

## Two things are measured and one is not, and it matters which

**Measured: colour is a second axis, with a direction.** KEER2014 drew four characters with pressure deliberately
removed, ten outline conditions each, and found that impressions of *naturalness* and *potency* are moved by the
outline's colour and thickness **rather than by the character design**, while *activity* is moved by the design and
not by the outlines. The two are separable, so "it looks unnatural or weak" is a diagnosis about the linework and no
amount of character-design work will fix it. Thicker raises potency and lowers naturalness; brown/reddish-brown
raises naturalness and lowers potency. **It is a trade, not an optimum** -- and a hierarchy that only ever thickens
the contour is spending naturalness to buy potency without saying so, which is what `trade()` exists to make visible.
See `RESEARCH-LINE-QUALITY.md`.

**Measured: the width range a drawing occupies.** From `tests/data/corpus_summary.json` over 276 line drawings out of
929 measured images in three independent collections: within one drawing, the 90th-percentile line width is **2.75x**
the median and the maximum is **5.33x**. Three collections agreeing is the whole argument -- `2.750` from 26 images,
`2.750` from 262, `2.750` after adding seventeen character-art sheets.

**Not measured: where inside that range each role sits.** The convention states the *ordering* (outer contour thick,
interior lines thin, fine hair tips thinner) and one requirement -- *"check that thick and thin are still
distinguishable at reduced scale"* -- but no magnitudes. So the widths below are a **placement rule, not a
measurement**, and they are placed the one way that is not arbitrary: `contour` is the anchor at 1.0 because the
brush width is calibrated to the median line width and interior lines are the most numerous; `silhouette` is the
corpus's own p90/median, because in a finished drawing the p90 *is* the outer contour; and `shadow` and `detail` sit
geometrically either side of the anchor, inside the corpus's max/median envelope.

## The caveat a role model has to carry

The library's existing spread -- brush and pressure model alone, no roles -- already lands at p90/median **2.67**
against the reference 2.75 (README calibration table). **So role multipliers add on top of a ratio that is already at
target, and a drawing that puts every stroke in `silhouette` will overshoot the corpus badly.** Two of the three
numbers in that table are computed over a pool that mixes all four brushes, including the 22-unit wash, which a real
drawing would not put beside a 2-unit pen -- so part of the existing spread may be a confound of the pool rather than
a property of a drawing. That question is open. What follows from it is not: **`--roles` reports the drawing's own
measured ratios next to the corpus reference**, because that is the only way a role assignment can be argued with.
"""

from __future__ import annotations

from typing import NamedTuple

# From the pooled corpus (`tests/data/corpus_summary.json`, README calibration table). Within one drawing.
WIDTH_P90_OVER_MEDIAN = 2.75
WIDTH_MAX_OVER_MEDIAN = 5.33


# **The ink a drawing is made of when nobody says otherwise.**
#
# This was `#1A1620` -- a cool violet-black, R-B minus six -- and *neither measured drawing is cool*. Video 1's line
# stage measures a warm red-brown at R-B **+40** (46% of its ink pixels have a measurable hue); video 2's measures
# **hueless**, with no measurable hue at all across five frames and 146k-317k ink pixels each. Both sit where KEER2014
# found a positive naturalness impression -- black and the browns -- and a cool cast sits on neither. Neutral is the
# one value both drawings agree with, and a warm ink is the `silhouette` role's, which is where the convention puts it.
#
# The two recorded figures this replaces were +10 and +0.3, and both were wrong in a way that mattered: see
# `RESEARCH-LINE-QUALITY.md`, "the ink axis, re-measured".
DEFAULT_INK = '#1A1A1A'

# The placement rule, as code rather than as a comment: the two middle roles sit one geometric step either side of the
# anchor, so the ratio between adjacent roles is the same going up as going down. Derived rather than typed, because
# two hand-rounded numbers cannot be reciprocal and a test that says they are would be asserting the rounding.
_ROLE_STEP = WIDTH_P90_OVER_MEDIAN ** 0.5


class Role(NamedTuple):
    """One kind of line. **Data, not behaviour** -- adding a role is adding a row, not a branch."""
    name: str
    japanese: str
    formal: str
    width: float        # multiplier on the brush width
    ink: str            # the colour this role is drawn in by default
    source: str         # where its width comes from, honestly labelled
    trade: str          # what it buys and what it costs, where that has been measured


# The four rows. `width` is a placement rule rather than a measurement -- see the module docstring for the anchor and
# the envelope -- and every `source` says which of the two it is.
ROLES: dict[str, Role] = {
    'silhouette': Role(
        'silhouette', '輪郭線', 'silhouette', WIDTH_P90_OVER_MEDIAN, '#2A1C18',
        'the corpus p90/median: in a finished drawing the p90 is the outer contour',
        'buys potency, costs naturalness (KEER2014, measured)'),
    'shadow': Role(
        'shadow', '陰影線', 'suggestive contour', _ROLE_STEP, '#241A18',
        'placed geometrically between the anchor and the silhouette, inside the corpus max/median envelope',
        'convention only: the shadow side, and the base of hair strands and cloth folds, are drawn thicker'),
    'contour': Role(
        'contour', '内部線', 'contour (occlusion edge)', 1.0, DEFAULT_INK,
        'the anchor -- the brush width is calibrated to the corpus median line width and interior lines are the most '
        'numerous',
        'convention only: interior lines go thin, except where parts overlap'),
    'detail': Role(
        'detail', '補助線', '--', 1.0 / _ROLE_STEP, '#3A2A26',
        'placed geometrically below the anchor by the same step as `shadow` above it',
        'convention only: fine hair tips and auxiliary lines, which must not obstruct'),
}

# No role means "the brush width, exactly as given", which is what every drawing did before roles existed. It is
# deliberately not one of the four: defaulting a missing role to `contour` would silently rescale every existing
# stroke in every existing project file by 1.0 while looking like it had done nothing at all.
NO_ROLE = ''

#: **A role is what a line is for; a part is where it is drawn.** This table is the first row of the part-x-role table
#: described in `AESTHETIC-LIBRARY.md`, and it exists because a model that knows a line is a `contour` still does not know
#: whether it is drawing a hair tip or a jaw -- and those two must not be drawn the same weight.
#:
#: The content is `learn/facts.json`'s `light_source_rule`: *comic-inking* ch.III names five places on a face that carry
#: extra weight, and the rule behind them is "heavy on the dark side, thin on the light side". Four of the five sit under
#: a form that overhangs -- the eyelid under its own lid, the nose, both lips -- so they are `shadow`, the convention's
#: 陰影線. The jaw is where the head's surface turns away from the viewer, which is the definition of `silhouette`, so it
#: carries that role and its wider multiplier.
#:
#: **The fact and this table are checked against each other** by `tools/check_learn.py`, because two copies of one fact
#: drift silently -- the same fault that kept a wrong pixel threshold in service for two whole rounds.
PART_ROLES: dict[str, str] = {
    'under_top_eyelid': 'shadow',
    'under_nose': 'shadow',
    'under_top_lip': 'shadow',
    'under_bottom_lip': 'shadow',
    'jaw_line': 'silhouette',
}


def names() -> tuple[str, ...]:
    return tuple(ROLES)


def role(name: str) -> Role:
    """Looks a role up. **A name that is not in the registry is refused, not guessed.**

    Falling back to a default would mean a typo produces a drawing that is plausibly wrong -- and the whole point of
    naming a line's role is that the name is the claim being made about it.
    """
    if name not in ROLES:
        raise ValueError('unknown line role %r; known roles are %s'
                         % (name, ', '.join(sorted(ROLES)) or 'none'))
    return ROLES[name]


def width_scale(name: str) -> float:
    """The multiplier a role applies to the brush width. An unset role is 1.0 and changes nothing."""
    return ROLES[name].width if name else 1.0


#: **What the measurements support: an order, not a magnitude.** Three drawings were labelled by part and measured with
#: subpixel widths (`tools/line_width_library.py --regions`), in units of each figure's own height:
#:
#:     150605691  pencil full figure   face 0.309  eye 0.300  boot 0.197  hair 0.194  cloth 0.165
#:     150609781  grey-toned figure    eye  0.345  face 0.335 hair 0.291  dress 0.230 leg 0.229  boot 0.200
#:     150605984  smooth outline       head 0.160  leg 0.158  torso 0.155 shoe 0.154  dress 0.131
#:
#: The third is not a counterexample: a drawing with no interior detail has no hierarchy of line to measure, and its
#: ratio of 1.22 between heaviest and lightest part says so. **The table applies to drawings that spend line weight on
#: hierarchy**, which is a classification step before the lookup and is what `roles_report` already prints.
#:
#: **Only comparisons that repeat across drawings are written here.** Face and eye are above hair and boot in both
#: measuring drawings; face against eye swaps (0.309 over 0.300, then 0.345 over 0.335) and hair against boot swaps too,
#: so each pair shares a tier. **A tier means the order inside it was not measured**, not that it is absent -- and a
#: caller told None gets to say so instead of inventing a rank.
PART_TIERS: tuple[tuple[str, ...], ...] = (
    ('face', 'eye'),
    ('hair', 'cloth', 'leg', 'boot'),
)


def tier_of(part: str) -> int | None:
    """Which tier a part sits in, 0 being the heaviest, or None when the part has not been measured."""
    for index, tier in enumerate(PART_TIERS):
        if part in tier:
            return index
    return None


def heavier_than(part: str, other: str) -> bool | None:
    """Whether `part` is drawn heavier than `other`, or **None when the measurements do not decide it.**

    Two parts in one tier, or a part nobody has measured, both give None rather than a plausible answer: this table
    exists to be checked against a drawing, and a guess dressed as a verdict cannot be checked.
    """
    a, b = tier_of(part), tier_of(other)
    if a is None or b is None or a == b:
        return None
    return a < b


#: **A tier is not a role**, so turning one into the other is a decision that has to be named rather than implied. The
#: measured statement is "these parts are drawn heavier than those"; the convention's statement is that a heavier line is
#: a shadow line (陰影線) and a lighter one is an interior contour (内部線). Put together, the top tier answers with
#: `shadow` and the rest with `contour`.
#:
#: **It is a fallback, not a measurement**, and the caller can ask for it to be off. `--roles` prints which of the two a
#: stroke's role came from, because "the book says this part is a shadow line" and "this part is in the heavy half and
#: heavy means shadow" are different claims.
TIER_ROLES: tuple[str, ...] = ('shadow', 'contour')


#: **The coarse tiers a position rule can give.** `part_by_height` in `tools/edge_strokes.py` knows only where a line sits,
#: not what it draws: it can say `head`, never `face` or `hair`. This maps those three words onto the tiers `PART_TIERS`
#: uses, so a line filed by position can still be given a role -- with the understanding that everything in the head gets
#: the face's treatment, hair included, and everything on the body gets the cloth's.
#:
#: **It is a mapping between two vocabularies and not a measurement**, which is why it is separate from `PART_TIERS`:
#: adding `head` to a tier would have claimed the measurements covered a part nobody measured.
COARSE_TIERS: dict[str, int] = {'head': 0, 'torso': 1, 'legs': 1}


#: **A rig's word for a part, mapped onto the six words the measurements use.** A model names 30 families because that
#: is how many parts are worth moving -- `hair` alone is 134 bones -- while `PART_TIERS` names six because those six are
#: what an illustrator's drawing was measured on. This translates the first onto the second wherever the correspondence
#: is plain, and **leaves the rest out on purpose**.
#:
#: **What is absent is the finding.** The arms and the hands have no word in `PART_TIERS` at all: the corpus was measured
#: on full-body drawings, and "the arm" was never one of the parts compared. So `upper`, `lower`, `hand` and the five
#: fingers are not here -- a line on an arm then has a position and no role. On the first render measured that gap is
#: **16 per cent of the line**, which is why it is written down rather than papered over with `cloth`.
#:
#: **`ear` and `bag` are absent for the same reason as the arms**: bones that exist, parts that nobody measured.
BONE_FAMILIES: dict[str, str] = {
    'face': 'face',
    'eye': 'eye',
    'hair': 'hair',
    'ahoge': 'hair',
    'cloth': 'cloth',
    'skirt': 'cloth',
    'ribbon': 'cloth',
    'belt': 'cloth',
    'chest': 'cloth',
    'leg': 'leg',
    'foot': 'boot',
    'toe': 'boot',
}


def role_for_part(part: str, allow_tier: bool = True) -> Role | None:
    """The role a named part is drawn in, **or None when nothing decides it.**

    **Three sources, in order of how much they claim.** A part named in `PART_ROLES` gets the role the books give it. A
    part in one of the measured `PART_TIERS` gets that tier's role, which is a derivation and not a citation. A part in
    neither gets None.

    **None rather than a fallback to `contour`**, for the reason `role()` refuses an unknown name: a part nobody has
    written down is a part nobody has decided about, and answering "contour" would turn "not yet decided" into a
    confident answer that happens to look like every other line.
    """
    name = PART_ROLES.get(part)
    if name:
        return ROLES[name]
    if not allow_tier:
        return None
    tier = tier_of(part)
    if tier is None:
        tier = COARSE_TIERS.get(part)
    if tier is None:
        # **A rig's word translated into a measured one, and only where the two name the same thing.** The absence list
        # in `BONE_FAMILIES` is load-bearing: an arm falls through to None, which is the honest answer, rather than
        # borrowing the cloth's role because it is also "not the head".
        alias = BONE_FAMILIES.get(part)
        if alias is not None:
            tier = tier_of(alias)
    if tier is None or tier >= len(TIER_ROLES):
        return None
    return ROLES[TIER_ROLES[tier]]


def parts_for_role(role_name: str) -> tuple[str, ...]:
    """Every part drawn in one role, in name order. The reverse lookup, which is what a checklist needs."""
    return tuple(sorted(part for part, name in PART_ROLES.items() if name == role_name))


def ink(name: str) -> str:
    """The colour a role is drawn in by default, or the historical default ink when there is no role."""
    return ROLES[name].ink if name else DEFAULT_INK


def chroma(colour: str) -> float:
    """Saturation of a `#RRGGBB`, 0..1. **This, and not hue, is the axis KEER2014 measured.**

    Reddish-brown scored positive on naturalness and red scored negative. They are a few degrees apart in hue, so a
    hue test cannot separate them and would confidently report the opposite of the finding.
    """
    text = colour.lstrip('#')
    if len(text) == 3:
        text = ''.join(c * 2 for c in text)
    if len(text) != 6:
        raise ValueError('not a #RRGGBB colour: %r' % (colour,))
    channels = [int(text[i:i + 2], 16) for i in (0, 2, 4)]
    top = max(channels)
    return 0.0 if top == 0 else (top - min(channels)) / 255.0


def value(colour: str) -> float:
    """Brightness of a `#RRGGBB`, 0..1."""
    text = colour.lstrip('#')
    if len(text) == 3:
        text = ''.join(c * 2 for c in text)
    return max(int(text[i:i + 2], 16) for i in (0, 2, 4)) / 255.0


def measured_natural(colour: str) -> bool:
    """Whether a colour sits where the measurement found a positive naturalness impression.

    The three that scored positive are **black and two browns**; the three that scored negative are **green, blue and
    red**. Tested as saturation plus darkness, because that is what separates a brown from a red.
    """
    return chroma(colour) < 0.25 or value(colour) < 0.35


def ink_verdict(colour: str) -> str:
    """A one-line reading of a colour against the measured axis, for a report."""
    if measured_natural(colour):
        return 'measured positive (black, or a desaturated brown)'
    return 'measured NEGATIVE (green, blue or red scored below neutral; saturation %.2f)' % chroma(colour)


def trade(name: str) -> str:
    """What an assignment buys and what it costs.

    **The reason this function exists.** KEER2014's finding is that thickening and warming are *purchases*, and the
    paper says the industry's move to brown outlines is exactly that purchase. A hierarchy model that only ever
    thickens the contour is spending naturalness to buy potency silently; printing the trade is the cheapest way to
    stop it being silent.
    """
    return ROLES[name].trade if name else 'no role: the brush width exactly as given, no trade declared'
