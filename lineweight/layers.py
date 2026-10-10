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

#: The character's parts, from the 3D asset's material list, **with how many of 292 characters carry each**. Read off
#: the materials census rather than chosen: `Body` 285, `EyeMouth` 282, `Hair` 281, `Eyebrow` 280, `Face` 279,
#: `Halo` 219, `Weapon` 208; `Ear`, `Tail` and `Horn` zero and `Wing` one, so those are not parts of this art.
#:
#: **`EyeMouth` at 97% is the one worth keeping.** The eyes and mouth are their own material against `Face`, not
#: painted into it, and the 2D rig says the same thing with its own slots (`L_eye_01_1..3`, `Mouse_01..10`). Both
#: representations agree that a face is not one layer, and the census says it holds for nearly the whole cast.
PARTS: tuple[str, ...] = ('body', 'face', 'eyebrow', 'eye_mouth', 'hair', 'halo', 'weapon', 'prop')

#: How many of 292 characters carry each part, so a layer stack can be built from what the art actually uses rather
#: than from a guess about what a character is made of.
PART_FREQUENCY: dict[str, int] = {
    'body': 285, 'eye_mouth': 282, 'hair': 281, 'eyebrow': 280, 'face': 279, 'halo': 219, 'weapon': 208,
}

#: **The parts every character has**, which is what a default figure should be built from. `halo` and `weapon` are
#: below it because a quarter and a third of the cast do without them.
UNIVERSAL_PARTS: tuple[str, ...] = ('body', 'eye_mouth', 'hair', 'eyebrow', 'face')

#: **The parts whose outline the asset states separately -- which is all of them, and the outline is a PROPERTY of a
#: part rather than a layer of the drawing.**
#:
#: This was wrong here first, and building the standard figure is what showed it. The material carries `_OutlineTint`,
#: so the outline was modelled as an extra `<part>.outline` layer. But the 2D rig's **174 slots contain no
#: `*_Outline` slot at all**, and the 3D asset has **`_OutlineTex` = 0 across the whole corpus** -- the line is a
#: parameter the part is drawn with, and in 2D it is painted into each slot's own artwork. So it is an attribute here
#: (`Layer.outline`) and not a stack entry.
OUTLINED: tuple[str, ...] = PARTS

#: **How the material vocabulary maps onto the drawing vocabulary.** They are at different levels -- eight materials,
#: twenty draw classes -- and this is the correspondence: the `Body` material covers the torso, arms, legs, hands,
#: neck and head; `EyeMouth` covers `eye` and `mouth`; `Hair` covers `back_hair` and `front_hair`.
PART_OF_CLASS: dict[str, str] = {
    'torso': 'body', 'arm': 'body', 'leg': 'body', 'hand': 'body', 'neck': 'body', 'head': 'body',
    'eye': 'eye_mouth', 'mouth': 'eye_mouth',
    'back_hair': 'hair', 'front_hair': 'hair',
    'face': 'face', 'eyebrow': 'eyebrow', 'halo': 'halo',
    'prop': 'prop',
}

#: A cast shadow is drawn **before** what casts it — `Handkerchief_Shadow` is slot 17 and `Handkerchief` is 18;
#: `Airi_Shadow` is 19 and the character follows. This is the opposite of how a shading pass works, and it is what
#: makes a shadow an object in its own right rather than a darkening of one.
SHADOW_BEFORE_CASTER = True


@dataclass
class Layer:
    """One layer of a drawing: a name, a tier, its draw class, and whether it is drawn with its own line.

    **`part` holds a draw class, from `DRAW_CLASSES`, not a material.** The two vocabularies are at different levels
    -- eight materials against twenty draw classes -- and the *order* is a fact about the draw classes, so that is what
    a layer carries; `PART_OF_CLASS` maps it back up when the material-level question is asked.

    This was wrong here first and the order check silently did nothing: `part` held the material, so `back_hair` and
    `front_hair` both indexed as `hair`, `setdefault` kept the first, and every hair constraint compared a layer with
    itself. Moving the back hair to the top of the stack reported no violation.

    `outline` is an attribute rather than a layer because that is what the evidence says -- see `OUTLINED`.
    """
    name: str
    tier: str
    part: str = ''
    casts_for: str = ''
    outline: bool = True

    def __post_init__(self):
        if self.tier not in TIERS:
            raise ValueError('unknown tier %r; known are %s' % (self.tier, ', '.join(TIERS)))


