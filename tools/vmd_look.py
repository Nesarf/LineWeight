"""Read a VMD motion: which bones move, over which frames, and by how much.

**This is the missing half of the model library.** The meshes in ANMS say where the joints are and carry no motion at
all -- four VRM files declare no animations, and the only FBX with curve nodes has no keyframe curves under them. A VMD
is the opposite: nothing but motion, one record per bone per keyframe.

**The format, and it is fixed-width.** A 30 byte header, a 20 byte model name (10 in the older version), then a count
and that many 111 byte records -- 15 byte name, frame number, three floats of position, four of a quaternion, and 64
bytes of interpolation curves this does not read.

**What "how much" is taken to mean.** Each bone's rotation is a quaternion; the angle it turns is

    angle = 2 acos(|w|)

and the spread of that angle across a bone's keyframes is how much that joint is used. **A joint that barely changes is
a joint the pose does not lean on**, and that is the sentence a drawing needs: not "where is the elbow" but "which
joints carry this movement".

    python tools/vmd_look.py --src "G:\\KKS\\[VMD]\\walk.vmd"
"""
import argparse
import math
import struct

HEADER = 30
BONE_RECORD = 111
NAME = 15


def parse(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic = data[:25]
    if not magic.startswith(b'Vocaloid Motion Data'):
        raise ValueError('not a VMD: %r' % magic)
    version = data[:30].split(b'\x00')[0].decode('latin-1')
    name_len = 20 if version.endswith('0002') else 10
    model = data[HEADER:HEADER + name_len].split(b'\x00')[0]
    try:
        model_name = model.decode('cp932')
    except UnicodeDecodeError:
        model_name = model.decode('latin-1')
    off = HEADER + name_len
    count = struct.unpack_from('<I', data, off)[0]
    off += 4

    bones = {}
    frames = []
    for _ in range(count):
        raw = data[off:off + NAME]
        off += NAME
        try:
            bone = raw.split(b'\x00')[0].decode('cp932')
        except UnicodeDecodeError:
            bone = raw.split(b'\x00')[0].decode('latin-1')
        frame, px, py, pz, qx, qy, qz, qw = struct.unpack_from('<I3f4f', data, off)
        off += 4 + 12 + 16 + 64
        angle = 2.0 * math.acos(min(1.0, abs(qw)))
        bones.setdefault(bone, []).append((frame, angle, (px, py, pz)))
        frames.append(frame)
    return version, model_name, bones, (min(frames) if frames else 0, max(frames) if frames else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--top', type=int, default=14, help='how many bones to list, most-used first')
    ap.add_argument('--bone', default='', help='show one bone frame by frame')
    args = ap.parse_args()

    version, model_name, bones, span = parse(args.src)
    print('  %s' % args.src)
    print('  %s   model %r   bones %d   frames %d..%d (%.1f s at 30 fps)'
          % (version, model_name, len(bones), span[0], span[1], (span[1] - span[0]) / 30.0))

    stats = []
    for bone, recs in bones.items():
        angles = [a for _f, a, _p in recs]
        moves = max(p for _f, _a, p in recs)
        stats.append((bone, len(recs), min(angles), max(angles), max(angles) - min(angles), moves))
    stats.sort(key=lambda t: -t[4])

    print()
    print('    %-16s %6s %8s %8s %8s' % ('bone', 'keys', 'min deg', 'max deg', 'spread'))
    for bone, keys, lo, hi, spread, _moves in stats[:args.top]:
        print('    %-16s %6d %8.1f %8.1f %8.1f'
              % (bone, keys, math.degrees(lo), math.degrees(hi), math.degrees(spread)))

    total = sum(s[4] for s in stats)
    print()
    print('  total rotation spread over all bones: %.1f rad' % total)
    print('  bones that move less than 5 degrees: %d of %d'
          % (sum(1 for s in stats if s[4] < math.radians(5)), len(stats)))

    if args.bone:
        recs = bones.get(args.bone)
        if not recs:
            print('  no bone named %r; the names in this file are:' % args.bone)
            print('    %s' % sorted(bones)[:24])
            return 0
        recs.sort()
        print()
        print('  %s, frame by frame:' % args.bone)
        for frame, angle, pos in recs[:20]:
            print('    frame %4d  angle %6.1f deg  pos (%.2f, %.2f, %.2f)'
                  % (frame, math.degrees(angle), pos[0], pos[1], pos[2]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
