"""Read the animation curves out of a binary FBX, which is the only motion in the whole model library.

**Why this file exists.** A mesh at rest is an A-pose: it says where the joints are and nothing about how they move.
Among the four VRM files and thirteen FBX files in the model library, exactly one carries curves -- `Zome_VRC.fbx`,
three animation stacks and 687 `AnimationCurve` records -- so if a gesture is to be learned from these assets at all,
it is learned here.

**The format, and it is short.** A binary FBX is a header and a tree of records. Each record is 13 bytes of header
(end offset, property count, property list length, name length) then a name then its properties; a record with a zero
end offset closes its parent. Properties are typed by one character: numbers, strings, and -- what matters here --
arrays that are usually zlib compressed.

    python tools/fbx_curves.py --src "E:\\ANMS\\Zome_Ver1.3_by_Yo\\FBX\\Zome_VRC.fbx"

**What is deliberately not done.** The curves are not attached to the bones: that needs the `Connections` graph and a
full node hierarchy walk, and the question this answers first is whether there is motion here worth attaching.
"""
import argparse
import struct
import zlib

SCALAR = {'Y': ('<h', 2), 'C': ('<B', 1), 'I': ('<i', 4), 'F': ('<f', 4), 'D': ('<d', 8), 'L': ('<q', 8)}
#: Array properties, by FBX code, in `array.array` type codes -- **which are one character each**, unlike numpy's
#: '<f4' spelling. Passing the numpy spelling raises "argument 1 must be a unicode character", which is how this was
#: found rather than guessed.
ARRAY = {'f': 'f', 'd': 'd', 'l': 'q', 'i': 'i', 'b': 'B'}


def read_property(data, off):
    code = chr(data[off])
    off += 1
    if code in SCALAR:
        fmt, size = SCALAR[code]
        if off + size > len(data):
            raise ValueError('truncated %r property at %d of %d' % (code, off, len(data)))
        value = struct.unpack_from(fmt, data, off)[0]
        return value, off + size
    if code in ('S', 'R'):
        n = struct.unpack_from('<I', data, off)[0]
        off += 4
        raw = data[off:off + n]
        return (raw.decode('latin-1') if code == 'S' else raw), off + n
    if code in ARRAY:
        n, encoding, clen = struct.unpack_from('<III', data, off)
        off += 12
        raw = data[off:off + clen]
        off += clen
        if encoding == 1:
            raw = zlib.decompress(raw)
        import array
        values = array.array(ARRAY[code])
        values.frombytes(raw[:n * values.itemsize])
        return values.tolist(), off
    raise ValueError('unknown property code %r at %d' % (code, off - 1))


#: The last few records read, so a failure can say where the walk went wrong rather than only that it did.
_TRACE = []


def read_node(data, off, wide):
    """One record. **`wide` is the version, and getting it wrong costs exactly twelve bytes per record.**

    A binary FBX before 7500 writes a record header as three 32-bit counts and a one-byte name length -- 13 bytes.
    **7500 and later write the same three counts as 64-bit**, so the header is 25 bytes. Reading a 7700 file as 13
    bytes put the walk twelve bytes early at every node, and the first symptom was a node named `ileId`, which is
    `FileId` with its name length consumed as if it were a name.
    """
    if wide:
        end, nprops, plen = struct.unpack_from('<QQQ', data, off)
        nlen = data[off + 24]
        start = off
        off += 25
    else:
        end, nprops, plen, nlen = struct.unpack_from('<IIIB', data, off)
        start = off
        off += 13
    if end == 0:
        return None, off
    name = data[off:off + nlen].decode('latin-1')
    off += nlen
    _TRACE.append((start, name.split('\x00')[-1][:24], end, nprops, plen))
    del _TRACE[:-24]
    if end > len(data) or end < off:
        raise ValueError('node %r claims to end at %d, outside the record that starts at %d'
                         % (name, end, off - nlen - (25 if wide else 13)))
    props = []
    for _ in range(nprops):
        value, off = read_property(data, off)
        props.append(value)
    children = []
    while off < end:
        child, off = read_node(data, off, wide)
        if child is None:
            break
        children.append(child)
    return {'name': name, 'props': props, 'children': children}, end


