"""Does an asset carry motion? Count the places a glTF or an FBX would keep it.

**The question decides whether a model library can teach a gesture at all.** A mesh at rest is an A-pose, and an A-pose
is the one thing this project already knows the coordinates of. What teaches "the moment before the action" is a
sequence -- keyframes, a clip, an animation stack -- and if none of these files has one, then no amount of vertices will
produce it.

    python tools/anim_probe.py --root "E:\\ANMS"
"""
import argparse
import pathlib
import struct
import sys


def glb_json(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, version, length = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF':
        return None
    off = 12
    while off < min(length, len(data)):
        clen, ctype = struct.unpack_from('<II', data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            import json
            return json.loads(chunk.decode('utf-8'))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    args = ap.parse_args()
    root = pathlib.Path(args.root)

    print('  vrm -- a glTF keeps animation in an `animations` array, so its absence is conclusive')
    for p in sorted(root.rglob('*.vrm')):
        try:
            js = glb_json(p)
        except Exception as exc:
            print('    %-40s unreadable: %s' % (p.name, exc))
            continue
        anims = js.get('animations', [])
        names = [a.get('name', '?') for a in anims]
        print('    %-40s animations %d %s' % (p.name, len(anims), names[:4]))

    print()
    print('  fbx -- a binary FBX names its clips inline, so counting the marker is enough to know')
    for p in sorted(root.rglob('*.fbx')):
        raw = p.read_bytes()
        stacks = raw.count(b'AnimStack')
        curves = raw.count(b'AnimationCurve')
        deformers = raw.count(b'Deformer')
        print('    %-40s AnimStack %3d   AnimationCurve %4d   Deformer %4d'
              % (p.name, stacks, curves, deformers))

    print()
    print('  pmx -- motion lives in a separate .vmd file and never inside the model')
    for p in sorted(root.rglob('*.pmx')):
        print('    %-40s (a .vmd beside it would be the motion)' % p.name)
    vmds = list(root.rglob('*.vmd'))
    print('    .vmd files found under the root: %d' % len(vmds))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
