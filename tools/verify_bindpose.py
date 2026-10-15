"""Check the composed skeleton against the mesh's own bind poses -- a second, independent source of the same numbers.

**Why symmetry was not enough.** Mirroring the left chain against the right catches a mistake that is introduced on one
side only. It cannot catch anything that is applied to both -- a wrong root rotation, a transposed axis, a scale
applied once -- because those leave a rig perfectly symmetric and perfectly wrong. So a check is needed that speaks to
absolute placement, and one exists in the file.

**A skinned mesh carries `m_BindPose`**: one 4x4 matrix per bone, in `m_Bones` order, and each one is **the inverse of
that bone's world transform at the moment the skin was bound**. Inverting it therefore gives the world position again,
derived from a different object with a different layout, written by a different part of Unity. **If the composition
and the bind poses agree, two independent readings of the same skeleton agree.**

    python verify_bindpose.py
"""
import importlib.util
import pathlib
import statistics
import sys

import UnityPy

BUNDLES = pathlib.Path(r'E:\~Harumi~Desuwa~\bluearchive\files\AssetBundles')
spec = importlib.util.spec_from_file_location('rr', str(pathlib.Path(__file__).parent / 'read_rig.py'))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)


def matrix_rows(m):
    """A UnityPy `Matrix4x4f` as three rows of three plus a translation.

    **The elements are named `e<row><col>` and the translation is the last column**, which is visible rather than
    assumed: `e30, e31, e32, e33` come back as `0, 0, 0, 1`, and that is only true of the bottom row. So `e03, e13,
    e23` is where the position is, and the rotation is the leading three-by-three.
    """
    r = [[m.e00, m.e01, m.e02], [m.e10, m.e11, m.e12], [m.e20, m.e21, m.e22]]
    t = [m.e03, m.e13, m.e23]
    return r, t


def invert_rigid(r, t):
    """The inverse of a rigid transform: transpose the rotation and rotate the negated translation.

    **Done this way rather than with a general matrix inverse on purpose.** A general inverse would invert anything,
    including a matrix carrying a scale that should not be there, and the point of this check is to compare world
    positions -- so the inverse is restricted to what a bind pose is allowed to be.
    """
    rt = [[r[j][i] for j in range(3)] for i in range(3)]
    tinv = [-sum(rt[i][k] * t[k] for k in range(3)) for i in range(3)]
    return tinv


def main():
    """Find a character's prefabs and meshes bundles, load them together, and compare the two sources.

    **They are two bundles and both are needed.** The rig lives in `character-<name>-...-prefabs-`, the skinned mesh
    -- which is where the bind poses are -- in `assets-_mx-characters-<name>-...-meshes-`, and the renderer in the
    first names the bones that the second supplies matrices for. `m_BindPose` is absent from the renderer's own type
    tree here: it has 34 keys and none of them mention binding. Loading both into one environment resolves the cross
    references, which was checked before this was written.
    """
    pre = [p for p in BUNDLES.glob('character-*prefabs*.bundle') if 'airi' in p.name]
    mes = [p for p in BUNDLES.glob('*characters-airi_original*meshes*.bundle')]
    if not pre or not mes:
        print('  bundles not found')
        return 1
    print('  %s' % pre[0].name[:70])
    print('  %s' % mes[0].name[:70])

    env = UnityPy.load(str(pre[0]), str(mes[0]))
    world = rr.compose(env)
    print('  %d bones composed from the hierarchy' % len(world))

    # the renderers, and the meshes they point at
    best = None
    for obj in env.objects:
        if obj.type.name != 'SkinnedMeshRenderer':
            continue
        try:
            smr = obj.read()
            bones = [b.path_id for b in smr.m_Bones]
            mesh = smr.m_Mesh.read()
            poses = list(mesh.m_BindPose)
        except Exception as exc:
            print('    renderer skipped: %s' % str(exc)[:60])
            continue
        if not poses:
            continue
        name_of = {}
        for b in smr.m_Bones:
            try:
                name_of[b.path_id] = b.read().m_GameObject.read().m_Name
            except Exception:
                pass
        rows = []
        for bone_id, pose in zip(bones, poses):
            name = name_of.get(bone_id)
            if not name or name not in world:
                continue
            r, t = matrix_rows(pose)
            tinv = invert_rigid(r, t)
            wx, wy, wz = world[name]
            d = max(abs(wx - tinv[0]), abs(wy - tinv[1]), abs(wz - tinv[2]))
            rows.append((d, name))
        if not rows:
            continue
        rows.sort()
        if best is None or len(rows) > best[1]:
            best = (getattr(mesh, 'm_Name', '?'), len(rows), rows)

    if not best:
        print('  no skinned mesh with bind poses matched')
        return 1

    mesh_name, n, rows = best
    med = statistics.median(d for d, _ in rows)
    print()
    print('  %s: %d bones matched between the bind poses and the composed hierarchy' % (mesh_name, n))
    print('  difference in world position: median %.6f   worst %.6f  (%s)' % (med, rows[-1][0], rows[-1][1]))
    print('  the ten worst:')
    for d, name in rows[-10:][::-1]:
        print('    %-32s %.6f' % (name, d))
    print()
    print('  ** a bind pose is the inverse of a bone\'s world transform at bind time, carried by the mesh rather')
    print('     than by the transform hierarchy, and it is a different object with a different layout read through a')
    print('     different code path. Agreement is what the symmetry check could not establish, because a wrong root')
    print('     rotation leaves a rig perfectly symmetric. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
