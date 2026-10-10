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


#: **The draw order the rigs agree on, and what they do not.** Sixty lobby rigs were dumped in slot order and every
#: draw class compared with every other; these are the pairs that came out the same way in **every rig that saw both
#: members**.
#:
#: **Sixty rigs, not nine, and the number matters.** The first version of this table was built from nine rigs and had
#: 99 pairs in it. Run against sixty, **66 of those 99 were contradicted** -- including most of the `shadow` family,
#: which turned out not to be a class at all: `Handkerchief_Shadow` sits at slot 17 and `F_Hair_Shadow_06` at 124, so
#: grouping them made the class contradict itself. A `*_Shadow` slot now takes the class of what it shadows, and the
#: relation *a shadow precedes its caster* is checked separately.
#:
#: The rows worth reading, now that only the survivors are here: **`background`, `scenery` and `halo` come before the
#: character's parts** -- the halo is drawn *behind* the character, the same halo that inflated every bounding box
#: attempted earlier. **`back_hair` before `front_hair`**, which is why hair is two layers. **`eye` before `face`
#: before `eyebrow`**. And **`mouth` before `overlay`**.
ORDER_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ('back_hair', 'front_hair'), ('back_hair', 'overlay'), ('background', 'arm'),
    ('background', 'back_hair'), ('background', 'collar'), ('background', 'eye'),
    ('background', 'eyebrow'), ('background', 'face'), ('background', 'front_hair'),
    ('background', 'halo'), ('background', 'hand'), ('background', 'head'),
    ('background', 'leg'), ('background', 'neck'), ('background', 'overlay'),
    ('background', 'prop'), ('background', 'skirt'), ('background', 'torso'),
    ('collar', 'eyebrow'), ('collar', 'mouth'), ('eye', 'eyebrow'),
    ('eye', 'face'), ('halo', 'back_hair'), ('halo', 'collar'),
    ('halo', 'eyebrow'), ('halo', 'face'), ('halo', 'front_hair'),
    ('halo', 'hand'), ('halo', 'head'), ('halo', 'mouth'),
    ('halo', 'neck'), ('halo', 'overlay'), ('halo', 'skirt'),
    ('head', 'eyebrow'), ('head', 'face'), ('head', 'mouth'),
    ('leg', 'front_hair'), ('mouth', 'overlay'), ('neck', 'eyebrow'),
    ('neck', 'face'), ('other', 'arm'), ('other', 'eye'),
    ('other', 'eyebrow'), ('other', 'face'), ('other', 'front_hair'),
    ('other', 'hand'), ('other', 'head'), ('other', 'leg'),
    ('other', 'mouth'), ('other', 'neck'), ('other', 'prop'),
    ('other', 'skirt'), ('other', 'torso'), ('prop', 'head'),
    ('prop', 'mouth'), ('scenery', 'back_hair'), ('scenery', 'collar'),
    ('scenery', 'eyebrow'), ('scenery', 'face'), ('scenery', 'front_hair'),
    ('scenery', 'halo'), ('scenery', 'hand'), ('scenery', 'head'),
    ('scenery', 'mouth'), ('scenery', 'neck'), ('scenery', 'overlay'),
    ('scenery', 'skirt'), ('skirt', 'eyebrow'), ('skirt', 'face'),
    ('skirt', 'front_hair'), ('skirt', 'head'), ('skirt', 'mouth'),
    ('torso', 'eyebrow'),
)

#: **The classes the rigs only ever place late: each has determined predecessors and no determined successor.**
#:
#: This is the shape of what the corpus does not decide, and it is more precise than saying their position is
#: unknown. Nothing is determined to come *after* an arm, a hand, a face, an eyebrow, the front hair or an overlay --
#: so **their order among themselves is exactly the part that depends on the pose**: whether a hand is in front of a
#: face, whether the front hair covers an eye, where the arms hang, what the overlays sit on.
#:
#: A draw order is partly a property of the character and partly a property of the drawing, and this list is which
#: half is which.
FLOATING: tuple[str, ...] = ('arm', 'eyebrow', 'face', 'front_hair', 'hand', 'overlay')

#: **The classes the rigs only ever place early** -- determined predecessors and no determined predecessor of their
#: own. Everything else in a drawing sits above these, which is what makes them a floor rather than a layer.
ANCHORED_BELOW: tuple[str, ...] = ('background', 'scenery')


def order_errors(stack: 'Stack') -> list[str]:
    """A proposed stack against the order the rigs agree on."""
    problems = []
    index = {}
    for i, layer in enumerate(stack.layers):
        if layer.part and layer.part in DRAW_CLASSES:
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


#: Which tier each draw class belongs to. The **order** comes from the rigs; the tier is the coarse grouping the
#: tier check speaks in, and `standard_order` seeds it in as constraints so that a derived order satisfies both.
TIER_OF_CLASS: dict[str, str] = {
    'background': 'background', 'scenery': 'scenery', 'shadow': 'cast_shadow', 'overlay': 'overlay',
}


def standard_order() -> list[str]:
    """One total order that satisfies as many of the constraints as a total order can.

    **Two sources of order, and both are obeyed.** The pairwise constraints the rigs agree on, and the tier rule --
    scenery before the character, overlays after everything -- because a stack that satisfies the first and not the
    second is a stack the tier check rejects. Without the tier rule seeded in, `overlay` has no predecessors and the
    greedy placed it *before* `front_hair` and `eyebrow`, which is not a drawing anyone would make.

    Sorted greedily by fewest unsatisfied predecessors. `unsatisfiable()` reports anything a single order cannot
    satisfy; it returns nothing here, which is worth knowing rather than assuming -- an earlier version of this
    function raised `ValueError` claiming the constraints contradict each other, and that was a bug in the sort, not
    in the data.
    """
    remaining = list(DRAW_CLASSES)
    predecessors = {}
    for a, b in ORDER_CONSTRAINTS:
        predecessors.setdefault(b, set()).add(a)
    # the tier rule, seeded in as constraints of its own
    scene = [c for c in DRAW_CLASSES if TIER_OF_CLASS.get(c) in ('background', 'scenery', 'cast_shadow')]
    character = [c for c in DRAW_CLASSES if c not in scene and c != 'overlay']
    for a in scene:
        for b in character:
            predecessors.setdefault(b, set()).add(a)
    for a in character:
        predecessors.setdefault('overlay', set()).add(a)
    order, placed = [], set()
    while remaining:
        def cost(c):
            return len(predecessors.get(c, set()) - placed)
        best = min(remaining, key=lambda c: (cost(c), DRAW_CLASSES.index(c)))
        order.append(best)
        placed.add(best)
        remaining.remove(best)
    return order


def unsatisfiable(order: list[str] | None = None) -> list[tuple[str, str]]:
    """The constraints no single total order can satisfy, given the others.

    Reported rather than hidden: a stack built from `standard_order()` breaks these, and a caller that wants one of
    them has to move a layer and accept breaking another.
    """
    order = standard_order() if order is None else order
    index = {c: i for i, c in enumerate(order)}
    return [(a, b) for a, b in ORDER_CONSTRAINTS if a in index and b in index and index[a] > index[b]]
