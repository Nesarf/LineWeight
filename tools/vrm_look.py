"""Open a .vrm and say what is inside it: meshes, vertices, bones, materials.

**.vrm is a GLB, and a GLB is a header and two chunks.** The first chunk is JSON, the second is the binary blob the
accessors point into -- so a standard library plus numpy reads the whole geometry without a glTF package. That matters
here because the packages are absent and because a viewer's numbers are the wrong end of the tool: what a drawing wants
is the vertices themselves.

    python tools/vrm_look.py --src "E:\\ANMS\\Zome_Ver1.3_by_Yo\\Zome.vrm"
"""
import argparse
import json
import struct

import numpy as np

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
#: glTF component types that appear in a position accessor, and the numpy spelling of each.
COMPONENT = {5120: '<i1', 5121: '<u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
TYPECOUNT = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def load_glb(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, version, length = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF':
        raise ValueError('%s is not a GLB: magic %r' % (path, magic))
    off = 12
    js, blob = None, None
    while off < min(length, len(data)):
        clen, ctype = struct.unpack_from('<II', data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == JSON_CHUNK:
            js = json.loads(chunk.decode('utf-8'))
        elif ctype == BIN_CHUNK:
            blob = chunk
    return version, js, blob


def accessor_array(js, blob, index):
    """One accessor as an (n, k) array. **byteStride is honoured** because a viewer packs several attributes together."""
    acc = js['accessors'][index]
    view = js['bufferViews'][acc['bufferView']]
    dtype = np.dtype(COMPONENT[acc['componentType']])
    k = TYPECOUNT[acc['type']]
    start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    count = acc['count']
    stride = view.get('byteStride') or (dtype.itemsize * k)
    if stride == dtype.itemsize * k:
        flat = np.frombuffer(blob, dtype=dtype, count=count * k, offset=start)
        return flat.reshape(count, k)
    rows = []
    for i in range(count):
        rows.append(np.frombuffer(blob, dtype=dtype, count=k, offset=start + i * stride))
    return np.stack(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--only', default='', help='keep only meshes whose name contains this')
    args = ap.parse_args()

    version, js, blob = load_glb(args.src)
    print('  %s' % args.src)
    print('  glTF version %d, binary chunk %.1f MB' % (version, len(blob) / 1048576.0))
    print('  meshes %d   nodes %d   skins %d   materials %d   accessors %d'
          % (len(js.get('meshes', [])), len(js.get('nodes', [])), len(js.get('skins', [])),
             len(js.get('materials', [])), len(js.get('accessors', []))))

    # **Vertices, taken from POSITION and nothing else.** A drawing needs where the surface is; normals and UVs are
    # for shading a renderer, and this is not one.
    total = 0
    all_points = []
    per_mesh = []
    for m, mesh in enumerate(js.get('meshes', [])):
        name = mesh.get('name', 'mesh%d' % m)
        pieces = []
        for prim in mesh.get('primitives', []):
            pos = prim.get('attributes', {}).get('POSITION')
            if pos is None:
                continue
            pieces.append(accessor_array(js, blob, pos))
        if not pieces:
            continue
        mine = np.concatenate(pieces, axis=0).astype(np.float64)
        total += len(mine)
        per_mesh.append((name, len(mine), mine.min(axis=0), mine.max(axis=0)))
        if not args.only or args.only.lower() in name.lower():
            all_points.append(mine)
    print('  vertices: %d' % total)

    # **Per mesh, because a vertex cloud is not a body.** A character's width includes hair, a headdress, a skirt and
    # whatever the hand is holding -- and summing them answers a question about the whole character that no single
    # part can use. The bounds below are what says which mesh is what.
    print()
    print('    %-22s %7s  %-26s' % ('mesh', 'verts', 'bounds  (x, y, z)'))
    for name, count, lo, hi in sorted(per_mesh, key=lambda t: -t[1])[:10]:
        print('    %-22s %7d  x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f'
              % (name, count, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))

    if not all_points:
        print('  no mesh matched %r' % args.only)
        return 1
    pts = np.concatenate(all_points, axis=0)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    print()
    print('  measured over %s: %d vertices' % ('all meshes' if not args.only else repr(args.only), len(pts)))
    print('  bounds x %.3f..%.3f   y %.3f..%.3f   z %.3f..%.3f'
          % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
    print('  height %.3f   width %.3f   depth %.3f' % (hi[1] - lo[1], hi[0] - lo[0], hi[2] - lo[2]))

    # **The three widths at every height, which is the thing a two dimensional silhouette cannot give.** The front
    # view of a body and its side view disagree, and the difference between them is what a volume is.
    print()
    print('  %-7s %8s %8s %8s' % ('height', 'width', 'depth', 'front/back'))
    h = hi[1] - lo[1]
    for frac in (0.03, 0.08, 0.13, 0.18, 0.22, 0.30, 0.40, 0.50, 0.57, 0.65, 0.78, 0.92):
        y = lo[1] + frac * h
        band = pts[(pts[:, 1] > y - h * 0.008) & (pts[:, 1] < y + h * 0.008)]
        if not len(band):
            continue
        w = band[:, 0].max() - band[:, 0].min()
        d = band[:, 2].max() - band[:, 2].min()
        print('  %-7.2f %8.3f %8.3f %8.2f' % (frac, w / h, d / h, w / d if d else 0.0))

    biggest = sorted(per_mesh, key=lambda t: -t[1])[:6]
    print()
    print('  largest meshes: %s' % ', '.join('%s=%d' % (t[0], t[1]) for t in biggest))

    # **The head, measured apart from the hair.** A silhouette cannot do this: a long-haired character's narrowest
    # point above the shoulders is where the *hair* is narrowest, and the chin is a different height. A mesh named
    # face is the skin of the face, so its own bounds are the chin and the top of the brow, and the height of the
    # whole head is that plus the skull above it -- which the hair covers and this cannot see. What it can say exactly
    # is the chin, the face's width, and how tall the face is against the figure.
    face = [t for t in per_mesh if 'face' in t[0].lower()]
    if face:
        name, count, flo, fhi = face[0]
        chin = flo[1]
        head_top = max(hi[1], 0.0)
        h = hi[1] - lo[1]
        print()
        print('  head (%s, %d verts):' % (name, count))
        print('    chin at y %.3f -- %.3f of the height above the feet' % (chin, (chin - lo[1]) / h))
        print('    face height %.3f  = %.3f of the figure' % (fhi[1] - flo[1], (fhi[1] - flo[1]) / h))
        print('    face width  %.3f  = %.3f of the figure' % (fhi[0] - flo[0], (fhi[0] - flo[0]) / h))
        print('    face depth  %.3f  = %.3f of the figure' % (fhi[2] - flo[2], (fhi[2] - flo[2]) / h))
        print('    top of everything at y %.3f, so chin-to-top is %.3f of the figure'
              % (head_top, (head_top - chin) / h))
        print('    face width over face height %.3f' % ((fhi[0] - flo[0]) / (fhi[1] - flo[1])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
