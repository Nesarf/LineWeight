"""The body's structure, as a constraint a described figure can be checked against.

**Where this comes from, and the correction a census forced.** The table below was first written from one
character -- Blue Archive's `Airi_Original`, whose Biped skeleton has 34 bones -- and then a census was run over
**all 286 characters with a 3D model**. It found the body bone count ranges from **22 to 52**, and that the module as
first written would have rejected **132 of them, 46% of the corpus**, as "inventing a joint" because they carry a
`Finger3` that the one character did not.

**What the census established instead is sharper**, and it is what this module now encodes:

* **Twenty bones are present in every single character** -- the axis and four limb chains. These are the spec.
* **Two things vary and nothing else does**: how many fingers a hand has (0, 2, 3, 4, 5 or 7, carried as 0 to 15
  finger *bones*), and whether the foot carries a toe (274 characters yes, 12 no).

```
22 bones :   1          32 bones :   6   (no toes)
34 bones : 154          36 bones :   5
38 bones :  41  (4 fingers)             40 bones :   3
42 bones :  74  (5 fingers)             52 bones :   1   (a different naming scheme)
```

**Why it is a module and not a note.** The failure this addresses is specific and countable: a generator that draws
three arms, or a hand at the end of a spine, or a leg growing out of the neck. Those are **topology** errors -- limb
count and attachment are properties of the parent relation -- and a parent relation can be validated.

**Two checks, deliberately different in kind.**

- `structural_errors(joints)` works **by name** and is the contract.
- `arity_profile(parents)` works **without names at all**, comparing the shape of the tree. **That is the one that
  works on something a generator produced**, because the reference branches 3/3/3 at pelvis, chest and hand, and a
  fourth child at the chest is a third arm whatever the joints are called.
"""

import re
from collections import Counter, defaultdict

#: **The twenty bones present in every character of the census**, and their parents. This is the invariant.
CORE_PARENT: dict[str, str] = {
    'Bip001': 'bone_root',
    'Bip001 Pelvis': 'Bip001',
    'Bip001 Spine': 'Bip001 Pelvis',
    'Bip001 Spine1': 'Bip001 Spine',
    'Bip001 Neck': 'Bip001 Spine1',
    'Bip001 Head': 'Bip001 Neck',
    'Bip001 L Clavicle': 'Bip001 Spine1',
    'Bip001 R Clavicle': 'Bip001 Spine1',
    'Bip001 L UpperArm': 'Bip001 L Clavicle',
    'Bip001 R UpperArm': 'Bip001 R Clavicle',
    'Bip001 L Forearm': 'Bip001 L UpperArm',
    'Bip001 R Forearm': 'Bip001 R UpperArm',
    'Bip001 L Hand': 'Bip001 L Forearm',
    'Bip001 R Hand': 'Bip001 R Forearm',
    'Bip001 L Thigh': 'Bip001 Pelvis',
    'Bip001 R Thigh': 'Bip001 Pelvis',
    'Bip001 L Calf': 'Bip001 L Thigh',
    'Bip001 R Calf': 'Bip001 R Thigh',
    'Bip001 L Foot': 'Bip001 L Calf',
    'Bip001 R Foot': 'Bip001 R Calf',
}

#: The reference character's full set -- 34 bones, three fingers of two segments and a toe each side. Kept because it
#: is the variant the first record was written from, and because a test wants one concrete whole body.
JOINT_PARENT: dict[str, str] = dict(CORE_PARENT, **{
    'Bip001 L Toe0': 'Bip001 L Foot',
    'Bip001 R Toe0': 'Bip001 R Foot',
    'Bip001 L Finger0': 'Bip001 L Hand', 'Bip001 L Finger01': 'Bip001 L Finger0',
    'Bip001 L Finger1': 'Bip001 L Hand', 'Bip001 L Finger11': 'Bip001 L Finger1',
    'Bip001 L Finger2': 'Bip001 L Hand', 'Bip001 L Finger21': 'Bip001 L Finger2',
    'Bip001 R Finger0': 'Bip001 R Hand', 'Bip001 R Finger01': 'Bip001 R Finger0',
    'Bip001 R Finger1': 'Bip001 R Hand', 'Bip001 R Finger11': 'Bip001 R Finger1',
    'Bip001 R Finger2': 'Bip001 R Hand', 'Bip001 R Finger21': 'Bip001 R Finger2',
})

#: Where a limb may attach, and how many limbs a body has there. **This is the whole defence against a third arm**:
#: `Spine1` carries exactly two clavicles and a neck.
ATTACHMENTS: dict[str, int] = {
    'Bip001 Pelvis': 3,      # both thighs and the spine
    'Bip001 Spine1': 3,      # both clavicles and the neck
}

#: **A body feature the census found and the first spec did not have.** `ch0303` carries `Bip001 Breast_L` and
#: `Bip001 Breast_R` hanging off `Spine1`, which made the chest read as five children against a spec that expected
#: three. They are optional -- most characters do not have them -- so they are allowed rather than required, and the
#: arity check adds however many are present to what it expects there.
OPTIONAL_ATTACHMENTS: dict[str, tuple[str, ...]] = {
    'Bip001 Spine1': ('Bip001 Breast_L', 'Bip001 Breast_R'),
}