@dataclass
class Stack:
    """An ordered layer list, bottom first, which is the order it is drawn in."""
    layers: list = field(default_factory=list)

    def add(self, name, tier, part='', casts_for='', outline=True):
        self.layers.append(Layer(name, tier, part, casts_for, outline))
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

    # 3. every part of the character is drawn with its own line. **An attribute, not a layer**: the rigs have no
    #    outline slot and the asset has no outline texture, so a part drawn without a line is a part the art does not
    #    have rather than a layer someone forgot.
    for layer in stack.layers:
        if layer.part and layer.tier == 'character' and not layer.outline:
            problems.append('the %s is drawn without an outline, and every part of the art has one' % layer.part)

    tiers_of = {}
    for layer in stack.layers:
        if layer.part:
            tiers_of.setdefault(layer.part, set()).add(layer.tier)
    for part, tiers in sorted(tiers_of.items()):
        if len(tiers) > 1:
            problems.append('the %s is drawn in %d tiers (%s)' % (part, len(tiers), ', '.join(sorted(tiers))))

    # 5. the order the nine rigs agree on
    problems.extend(order_errors(stack))

    return problems


#: **The draw order the rigs agree on, as pairs rather than as one list.** Nine lobby rigs were dumped in slot order
#: and every part class compared with every other; these are the pairs whose order is the same in **every rig that has
#: both members**. They are a partial order because the data is one -- four of the nine rigs are small enough that
#: most pairs never co-occur, and inventing a single linear order from that would be inventing.
#:
#: The rows worth reading:
#:
#: * **`scenery` before everything** and **`shadow` before the character parts**, which is the hand-written tier rule
#:   confirmed from data;
#: * **`halo` before `back_hair`, `collar`, `leg`, `skirt`** -- **the halo is drawn behind the character.** That is a
#:   fact this project did not have, and it is the same halo that inflated every bounding box attempted earlier;
#: * **`back_hair` before `front_hair` and `head`** -- the back hair is behind the body and the front hair is in
#:   front of it, which is why hair is two layers and not one;
#: * **`eye` before `face` before `eyebrow`** -- eyebrows are drawn over both;
#: * **`mouth` has nothing after it but `overlay`**, so the mouth is the last of the character's own parts.
ORDER_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ('scenery', 'shadow'), ('scenery', 'halo'), ('scenery', 'back_hair'), ('scenery', 'head'),
    ('scenery', 'arm'), ('scenery', 'leg'), ('scenery', 'skirt'), ('scenery', 'torso'),
    ('scenery', 'collar'), ('scenery', 'hand'), ('scenery', 'prop'), ('scenery', 'neck'),
    ('scenery', 'eye'), ('scenery', 'face'), ('scenery', 'mouth'), ('scenery', 'eyebrow'),
    ('scenery', 'front_hair'), ('scenery', 'overlay'),
    ('shadow', 'arm'), ('shadow', 'leg'), ('shadow', 'skirt'), ('shadow', 'torso'), ('shadow', 'collar'),
    ('shadow', 'hand'), ('shadow', 'prop'), ('shadow', 'neck'), ('shadow', 'eye'), ('shadow', 'face'),
    ('shadow', 'mouth'), ('shadow', 'eyebrow'), ('shadow', 'front_hair'), ('shadow', 'overlay'),
    ('halo', 'back_hair'), ('halo', 'collar'), ('halo', 'leg'), ('halo', 'skirt'), ('halo', 'mouth'),
    ('halo', 'prop'),
    ('back_hair', 'head'), ('back_hair', 'collar'), ('back_hair', 'neck'), ('back_hair', 'eye'),
    ('back_hair', 'face'), ('back_hair', 'mouth'), ('back_hair', 'eyebrow'), ('back_hair', 'front_hair'),
    ('back_hair', 'overlay'), ('back_hair', 'prop'),
    ('arm', 'leg'), ('arm', 'skirt'), ('arm', 'collar'), ('arm', 'hand'), ('arm', 'prop'), ('arm', 'mouth'),
    ('leg', 'skirt'), ('leg', 'torso'), ('leg', 'collar'), ('leg', 'hand'), ('leg', 'prop'), ('leg', 'neck'),
    ('leg', 'eye'), ('leg', 'face'), ('leg', 'mouth'), ('leg', 'eyebrow'), ('leg', 'overlay'),
    ('skirt', 'torso'), ('skirt', 'collar'), ('skirt', 'neck'), ('skirt', 'eye'), ('skirt', 'face'),
    ('skirt', 'mouth'), ('skirt', 'eyebrow'), ('skirt', 'overlay'), ('skirt', 'prop'),
    ('prop', 'hand'), ('prop', 'neck'), ('prop', 'eye'), ('prop', 'face'), ('prop', 'mouth'),
    ('prop', 'eyebrow'), ('prop', 'overlay'),
    ('collar', 'eye'), ('collar', 'face'), ('collar', 'mouth'), ('collar', 'eyebrow'), ('collar', 'overlay'),
    ('neck', 'eye'), ('neck', 'face'), ('neck', 'mouth'), ('neck', 'eyebrow'), ('neck', 'overlay'),
    ('eye', 'face'), ('eye', 'mouth'), ('eye', 'eyebrow'), ('eye', 'overlay'),
    ('face', 'mouth'), ('face', 'eyebrow'), ('face', 'overlay'),
    ('mouth', 'overlay'),
)



