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
from .cel import Palette, SHADOW_STEPS
from .layers import Stack, layer_errors, PARTS, PART_OF_CLASS, TIERS


@dataclass
class Figure:
    """A body, a layer stack, and the colour specification for its parts.

    **The three belong together because the production hands them over together.** J.C.STAFF's 仕上げ department
    describes a 色指定表 that names the colour *"for each character part and each shadow"*, and Ghibli's diary
    describes the animator drawing the boundary and the colour designer specifying what goes inside it. So a figure
    is not just a skeleton and an order: it is also **which colour each of its parts is, and how many bands of shadow
    the work is drawn in**.

    **The shadow REGIONS are not here, and that is deliberate.** A region belongs to one drawing of the figure -- a
    pose, a light direction, a cut -- while the palette and the step count belong to the character. Ghibli's own diary
    says the amount of shadow 「作品によって様々」, varies by work, and the 色指定表 is per character. So `Shadow`
    lives with whatever is being drawn and `Palette` lives here.
    """
    joints: dict = field(default_factory=dict)
    layers: Stack = field(default_factory=Stack)
    name: str = ''
    #: The 色指定表: one `Palette` per material part, keyed by the part names `layers.PARTS` defines.
    palettes: dict = field(default_factory=dict)
    #: How many bands of shadow this work is drawn in. **0 is 影無し**, an ordinary production choice.
    shadow_steps: int = 1

    #: A figure's body is only checked when one is declared, so an empty `Figure` is legal and means "nothing described
    #: yet" rather than "a body with no bones".
    def has_body(self) -> bool:
        return bool(self.joints)

    def palette_for(self, part: str) -> Palette | None:
        return self.palettes.get(part)

    def palette_for_class(self, draw_class: str) -> Palette | None:
        """The palette governing a draw layer, looked up through the class-to-material mapping.

        A drawing has twenty draw classes and a colour specification has eight parts -- `back_hair` and `front_hair`
        are one material, `eye` and `mouth` are another -- so a layer's colour is its part's, not its own.
        """
        part = PART_OF_CLASS.get(draw_class)
        return self.palettes.get(part) if part else None

    def errors(self) -> list[str]:
        """Everything wrong, body first. **Empty is the only state in which a figure may be drawn on.**"""
        problems = []
        if self.shadow_steps not in SHADOW_STEPS:
            problems.append('shadow_steps must be one of %s, got %r -- 0 is 影無し, an ordinary choice'
                            % (', '.join(str(n) for n in SHADOW_STEPS), self.shadow_steps))
        for part, palette in sorted(self.palettes.items()):
            if part not in PARTS:
                problems.append('%r is not a part; the vocabulary is %s' % (part, ', '.join(PARTS)))
                continue
            # **The step count is a property of the work and the palette is a property of the part, so the two
            # have to agree.** A figure drawn in two bands whose face carries one shade would leave the second band
            # with nothing to paint, and that is checkable here rather than at the first missing colour.
            if palette.steps != self.shadow_steps:
                problems.append('the %s has %d shade(s) and the figure is drawn in %d band(s)'
                                % (part, palette.steps, self.shadow_steps))
            if self.shadow_steps == 0 and palette.steps:
                problems.append('the %s has shades but the figure is 影無し' % part)
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
            'layers': [{'name': l.name, 'tier': l.tier, 'part': l.part, 'casts_for': l.casts_for,
                        'outline': l.outline} for l in self.layers.layers],
            'shadow_steps': self.shadow_steps,
            'palettes': {part: {'lit': list(p.lit), 'shades': [list(s) for s in p.shades]}
                         for part, p in sorted(self.palettes.items())},
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Figure':
        f = cls(joints=dict(d.get('joints', {})), name=d.get('name', ''),
                shadow_steps=int(d.get('shadow_steps', 1)))
        for row in d.get('layers', []):
            f.layers.add(row['name'], row['tier'], row.get('part', ''), row.get('casts_for', ''),
                         row.get('outline', True))
        for part, p in (d.get('palettes') or {}).items():
            f.palettes[part] = Palette(lit=tuple(p['lit']), shades=[tuple(s) for s in p.get('shades', [])])
        return f


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
    from .layers import standard_order, TIER_OF_CLASS
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
    lines.append('   shadow: %s' % ('影無し (no shadow)' if figure.shadow_steps == 0
                                    else '%d band(s)' % figure.shadow_steps))
    if figure.palettes:
        lines.append('   palette: %s' % ', '.join('%s %d shade(s)' % (p, v.steps)
                                                  for p, v in sorted(figure.palettes.items())))
    else:
        lines.append('   palette: not specified')
    problems = figure.errors()
    if problems:
        lines.append('   %d problem(s):' % len(problems))
        lines.extend('      ' + p for p in problems)
    else:
        lines.append('   no problems: this figure may be drawn on')
    return '\n'.join(lines)