#: The core chains, each of which must be present and in this order. A missing link is a limb that does not bend.
CHAINS: dict[str, tuple[str, ...]] = {
    'spine': ('Bip001 Pelvis', 'Bip001 Spine', 'Bip001 Spine1'),
    'neck': ('Bip001 Spine1', 'Bip001 Neck', 'Bip001 Head'),
    'arm.L': ('Bip001 L Clavicle', 'Bip001 L UpperArm', 'Bip001 L Forearm', 'Bip001 L Hand'),
    'arm.R': ('Bip001 R Clavicle', 'Bip001 R UpperArm', 'Bip001 R Forearm', 'Bip001 R Hand'),
    'leg.L': ('Bip001 L Thigh', 'Bip001 L Calf', 'Bip001 L Foot'),
    'leg.R': ('Bip001 R Thigh', 'Bip001 R Calf', 'Bip001 R Foot'),
}

#: **The two knobs the census found, as numbers.** A hand carries between 0 and 7 fingers -- the corpus uses 0, 2, 3,
#: 4, 5 and 7 -- and each finger is a chain of one or more segments. A foot may or may not carry a toe.
FINGERS_PER_HAND = (0, 2, 3, 4, 5, 7)

_FINGER = re.compile(r'Finger(\d+)')

#: **What hangs off a body joint without being part of it.** This vocabulary is taken from the census rather than
#: invented: running the check over all 286 characters and reading the rejections gave exactly these families --
#: `bone_*` costume and hair, `Xtra_*` face extras, `eye*`, twist bones, a Biped head nub, control bones
#: (`Forearm_ctrl`, `Forearm_TW`, `Clavicle02`, `Footsteps`) and skirt chains.
#:
#: **Neither a name-only nor a shape-only test works here, and the census showed why.** Naming alone misses a third
#: arm called anything unexpected; shape alone reads a pelvis carrying eight four-segment skirt chains as having eight
#: legs, because a skirt chain is as long as a limb. So: costume is a vocabulary, a limb is what is left.
COSTUME = re.compile(r'^bone_|^Bip001_|Xtra_|eye|Twist|Nub|ctrl|Footstep|_TW$|_ik$|IK$|Clavicle0\d|Helper|Locator',
                     re.I)


def is_costume(name: str) -> bool:
    """True for a bone that hangs off the body without being part of it."""
    if name in CORE_PARENT or is_finger(name) or is_toe(name):
        return False
    return bool(COSTUME.search(name))


def is_finger(name: str) -> bool:
    return bool(_FINGER.search(name))


def is_toe(name: str) -> bool:
    return name.endswith('Toe0')


def fingers_on(joints, hand: str) -> list[str]:
    """The roots of the fingers hanging off one hand, in name order. A finger's root is the bone whose parent is the
    hand itself."""
    return sorted(j for j, p in joints.items() if p == hand and is_finger(j))


def toes_on(joints, foot: str) -> list[str]:
    return sorted(j for j, p in joints.items() if p == foot and is_toe(j))


def kind(name: str) -> str:
    if is_finger(name):
        return 'finger'
    if is_toe(name):
        return 'toe'
    if re.search(r'Clavicle|UpperArm|Forearm|Hand$', name):
        return 'arm'
    if re.search(r'Thigh|Calf|Foot$', name):
        return 'leg'
    if re.search(r'Neck|Head$', name):
        return 'head'
    return 'axis'


def children_of(joints: dict[str, str]) -> dict[str, list[str]]:
    """The parent map turned round. Keys are parents, values their children in sorted order."""
    kids: dict[str, list[str]] = defaultdict(list)
    for child, parent in joints.items():
        kids[parent].append(child)
    return {k: sorted(v) for k, v in kids.items()}


