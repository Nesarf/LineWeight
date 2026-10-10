"""The body's structure, as a constraint a described figure can be checked against.

**Where this comes from.** Blue Archive ships a Unity 6-era 3D character whose Biped skeleton is a rig-family
constant: across fourteen characters with a model, **thirteen have the identical body bone set -- 34 names,
including the twelve finger bones** -- while total node count runs from 102 to 526. So the body is one spec and the
per-character difference is entirely in the costume worn on it. The table below is read from
`Airi_Original_Mesh.prefab`'s transform links rather than typed by hand.

**Why it is a module and not a note.** The failure this addresses is specific and countable: a generator that draws
three arms, or a hand at the end of a spine, or a leg growing out of the neck. Those are **topology** errors --
limb count and attachment are properties of the parent relation -- and a parent relation can be validated. Nothing
here is about how a limb *looks*; it is about what may be attached to what.

**Two checks, deliberately different in kind.**

- `structural_errors(joints)` works **by name** and is the contract: a figure described with these joint names either
  has the right parents or it does not.
- `arity_profile(parents)` works **without names at all**, and reports the shape of the tree -- how many children each
  node has, and the chain lengths. This is the one that catches an extra limb in a figure whose joints are named
  anything, because **the reference pelvis has exactly three children and the reference upper chest exactly three**,
  and an extra limb is a node with more.
"""

from collections import Counter, defaultdict

#: The 34 body joints and their parents, read from the rig. Costume, hair, face, props and the halo are deliberately
#: absent: they hang off these and vary per character (hair 7-37 nodes, skirt 12-176).
JOINT_PARENT: dict[str, str] = {
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
    'Bip001 L Toe0': 'Bip001 L Foot',
    'Bip001 R Toe0': 'Bip001 R Foot',
    # Three fingers of two segments each, against the 2D rig's five fingers of three -- the drawn hand is shown at a
    # size where all five matter and the small 3D model is not.
    'Bip001 L Finger0': 'Bip001 L Hand', 'Bip001 L Finger01': 'Bip001 L Finger0',
    'Bip001 L Finger1': 'Bip001 L Hand', 'Bip001 L Finger11': 'Bip001 L Finger1',
    'Bip001 L Finger2': 'Bip001 L Hand', 'Bip001 L Finger21': 'Bip001 L Finger2',
    'Bip001 R Finger0': 'Bip001 R Hand', 'Bip001 R Finger01': 'Bip001 R Finger0',
    'Bip001 R Finger1': 'Bip001 R Hand', 'Bip001 R Finger11': 'Bip001 R Finger1',
    'Bip001 R Finger2': 'Bip001 R Hand', 'Bip001 R Finger21': 'Bip001 R Finger2',
}

#: Where a limb may attach, and how many limbs the reference has there. **This is the whole defence against a third
#: arm**: `Spine1` carries exactly two clavicles and a neck, so the join from which arms spring has three children and
#: any fourth is a limb that no reference figure has.
ATTACHMENTS: dict[str, int] = {
    'Bip001 Pelvis': 3,      # both thighs and the spine
    'Bip001 Spine1': 3,      # both clavicles and the neck
    'Bip001 L Hand': 3,      # three fingers
    'Bip001 R Hand': 3,
}

#: The chains, each of which must be present and in this order. A missing link is a limb that does not bend.
CHAINS: dict[str, tuple[str, ...]] = {
    'spine': ('Bip001 Pelvis', 'Bip001 Spine', 'Bip001 Spine1'),
    'neck': ('Bip001 Spine1', 'Bip001 Neck', 'Bip001 Head'),
    'arm.L': ('Bip001 L Clavicle', 'Bip001 L UpperArm', 'Bip001 L Forearm', 'Bip001 L Hand'),
    'arm.R': ('Bip001 R Clavicle', 'Bip001 R UpperArm', 'Bip001 R Forearm', 'Bip001 R Hand'),
    'leg.L': ('Bip001 L Thigh', 'Bip001 L Calf', 'Bip001 L Foot', 'Bip001 L Toe0'),
    'leg.R': ('Bip001 R Thigh', 'Bip001 R Calf', 'Bip001 R Foot', 'Bip001 R Toe0'),
    'finger.L.0': ('Bip001 L Finger0', 'Bip001 L Finger01'),
    'finger.L.1': ('Bip001 L Finger1', 'Bip001 L Finger11'),
    'finger.L.2': ('Bip001 L Finger2', 'Bip001 L Finger21'),
    'finger.R.0': ('Bip001 R Finger0', 'Bip001 R Finger01'),
    'finger.R.1': ('Bip001 R Finger1', 'Bip001 R Finger11'),
    'finger.R.2': ('Bip001 R Finger2', 'Bip001 R Finger21'),
}