def parse(data):
    magic = data[:18]
    if not magic.startswith(b'Kaydara FBX Binary'):
        raise ValueError('not a binary FBX: %r' % magic)
    version = struct.unpack_from('<I', data, 23)[0]
    wide = version >= 7500
    off = 27
    nodes = []
    while off < len(data):
        start = off
        try:
            node, off = read_node(data, off, wide)
        except ValueError as exc:
            print('  parse stopped at %d of %d: %s' % (start, len(data), exc))
            print('  the last records read:')
            for rec in _TRACE[-8:]:
                print('    at %8d  %-24s ends %8d  props %d  bytes %d' % rec)
            raise
        if node is None:
            break
        nodes.append(node)
    return version, nodes


def walk(nodes):
    for node in nodes:
        yield node
        for deeper in walk(node['children']):
            yield deeper


def bare(name):
    """An FBX names its object types with a two-byte prefix, so the type is the part after the last separator."""
    return name.split('\x00')[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--curve', type=int, default=0, help='which curve to show the shape of')
    args = ap.parse_args()

    with open(args.src, 'rb') as f:
        data = f.read()
    version, nodes = parse(data)
    print('  %s' % args.src)
    print('  binary FBX version %d, %.1f MB' % (version, len(data) / 1048576.0))

    # **`AnimationCurveNode` contains `AnimationCurve` as a substring, and the wider match found only the outer
    # record.** 686 nodes came out with no keyframes in any of them, because a curve node is a container -- the
    # keyframes are in the `AnimationCurve` records nested under it.
    nodes_with_curves = [n for n in walk(nodes) if bare(n['name']) == 'AnimationCurveNode']
    curves = [n for n in walk(nodes) if bare(n['name']) == 'AnimationCurve']
    print('  AnimationCurveNode records: %d' % len(nodes_with_curves))
    print('  AnimationCurve records: %d' % len(curves))
    if not curves:
        print('  no curves: this file carries no motion')
        return 1

    times, values, lengths = [], [], []
    for node in curves:
        by_name = {c['name']: c for c in node['children']}
        t = by_name.get('KeyTime')
        v = by_name.get('KeyValueFloat')
        if not t or not v or not t['props'] or not v['props']:
            continue
        keytimes = t['props'][0]
        keyvalues = v['props'][0]
        if not keytimes:
            continue
        times.extend(keytimes)
        values.extend(keyvalues)
        lengths.append(len(keytimes))

    if not times:
        print('  curves found but none with keyframes attached')
        return 1
    span = (min(times), max(times))
    print('  keyframes: %d across %d curves' % (len(times), len(lengths)))
    print('  time span: %.3f to %.3f (FBX ticks; %.1f frames at 24 per second)'
          % (span[0], span[1], (span[1] - span[0]) / 46186158000.0 * 24.0))
    lengths.sort()
    print('  keyframes per curve: min %d  median %d  max %d'
          % (lengths[0], lengths[len(lengths) // 2], lengths[-1]))

    # **One curve, shown, because a count says there is motion and a shape says what kind.** A curve that ramps and
    # stops is a pose; one that rises, overshoots and settles is a limb being thrown and caught.
    target = curves[min(args.curve, len(curves) - 1)]
    by_name = {c['name']: c for c in target['children']}
    if 'KeyValueFloat' in by_name and by_name['KeyValueFloat']['props']:
        vals = by_name['KeyValueFloat']['props'][0]
        if vals:
            step = max(1, len(vals) // 16)
            print()
            print('  curve %d of %d, %d keys, sampled:' % (args.curve, len(curves), len(vals)))
            print('    %s' % ['%.3f' % v for v in vals[::step][:16]])
            rises = sum(1 for i in range(1, len(vals)) if vals[i] > vals[i - 1])
            print('    rises on %d of %d steps -- a monotone ramp would be all or none'
                  % (rises, len(vals) - 1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
