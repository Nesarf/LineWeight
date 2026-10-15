"""Can a character's bone positions be read out of the asset bundles?

**The question this answers before anything is built on it.** The drawing's pose is twenty hand-written coordinates.
The corpus holds 2180 character bundles and each one carries a `-prefabs-` bundle, which is where a skinned rig's
Transform components would live. **If those can be read, the invented pose can be replaced by measured ones; if they
cannot, that route is closed and it is better to know now than after building a loader around it.**

So this does one thing: opens one character's prefab bundle, lists what is inside, and looks for Transform components
with positions attached. It prints counts rather than conclusions.

    python read_rig.py character-airi_original-_mxload-prefabs-2025-07-02_assets_all_185225645.bundle
    python read_rig.py --search airi
"""
import argparse
import collections
import pathlib
import sys

BUNDLES = pathlib.Path(r'E:\~Harumi~Desuwa~\bluearchive\files\AssetBundles')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bundle', nargs='?')
    ap.add_argument('--search', default='')
    args = ap.parse_args()

    if not args.bundle:
        hits = [p for p in BUNDLES.glob('character-*prefabs*.bundle') if args.search in p.name]
        if not hits:
            print('  no prefab bundle matching %r' % args.search)
            return 1
        args.bundle = str(hits[0])

    path = pathlib.Path(args.bundle)
    if not path.exists():
        path = BUNDLES / args.bundle
    print('  %s  (%.1f MB)' % (path.name, path.stat().st_size / 1e6))

    import UnityPy
    env = UnityPy.load(str(path))

    kinds = collections.Counter()
    transforms = []
    for obj in env.objects:
        kinds[obj.type.name] += 1
        if obj.type.name in ('Transform', 'RectTransform'):
            try:
                data = obj.read()
                pos = getattr(data, 'm_LocalPosition', None)
                if pos is not None:
                    transforms.append((data.m_GameObject.read().m_Name if data.m_GameObject else '?',
                                       (pos.x, pos.y, pos.z),
                                       getattr(data, 'm_LocalRotation', None)))
            except Exception as exc:
                transforms.append(('<unreadable: %s>' % str(exc)[:40], None, None))

    print()
    print('  object kinds in this bundle:')
    for name, n in kinds.most_common(14):
        print('    %-22s %d' % (name, n))

    print()
    print('  Transform components with a local position: %d' % len(transforms))
    for name, pos, rot in transforms[:8]:
        if pos is None:
            print('    %s' % name)
        else:
            print('    %-34s (%7.3f, %7.3f, %7.3f)' % (name, pos[0], pos[1], pos[2]))
    if len(transforms) > 8:
        print('    ... and %d more' % (len(transforms) - 8))

    # **Local positions are not a pose.** Each one is measured from its parent, so a hand three bones down the arm
    # carries almost none of where the hand is. The rest pose is the composition of the chain, and that is what a
    # drawing needs -- so the hierarchy is walked here rather than the numbers being read off directly.
    world = compose(env)
    print()
    print('  the rest pose in world space, from the root out:')
    chain = ['Bip001', 'Bip001 Pelvis', 'Bip001 Spine', 'Bip001 Spine1', 'Bip001 Neck', 'Bip001 Head',
             'Bip001 L Clavicle', 'Bip001 L UpperArm', 'Bip001 L Forearm', 'Bip001 L Hand',
             'Bip001 L Thigh', 'Bip001 L Calf', 'Bip001 L Foot', 'Bip001 L Toe0',
             'Bip001 R Thigh', 'Bip001 R Calf', 'Bip001 R Foot']
    for name in chain:
        if name in world:
            x, y, z = world[name]
            print('    %-24s (%8.4f, %8.4f, %8.4f)' % (name, x, y, z))
    print('  %d bones in world space' % len(world))

    # **And the thing that decides whether this is usable**: the vertical extent and whether the arms come straight
    # out. A rest pose in these rigs is a T-pose, which no illustration is drawn in -- but a T-pose is still the
    # correct source, because it is the *shape* of the skeleton, and what a drawing needs from it is the proportions.
    ys = [p[1] for p in world.values()]
    if ys:
        print()
        print('  vertical extent: %.4f to %.4f  (height %.4f)' % (min(ys), max(ys), max(ys) - min(ys)))
    if 'Bip001 L Hand' in world and 'Bip001 L Clavicle' in world:
        hx = world['Bip001 L Hand'][0] - world['Bip001 L Clavicle'][0]
        hy = world['Bip001 L Hand'][1] - world['Bip001 L Clavicle'][1]
        print('  left hand is %.4f out and %.4f up from the clavicle -- a T-pose is all out and no up' % (hx, hy))
    print()
    print('  ** this is the skeleton shape. Whether it is a T-pose decides how it has to be used, not whether it')
    print('     can be: proportions are what a drawing takes from it. **')
    return 0


