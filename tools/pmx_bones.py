"""Read the bone table out of a PMX model: names, rest positions, parents.

**Why a bone table and nothing else.** A VMD records one local rotation per bone per keyframe; to turn that into a pose
the rotations have to be composed down a hierarchy, and a hierarchy needs rest positions. Those are in the model, and
**the mesh is not**: this reads the header, skips the vertices, faces, textures and materials, and stops after the bones,
because nothing past them is needed to place a joint.

**The format, briefly.** `PMX ` and a version, then a byte saying how many global settings follow, then those settings --
including the text encoding and the width of each kind of index, which differ between files. Everything after that is
lengths and records, so the only hard part is knowing each record's shape well enough to step over it.

    python tools/pmx_bones.py --src "E:\\ANMS\\Rindo...\\RINDO_Full.pmx" --top 24
"""
import argparse
import struct

#: Bone flags, and only the ones that make a record a different length matter here.
FLAG_TAIL_IS_BONE = 0x0001
FLAG_IK = 0x0020
FLAG_GRANT_ROTATION = 0x0080
FLAG_GRANT_TRANSLATION = 0x0100
FLAG_FIXED_AXIS = 0x0200
FLAG_LOCAL_AXIS = 0x0400
FLAG_EXTERNAL_PARENT = 0x1000


class Reader:
    def __init__(self, data):
        self.data = data
        self.off = 0
        self.encoding = 'utf-16-le'
        self.sizes = {'vertex': 4, 'texture': 4, 'material': 4, 'bone': 4, 'morph': 4, 'rigid': 4}

    def take(self, n):
        chunk = self.data[self.off:self.off + n]
        if len(chunk) != n:
            raise ValueError('ran out of data at %d wanting %d bytes' % (self.off, n))
        self.off += n
        return chunk

    def u8(self):
        return self.take(1)[0]

    def i32(self):
        return struct.unpack('<i', self.take(4))[0]

    def u32(self):
        return struct.unpack('<I', self.take(4))[0]

    def f32(self):
        return struct.unpack('<f', self.take(4))[0]

    def floats(self, n):
        return list(struct.unpack('<%df' % n, self.take(4 * n)))

    def text(self):
        n = self.i32()
        raw = self.take(n)
        return raw.decode(self.encoding, errors='replace')

    def index(self, kind):
        """A signed index whose width the header chose.

        **PMX indices are zero-based and are not offset**, and this function used to subtract one from every one of
        them. The symptom was not a crash: every bone pointed at its predecessor, so the left wrist's parent came back
        as the bone added just before the left shoulder and the arm chain was a ring of strangers. Rest positions were
        right, which is why it read as a kinematics bug rather than a parsing one.
        """
        size = self.sizes[kind]
        raw = self.take(size)
        if size == 1:
            value = struct.unpack('<b', raw)[0]
        elif size == 2:
            value = struct.unpack('<h', raw)[0]
        else:
            value = struct.unpack('<i', raw)[0]
        return value if value >= 0 else -1


def parse(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] != b'PMX ':
        raise ValueError('not a PMX: %r' % data[:4])
    r = Reader(data)
    r.off = 4
    version = r.f32()
    globals_count = r.u8()
    settings = [r.u8() for _ in range(globals_count)]
    r.encoding = 'utf-16-le' if settings[0] == 0 else 'utf-8'
    keys = ['vertex', 'texture', 'material', 'bone', 'morph', 'rigid']
    for i, key in enumerate(keys):
        r.sizes[key] = settings[2 + i]
    add_uv = settings[1]

    name = r.text()
    r.text()
    r.text()
    r.text()

    # vertices: skipped, and the skip has to know the weight type because that is what varies in length
    for _ in range(r.u32()):
        r.take(12 + 12 + 8 + 16 * add_uv)
        kind = r.u8()
        if kind == 0:
            r.index('bone')
        elif kind == 1:
            r.index('bone'); r.index('bone'); r.take(4)
        elif kind == 2:
            for _ in range(4):
                r.index('bone')
            r.take(16)
        elif kind == 3:
            r.index('bone'); r.index('bone'); r.take(4 + 36)
        elif kind == 4:
            for _ in range(4):
                r.index('bone')
            r.take(16)
        else:
            raise ValueError('unknown weight type %d' % kind)
        r.take(4)

    r.take(4 * r.u32())          # face indices
    for _ in range(r.u32()):     # texture names
        r.text()

    for _ in range(r.u32()):     # materials
        r.text(); r.text()
        r.take(16 + 12 + 4 + 12)
        flags = r.u8()
        r.take(16 + 4)
        r.index('texture'); r.index('texture')
        r.u8()
        if r.u8() == 1:
            r.index('texture')
        else:
            r.u8()
        r.text()
        r.u32()

    bones = []
    count = r.u32()
    for _ in range(count):
        jp = r.text()
        en = r.text()
        pos = r.floats(3)
        parent = r.index('bone')
        r.i32()
        flags = struct.unpack('<H', r.take(2))[0]
        if flags & FLAG_TAIL_IS_BONE:
            r.index('bone')
        else:
            r.take(12)
        if flags & (FLAG_GRANT_ROTATION | FLAG_GRANT_TRANSLATION):
            r.index('bone')
            r.take(4)
        if flags & FLAG_FIXED_AXIS:
            r.take(12)
        if flags & FLAG_LOCAL_AXIS:
            r.take(24)
        if flags & FLAG_EXTERNAL_PARENT:
            r.take(4)
        if flags & FLAG_IK:
            r.index('bone')
            r.i32()
            r.take(4)
            links = r.i32()
            for _ in range(links):
                r.index('bone')
                if r.u8():
                    r.take(24)
        bones.append({'name': jp, 'english': en, 'pos': pos, 'parent': parent})
    return version, name, bones, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--top', type=int, default=24)
    ap.add_argument('--find', default='', help='print the rest position and parent of one bone')
    args = ap.parse_args()

    version, name, bones, _r = parse(args.src)
    print('  %s' % args.src)
    print('  PMX version %.1f   model %r   bones %d' % (version, name, len(bones)))

    if args.find:
        hit = [b for b in bones if b['name'] == args.find]
        if not hit:
            print('  no bone %r; closest: %s'
                  % (args.find, [b['name'] for b in bones if args.find[:2] in b['name']][:12]))
            return 1
        for b in hit:
            parent = bones[b['parent']]['name'] if 0 <= b['parent'] < len(bones) else '-'
            print('    %-12s pos (%.3f, %.3f, %.3f)  parent %s'
                  % (b['name'], b['pos'][0], b['pos'][1], b['pos'][2], parent))
        return 0

    print()
    print('    %-14s %-22s %-6s %s' % ('bone', 'rest position', 'parent', 'parent name'))
    for b in bones[:args.top]:
        parent = bones[b['parent']]['name'] if 0 <= b['parent'] < len(bones) else '-'
        print('    %-14s (%7.3f, %7.3f, %7.3f) %-6d %s'
              % (b['name'], b['pos'][0], b['pos'][1], b['pos'][2], b['parent'], parent))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