def structural_errors(joints: dict[str, str]) -> list[str]:
    """Everything wrong with a proposed body, by name. Empty means it is a body this game ships.

    The core is checked strictly, because it is invariant across all 286 characters. The hand and the foot are checked
    **structurally rather than by count**, because the count is the thing that varies -- and an earlier version of this
    function got that wrong and would have rejected nearly half the corpus.

    1. **a limb count wrong in either direction** at the pelvis and the chest;
    2. **a core bone attached to the wrong place**;
    3. **a broken chain** -- a limb that cannot bend;
    4. **a core bone missing**, which is a body without that part; additions are not errors;
    5. **a finger that does not hang off a hand**, or an impossible number of them;
    6. **a cycle**.
    """
    problems: list[str] = []
    kids = children_of(joints)

    # 1. limb count, both directions -- a missing limb is as broken as a spare one.
    # **Only BODY children are counted.** The first version counted every child and so read a pelvis carrying six
    # skirt bones as having six limbs; an acceptance run over all 286 characters rejected every one of them, and 15
    # of those rejections were this. Costume, hair, face, props, twist and control bones all hang off the same joints
    # and none of them is a limb.
    def body_children(where):
        return [c for c in kids.get(where, []) if not is_costume(c)]

    for where, expected in ATTACHMENTS.items():
        if where not in joints:
            continue
        allowed_here = expected + sum(1 for o in OPTIONAL_ATTACHMENTS.get(where, ()) if o in joints)
        expected = allowed_here
        got = len(body_children(where))
        named = ', '.join(body_children(where))
        if got > expected:
            problems.append('%s has %d children, a body has %d -- an extra limb (%s)'
                            % (where, got, expected, named))
        elif got < expected:
            problems.append('%s has %d children, a body has %d -- a limb is missing'
                            % (where, got, expected))

    # 2, 4. core attachment, and the core being incomplete
    for child, parent in sorted(joints.items()):
        if child in CORE_PARENT:
            if child != 'Bip001' and parent != CORE_PARENT[child]:
                problems.append('%s is attached to %s, a body attaches it to %s'
                                % (child, parent, CORE_PARENT[child]))
        else:
            # **Anything that is not a core bone is an addition, and additions are allowed.** The rigs carry face
            # bones, hair, eight skirt chains, twist bones, control bones and a head nub, and the census found all of
            # them; `structural_errors` is about the body and has no business objecting to a costume. What it does
            # object to is a *core* bone that has been moved, renamed or removed -- which is why that check above is
            # the strict one and this one is empty.
            continue

    for core in CORE_PARENT:
        if core not in joints:
            problems.append('the core bone %s is missing' % core)

    # 3. chains
    for label, chain in CHAINS.items():
        missing = [j for j in chain if j not in joints]
        if missing:
            problems.append('the %s chain is missing %s' % (label, ', '.join(missing)))
            continue
        for a, b in zip(chain, chain[1:]):
            if joints.get(b) != a:
                problems.append('the %s chain is broken between %s and %s' % (label, a, b))

    # 5. fingers hang off hands, in a number the corpus uses
    for hand in ('Bip001 L Hand', 'Bip001 R Hand'):
        if hand not in joints:
            continue
        roots = fingers_on(joints, hand)
        if len(roots) not in FINGERS_PER_HAND:
            problems.append('%s carries %d fingers; the corpus uses %s'
                            % (hand, len(roots), ', '.join(str(n) for n in FINGERS_PER_HAND)))
    for child, parent in joints.items():
        if is_finger(child) and parent not in joints:
            problems.append('%s hangs off %s, which is not a joint' % (child, parent))

    # 6. cycles
    for start in list(joints)[:400]:
        seen = {start}
        node = joints.get(start)
        while node and node in joints:
            if node in seen:
                problems.append('%s is its own ancestor' % start)
                break
            seen.add(node)
            node = joints.get(node)

    return problems


def arity_profile(parents) -> dict:
    """The shape of a tree, **without using any name**.

    `parents` is any iterable of `(child, parent)` pairs. The profile is what can be compared between two skeletons
    that share no vocabulary: how many nodes have 0, 1, 2, ... children; the length of every maximal chain; and the
    depth. The reference branches 3/3/3 at pelvis, chest and hand, which is what a third arm changes.
    """
    kids = defaultdict(set)
    nodes = set()
    for child, parent in parents:
        nodes.add(child)
        nodes.add(parent)
        kids[parent].add(child)
    children_hist = Counter(len(kids.get(n, ())) for n in nodes)
    chains = []
    for n in nodes:
        for start in kids.get(n, ()):
            length = 1
            cur = start
            while len(kids.get(cur, ())) == 1:
                cur = next(iter(kids[cur]))
                length += 1
                if length > len(nodes):
                    break
            chains.append(length)
    roots = [n for n in nodes if not any(n == c for c, _ in parents)]
    depth = 0
    for r in roots:
        stack, seen = [(r, 0)], set()
        while stack:
            node, d = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            depth = max(depth, d)
            for c in kids.get(node, ()):
                stack.append((c, d + 1))
    return {'nodes': len(nodes), 'children': dict(sorted(children_hist.items())),
            'chains': sorted(chains, reverse=True), 'depth': depth,
            'branching': sorted((len(v) for v in kids.values() if len(v) > 1), reverse=True)}


def arity_errors(proposed) -> list[str]:
    """Compare a proposal's shape with a body's, **by shape rather than by name**.

    This is the check for a figure whose joints are not named the way the rig names them, which is the usual case for
    something a generator produced. It cannot say *which* limb is wrong, only that the tree branches more or less
    than a body does, and it says so rather than guessing.
    """
    ref = arity_profile(list(JOINT_PARENT.items()))
    got = arity_profile(proposed)
    problems = []
    if got['branching'] != ref['branching']:
        problems.append('branching counts %s, a body has %s' % (got['branching'], ref['branching']))
    if got['nodes'] < len(CORE_PARENT):
        problems.append('%d nodes against the body\'s %d core bones' % (got['nodes'], len(CORE_PARENT)))
    return problems