def compose(env):
    """Every Transform's world position, by walking parents **and composing the rotations**.

    Unity stores `m_LocalPosition` and a parent pointer; there is no world position in the file. **So the pose is a
    computation, not a read**, and the first version of this got it wrong in a way worth keeping: it added the local
    positions up the chain and ignored `m_LocalRotation`. The result looked like a skeleton and was not one --
    `Bip001 Pelvis`, `Spine`, `Spine1` and `Neck` all came out at the same Z and marched along negative X, because a
    child's local position is expressed in its **parent's rotated frame**. Unity's up axis is Y and the composed chain
    had no Y in it at all, which is what gave it away.

    A child's world transform is `parent_world * local`, so a local position has to be rotated by the parent's
    accumulated rotation before it is added. The quaternions are Unity's `(x, y, z, w)`.
    """
    nodes = {}
    for obj in env.objects:
        if obj.type.name not in ('Transform', 'RectTransform'):
            continue
        try:
            data = obj.read()
        except Exception:
            continue
        name = '?'
        try:
            if data.m_GameObject:
                name = data.m_GameObject.read().m_Name
        except Exception:
            pass
        parent = None
        try:
            if data.m_Father:
                parent = data.m_Father.path_id
        except Exception:
            pass
        pos = data.m_LocalPosition
        rot = getattr(data, 'm_LocalRotation', None)
        scale = getattr(data, 'm_LocalScale', None)
        nodes[obj.path_id] = (
            name, parent,
            (pos.x, pos.y, pos.z),
            (rot.x, rot.y, rot.z, rot.w) if rot is not None else (0.0, 0.0, 0.0, 1.0),
            (scale.x, scale.y, scale.z) if scale is not None else (1.0, 1.0, 1.0),
        )

    world = {}
    resolving = set()

    def locate(pid):
        if pid in world:
            return world[pid]
        if pid in resolving or pid not in nodes:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        resolving.add(pid)
        name, parent, local, rot, scale = nodes[pid]
        if parent is None or parent not in nodes:
            parent_pos, parent_rot = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)
        else:
            parent_pos, parent_rot = locate(parent)
        # **rotate the local offset by the parent's rotation, then add** -- the step the first version left out
        offset = quat_rotate(parent_rot, local)
        world_pos = (parent_pos[0] + offset[0], parent_pos[1] + offset[1], parent_pos[2] + offset[2])
        world_rot = quat_mul(parent_rot, rot)
        world[pid] = (world_pos, world_rot)
        resolving.discard(pid)
        return world[pid]

    for pid in nodes:
        locate(pid)
    return {nodes[pid][0]: world[pid][0] for pid in nodes if nodes[pid][0] != '?'}


def quat_mul(a, b):
    """Hamilton product, in Unity's (x, y, z, w) order."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def quat_rotate(q, v):
    """Rotate a vector by a quaternion, without building a matrix."""
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 * cross(q.xyz, v); v' = v + w*t + cross(q.xyz, t)
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


if __name__ == '__main__':
    raise SystemExit(main())