def order_errors(stack: 'Stack') -> list[str]:
    """A proposed stack against the order the rigs agree on."""
    problems = []
    index = {}
    for i, layer in enumerate(stack.layers):
        if layer.part:
            index.setdefault(layer.part, i)
    for before, after in ORDER_CONSTRAINTS:
        if before in index and after in index and index[before] > index[after]:
            problems.append('%s is drawn after %s, and the rigs draw it before' % (before, after))
    return problems


#: **The drawing's own vocabulary, which is finer than the material's.** A material is `hair`; a drawing has
#: `back_hair` and `front_hair`, drawn at opposite ends of the stack. A material is `face`; a drawing has `face`,
#: `eye`, `mouth` and `eyebrow`. **The two vocabularies sit at different levels on purpose** -- eight materials
#: against 174 slots -- and `Layer.part` takes one of these, because it is the draw order that is being checked.
DRAW_CLASSES: tuple[str, ...] = (
    'background', 'scenery', 'shadow', 'halo', 'back_hair', 'head', 'torso', 'arm', 'leg', 'skirt',
    'collar', 'hand', 'prop', 'neck', 'eye', 'face', 'mouth', 'front_hair', 'eyebrow', 'overlay',
)


def standard_order() -> list[str]:
    """A layer order that satisfies every constraint the rigs agree on.

    **Topologically sorted rather than written out**, so that it cannot drift from `ORDER_CONSTRAINTS`: a constraint
    added there changes this, and constraints that contradict each other raise rather than quietly producing an order
    that breaks one of them.

    The free set is *"every class that must precede this one is already placed"*. The first version asked whether any
    placed class listed it as a successor -- which stays true after the predecessor is placed, so it stalled on the
    first constrained class and the report blamed the data for a cycle the data does not have.
    """
    remaining = list(DRAW_CLASSES)
    predecessors = {}
    for a, b in ORDER_CONSTRAINTS:
        predecessors.setdefault(b, set()).add(a)
    order = []
    placed = set()
    while remaining:
        free = [c for c in remaining if predecessors.get(c, set()) <= placed]
        if not free:
            raise ValueError('the order constraints contradict each other; stuck with %s' % ', '.join(remaining))
        pick = free[0]
        order.append(pick)
        placed.add(pick)
        remaining.remove(pick)
    return order
