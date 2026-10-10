"""The layers a drawing of a character is made of, and the order they go in.

**Where this comes from.** Two places, both measured, and they agree.

* The **2D rig**: Blue Archive's Spine lobby art for one character is **174 slots**, and Spine stores them **in draw
  order**. Reading them from slot 0 upward gives the artist's stack directly, and the bottom of it is
  `BG_01 → SakuraTree → Flower_14..01 → Handkerchief_Shadow → Handkerchief → Airi_Shadow → TreeShadow_01..21 → …` —
  background, then scenery, then this painting's own cast shadows, and only then the character.
* The **3D asset** for the same character carries **six materials** — `Body`, `Face`, `EyeMouth`, `Hair`, `Eyebrow`,
  `Halo`, plus weapon and prop — and each one carries its own `_OutlineTint`, `_OutlineZCorrection` and
  `_Adjustive…Shadow`. So per-part outline and per-part shadow adjustment are properties of the part, not of the
  drawing.

**Why this is a module and not a note.** The failure it addresses is the other half of the one `body.py` addresses: a
generator with a correct skeleton and no layer model produces a body wearing nothing, and one with layers and no
skeleton produces a pile of them with three arms. **Layering is a property of an ordered list**, and an ordered list
can be validated — a scenery layer over the character, a part with no outline, or a cast shadow drawn after the thing
casting it are all detectable.
"""

from dataclasses import dataclass, field

#: The tiers, bottom first, with the evidence for each. Measured from the Spine draw order; the numbers are slot
#: indices in that rig for one character, and are given so the reader can check the claim rather than take it.
TIERS: tuple[str, ...] = ('background', 'scenery', 'cast_shadow', 'character', 'overlay')

#: Slot index evidence for the tier order, from `airi_home`. Not every slot, the ones that fix the boundary.
TIER_EVIDENCE: dict[str, str] = {
    'background': 'BG_01 at slot 0',
    'scenery': 'SakuraTree_06 at slot 1, Flower_14..01 at slots 3-16',
    'cast_shadow': 'Handkerchief_Shadow at slot 17, Airi_Shadow at 19, TreeShadow_01..21 from 20',
    'character': 'the character slots follow the shadows',
}

#: The character's parts, from the 3D asset's material list. **Each is a part of the drawing, not a shading step.**
#: `EyeMouth` being its own material against `Face` is the one worth noticing: the eyes and mouth are not painted into
#: the face, they are a layer above it, and in the 2D rig they are separate slots (`L_eye_01_1..3`, `Mouse_01..10`).
PARTS: tuple[str, ...] = ('body', 'face', 'eyebrow', 'eye_mouth', 'hair', 'halo', 'weapon', 'prop')

#: Parts whose outline the asset states separately, i.e. every one of them. Kept as data because the check is
#: "every part has an outline", and that needs the list rather than a rule.
OUTLINED: tuple[str, ...] = PARTS

#: A cast shadow is drawn **before** what casts it — `Handkerchief_Shadow` is slot 17 and `Handkerchief` is 18;
#: `Airi_Shadow` is 19 and the character follows. This is the opposite of how a shading pass works, and it is what
#: makes a shadow an object in its own right rather than a darkening of one.
SHADOW_BEFORE_CASTER = True


@dataclass
class Layer:
    """One layer of a drawing: a name, a tier, and what it belongs to."""
    name: str
    tier: str
    part: str = ''
    casts_for: str = ''

    def __post_init__(self):
        if self.tier not in TIERS:
            raise ValueError('unknown tier %r; known are %s' % (self.tier, ', '.join(TIERS)))


@dataclass
class Stack:
    """An ordered layer list, bottom first, which is the order it is drawn in."""
    layers: list = field(default_factory=list)

    def add(self, name, tier, part='', casts_for=''):
        self.layers.append(Layer(name, tier, part, casts_for))
        return self

    def tier_of(self, name):
        for layer in self.layers:
            if layer.name == name:
                return layer.tier
        return None

    def index_of(self, name):
        for i, layer in enumerate(self.layers):
            if layer.name == name:
                return i
        return None


def layer_errors(stack: 'Stack') -> list[str]:
    """Everything wrong with a proposed layer stack. Empty means it is ordered like the rig.

    1. **A tier out of order** -- scenery drawn over the character, or a shadow tier above it. The tier order is the
       one thing the rig states unambiguously, because it is stored as an order.
    2. **A cast shadow drawn after its caster.** Measured, not assumed: `Handkerchief_Shadow` is slot 17 and
       `Handkerchief` is 18.
    3. **A part with no outline.** Every material in the 3D asset carries `_OutlineTint`, so a part drawn without one
       is a part the asset does not have.
    4. **A part drawn in two tiers**, which is a part split across the stack -- the thing that makes a drawing come
       apart when something moves.
    """
    problems = []
    order = {t: i for i, t in enumerate(TIERS)}

    previous = -1
    for layer in stack.layers:
        here = order[layer.tier]
        if here < previous:
            problems.append('%s is %s but comes after a %s layer'
                            % (layer.name, layer.tier, TIERS[previous]))
        previous = max(previous, here)

    if SHADOW_BEFORE_CASTER:
        for layer in stack.layers:
            if not layer.casts_for:
                continue
            caster = stack.index_of(layer.casts_for)
            shadow = stack.index_of(layer.name)
            if caster is not None and shadow is not None and shadow > caster:
                problems.append('the shadow %s is drawn after %s, which casts it' % (layer.name, layer.casts_for))

    drawn = {layer.part for layer in stack.layers if layer.part}
    for part in OUTLINED:
        if part in drawn and ('%s.outline' % part) not in {layer.name for layer in stack.layers}:
            problems.append('the %s has no outline layer' % part)

    tiers_of = {}
    for layer in stack.layers:
        if layer.part:
            tiers_of.setdefault(layer.part, set()).add(layer.tier)
    for part, tiers in sorted(tiers_of.items()):
        if len(tiers) > 1:
            problems.append('the %s is drawn in %d tiers (%s)' % (part, len(tiers), ', '.join(sorted(tiers))))

    return problems
