"""A described figure: a body and the layers it is drawn in, validated before anything is drawn.

**The failure this closes.** A generator that draws three arms has no representation in which that is *wrong*. It has
pixels, or marks, and no statement of what the thing was supposed to be. `Figure` is that statement: the body's
topology and the drawing's layer stack, both taken from the rigs Blue Archive ships, and **both validated before a
single mark is allowed onto the drawing**.

**Where the two halves come from, and why they are one object.** They are the two halves of the same character:

* `body.py` says what the body *is* -- twenty invariant bones, two arms, two legs, one spine, and no node a third
  limb could hang from. Read from 296 character rigs, with the vocabulary for what is costume rather than body taken
  from the same census.
* `layers.py` says what a drawing of it is *made of* -- the tier order and the part vocabulary, read from the 2D rig's
  174 slots in draw order and from the 3D asset's material list.

**A figure with a valid body and no layers is a correct body wearing nothing; a figure with layers and no body is a
pile of layers with three arms.** So `Figure` holds both and refuses to be either.

**Nothing here is about how a limb looks.** There are no positions in this module, deliberately: the census gives
topology and part vocabulary as facts, and a joint *position* would be invented. What can be checked is checked, and
what cannot is left out rather than filled in with a plausible number.
"""

from dataclasses import dataclass, field

from . import body as _body
from .layers import Stack, layer_errors, PARTS, TIERS


@dataclass
class Figure:
    """A body and a layer stack, and the errors in either."""
    joints: dict = field(default_factory=dict)
    layers: Stack = field(default_factory=Stack)
    name: str = ''

    #: A figure's body is only checked when one is declared, so an empty `Figure` is legal and means "nothing described
    #: yet" rather than "a body with no bones".
    def has_body(self) -> bool:
        return bool(self.joints)

    def errors(self) -> list[str]:
        """Everything wrong, body first. **Empty is the only state in which a figure may be drawn on.**"""
        problems = []
        if self.joints:
            problems.extend(_body.structural_errors(self.joints))
            problems.extend(_body.arity_errors(list(self.joints.items())))
            # **A body with no layers is refused here rather than at every mark.** Left implicit it would surface as
            # "no such layer (the figure has )" on the first stroke, which describes the symptom; this describes the
            # thing that is wrong -- a figure with nowhere to be drawn.
            if not self.layers.layers:
                problems.append('the figure describes a body but no layers to draw it in')
        problems.extend(layer_errors(self.layers))
        return problems

    def limb_counts(self) -> dict:
        """What the body has, counted by kind -- the summary a person wants before trusting it."""
        if not self.joints:
            return {}
        counts = {}
        for name in self.joints:
            counts[_body.kind(name)] = counts.get(_body.kind(name), 0) + 1
        return counts

    def layer_names(self) -> set:
        return {layer.name for layer in self.layers.layers}

    def parts(self) -> set:
        return {layer.part for layer in self.layers.layers if layer.part}

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'joints': dict(sorted(self.joints.items())),
            'layers': [{'name': l.name, 'tier': l.tier, 'part': l.part, 'casts_for': l.casts_for}
                       for l in self.layers.layers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Figure':
        f = cls(joints=dict(d.get('joints', {})), name=d.get('name', ''))
        for row in d.get('layers', []):
            f.layers.add(row['name'], row['tier'], row.get('part', ''), row.get('casts_for', ''))
        return f


#: Which tier each draw class belongs to, for the coarse check. The **order** comes from the rigs; the tier is the
#: grouping the earlier hand-written rule used, kept because it is what `SHADOW_BEFORE_CASTER` and the tier check
#: speak in.
TIER_OF_CLASS: dict[str, str] = {
    'background': 'background', 'scenery': 'scenery', 'shadow': 'cast_shadow',
    'overlay': 'overlay',
}


def standard() -> Figure:
    """The reference figure a generator would start from and vary.

    **Both halves come from the corpus rather than from taste.** The body is the rig's own 34-bone variant, the
    commonest in the census at 154 of 286. The layers are the twenty draw classes **topologically sorted from the 99
    order constraints nine lobby rigs agree on**, each carrying the tier its class belongs to, and each character part
    getting an outline because `_OutlineTint` is on 99% of the cast.

    What that produces is the art's own stack: background, scenery, cast shadow, the halo *behind* the character,
    back hair, head, arms, legs, skirt, torso, collar, prop, hand, neck, eyes, face, mouth, front hair, eyebrows,
    overlays.
    """
    from .layers import standard_order
    f = Figure(joints=dict(_body.JOINT_PARENT), name='standard')
    for cls in standard_order():
        # **`part` carries the draw class**, because the order is a fact about draw classes; `PART_OF_CLASS` gives the
        # material when that is what is being asked about.
        f.layers.add(cls, TIER_OF_CLASS.get(cls, 'character'), part=cls, outline=True)
    return f


def describe(figure: Figure) -> str:
    """A one-paragraph report, for a person or a log."""
    lines = ['figure %r' % (figure.name or '(unnamed)')]
    if figure.joints:
        counts = figure.limb_counts()
        lines.append('   body: %d joints -- %s' % (len(figure.joints),
                     ', '.join('%s %d' % (k, v) for k, v in sorted(counts.items()))))
    else:
        lines.append('   body: not described')
    lines.append('   layers: %d in %d tiers, parts %s'
                 % (len(figure.layers.layers), len({l.tier for l in figure.layers.layers}),
                    ', '.join(sorted(figure.parts())) or 'none'))
    problems = figure.errors()
    if problems:
        lines.append('   %d problem(s):' % len(problems))
        lines.extend('      ' + p for p in problems)
    else:
        lines.append('   no problems: this figure may be drawn on')
    return '\n'.join(lines)
