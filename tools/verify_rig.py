"""Two independent checks on the composed skeleton, since the Editor cannot be used headless.

**Why a check is owed here at all.** The rest pose was read with UnityPy, whose field layouts are gated by engine
version, and the bundles declare **2021.3.56f2** while the Editor on this machine is **2022.3.22f1c1**. A parser
reading the wrong layout for its version returns wrong numbers without complaining -- which is the failure this whole
stretch of work keeps meeting. The authoritative check would be Unity itself, and that route is closed: the Editor
exits with code 199 because its licensing client cannot be reached headless.

**So two checks that do not need Unity:**

  * **Symmetry.** A character rig is symmetric about X. If the quaternion composition were wrong, the left and right
    chains would stop mirroring each other -- and symmetry is a property of the *answer*, not of the parser, so it
    tests the result rather than the method.
  * **The type tree.** A Unity bundle carries an embedded description of its own field layout, and UnityPy can read
    objects through that instead of through its built-in classes. **Those are two different parsers for the same
    bytes**, and if they agree the version-gated concern is answered for this field.

    python verify_rig.py
"""
import collections
import importlib.util
import pathlib
import statistics
import sys

import UnityPy

BUNDLES = pathlib.Path(r'E:\~Harumi~Desuwa~\bluearchive\files\AssetBundles')
spec = importlib.util.spec_from_file_location('rr', str(pathlib.Path(__file__).parent / 'read_rig.py'))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

PAIRS = [('Bip001 L Hand', 'Bip001 R Hand'), ('Bip001 L Foot', 'Bip001 R Foot'),
         ('Bip001 L Thigh', 'Bip001 R Thigh'), ('Bip001 L Calf', 'Bip001 R Calf'),
         ('Bip001 L UpperArm', 'Bip001 R UpperArm'), ('Bip001 L Forearm', 'Bip001 R Forearm'),
         ('Bip001 L Toe0', 'Bip001 R Toe0'), ('Bip001 L Clavicle', 'Bip001 R Clavicle')]


def check_symmetry(world, name):
    """Left against right: X should be equal and opposite, Y and Z equal."""
    rows = []
    for left, right in PAIRS:
        if left in world and right in world:
            lx, ly, lz = world[left]
            rx, ry, rz = world[right]
            rows.append((left.replace('Bip001 L ', ''), abs(lx + rx), abs(ly - ry), abs(lz - rz)))
    return rows


def check_typetree(path):
    """The same Transform, read through the embedded type tree instead of the built-in class.

    **This is the check that speaks to the version question.** UnityPy's built-in classes are written against
    particular engine layouts; the type tree travels with the bundle and describes the layout the file actually has.
    Reading one Transform both ways and comparing the numbers is therefore a test of the parser against the file's
    own description of itself, with no reference to any Unity version.
    """
    env = UnityPy.load(str(path))
    results = []
    for obj in env.objects:
        if obj.type.name != 'Transform':
            continue
        try:
            by_class = obj.read()
            pos_class = (by_class.m_LocalPosition.x, by_class.m_LocalPosition.y, by_class.m_LocalPosition.z)
        except Exception as exc:
            results.append(('class read failed: %s' % str(exc)[:40], None, None))
            continue
        try:
            tree = obj.read_typetree()
            p = tree.get('m_LocalPosition', {})
            pos_tree = (p.get('x'), p.get('y'), p.get('z'))
        except Exception as exc:
            results.append(('typetree read failed: %s' % str(exc)[:40], pos_class, None))
            continue
        if None in pos_tree:
            results.append(('typetree had no position', pos_class, None))
            continue
        diff = max(abs(a - b) for a, b in zip(pos_class, pos_tree))
        results.append(('ok', pos_class, diff))
        if len(results) >= 40:
            break
    return results


def main():
    files = sorted(BUNDLES.glob('character-*prefabs*.bundle'))
    print('  %d character prefab bundles' % len(files))

    sample = files[:6]
    print()
    print('  symmetry, over %d characters (these are absolute departures from a mirror):' % len(sample))
    print('    %-12s %10s %10s %10s' % ('bone', 'X diff', 'Y diff', 'Z diff'))
    allrows = collections.defaultdict(list)
    counts = []
    for p in sample:
        env = UnityPy.load(str(p))
        world = rr.compose(env)
        bip = {k: v for k, v in world.items() if k.startswith('Bip001')}
        counts.append(len(bip))
        for bone, dx, dy, dz in check_symmetry(world, p.stem):
            allrows[bone].append((dx, dy, dz))
    for bone, rows in allrows.items():
        print('    %-12s %10.4f %10.4f %10.4f'
              % (bone, statistics.median(r[0] for r in rows),
                 statistics.median(r[1] for r in rows), statistics.median(r[2] for r in rows)))
    print('    Bip001 bone counts: %s' % counts)
    print('    ** a rig is symmetric about X, so these should be near zero. If the quaternion composition were')
    print('       wrong they would not be, and the composition is what is being questioned. **')

    print()
    print('  the same Transform read through the class and through the embedded type tree:')
    for p in sample[:2]:
        rows = check_typetree(p)
        ok = [r for r in rows if r[0] == 'ok']
        bad = [r for r in rows if r[0] != 'ok']
        worst = max((r[2] for r in ok), default=0.0)
        print('    %-44s %3d compared, %d failed, worst difference %.9f'
              % (p.name[:44], len(ok), len(bad), worst))
        for r in bad[:3]:
            print('        %s' % r[0])
    print()
    print('  ** the type tree travels with the bundle and describes the layout the file actually has, so agreement')
    print('     here is a test of the parser against the file rather than against one Unity version. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