#: What each kind of node is for, so a report can say "arms: 3" rather than printing joint names.
KIND: dict[str, str] = {}
for _name in JOINT_PARENT:
    if 'Finger' in _name:
        KIND[_name] = 'finger'
    elif 'Clavicle' in _name or 'UpperArm' in _name or 'Forearm' in _name or _name.endswith('Hand'):
        KIND[_name] = 'arm'
    elif 'Thigh' in _name or 'Calf' in _name or _name.endswith('Foot') or _name.endswith('Toe0'):
        KIND[_name] = 'leg'
    elif _name.endswith('Neck') or _name.endswith('Head'):
        KIND[_name] = 'head'
    else:
        KIND[_name] = 'axis'


def names() -> list[str]:
    return sorted(JOINT_PARENT)


def kind(name: str) -> str:
    return KIND.get(name, 'other')


def children_of(joints: dict[str, str]) -> dict[str, list[str]]:
    """The parent map turned round. Keys are parents, values their children in sorted order."""
    kids: dict[str, list[str]] = defaultdict(list)
    for child, parent in joints.items():
        kids[parent].append(child)
    return {k: sorted(v) for k, v in kids.items()}


def structural_errors(joints: dict[str, str]) -> list[str]:
    """Everything wrong with a proposed body, by name. Empty means it is the rig's body.

    Checks, in the order a person would want to read them:

    1. **a third limb** -- more children at an attachment than the reference has there;
    2. **a limb attached to the wrong place** -- a joint whose parent is not the reference parent;
    3. **a broken chain** -- a chain that is incomplete, which is a limb that cannot bend;
    4. **a joint named here but not in the rig** -- a body part this project has no evidence for;
    5. **a cycle or a joint that is its own ancestor** -- a structure no skinned mesh can be posed from.
    """
    problems: list[str] = []
    ref = JOINT_PARENT

    # 1. extra limbs at an attachment
    kids = children_of(joints)
    for where, expected in ATTACHMENTS.items():
        if where not in joints:
            continue
        got = len(kids.get(where, []))
        named = ', '.join(kids[where])
        if got > expected:
            problems.append('%s has %d children, the rig has %d -- an extra limb (%s)'
                            % (where, got, expected, named))
        elif got < expected:
            # **A missing limb is as broken as an extra one, and the first version of this check only caught the
            # extra.** It read `if got > allowed`, so moving a thigh to the neck -- which leaves the pelvis one child
            # short -- passed the arity test and was caught only by the attachment test. Two faults, one check.
            problems.append('%s has %d children, the rig has %d -- a limb is missing'
                            % (where, got, expected))

    # 2. wrong attachment, and 4. inventing a joint
    for child, parent in sorted(joints.items()):
        if child not in ref:
            problems.append('%s is not a joint of the rig' % child)
            continue
        if child == 'Bip001':
            continue
        if parent != ref[child]:
            problems.append('%s is attached to %s, the rig attaches it to %s' % (child, parent, ref[child]))

    # 3. broken chains
    for label, chain in CHAINS.items():
        missing = [j for j in chain if j not in joints]
        if missing:
            problems.append('the %s chain is missing %s' % (label, ', '.join(missing)))
            continue
        for a, b in zip(chain, chain[1:]):
            if joints.get(b) != a:
                problems.append('the %s chain is broken between %s and %s' % (label, a, b))

    # 5. cycles
    for start in list(joints)[:200]:
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
    that share no vocabulary:

    * `children` -- how many nodes have 0, 1, 2, ... children. The reference body has three nodes with three children
      each, and that is what a third arm changes;
    * `chains` -- the length of every maximal chain from a branching point to a leaf, sorted. Extra limbs lengthen
      this list;
    * `depth` -- the longest path from a root to a leaf.
    """
    kids = defaultdict(set)
    nodes = set()
    for child, parent in parents:
        nodes.add(child)
        nodes.add(parent)
        kids[parent].add(child)
    children_hist = Counter(len(kids.get(n, ())) for n in nodes)
    # maximal chains: walk down from every branching node through single-child nodes until a leaf or a branch
    chains = []
    for n in nodes:
        for start in kids.get(n, ()):
            length = 1
            cur = start
            while len(kids.get(cur, ())) == 1 and cur not in ():
                cur = next(iter(kids[cur]))
                length += 1
                if length > len(nodes):
                    break
            chains.append(length)
    roots = [n for n in nodes if not any(n == c for c, _ in parents)]
    depth = 0
    for r in roots:
        stack = [(r, 0)]
        seen = set()
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
    """Compare a proposal's shape with the rig's, **by shape rather than by name**.

    This is the check for a figure whose joints are not named the way the rig names them -- which is the usual case
    for something a generator produced. It cannot say *which* limb is wrong, only that the tree branches more or
    less than a body does, and it says so rather than guessing.
    """
    ref = arity_profile(list(JOINT_PARENT.items()))
    got = arity_profile(proposed)
    problems = []
    if got['branching'] != ref['branching']:
        problems.append('branching counts %s, the rig has %s -- a body branches %d/%d/%d at pelvis, chest and hand'
                        % (got['branching'], ref['branching'], *ref['branching'][:3]))
    if got['nodes'] < ref['nodes']:
        problems.append('%d nodes against the rig\'s %d -- a body needs at least the axis and four limbs'
                        % (got['nodes'], ref['nodes']))
    return problems
