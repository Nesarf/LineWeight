"""Turn a character mesh into a volume profile: at every height, how wide and how deep the body is.

**This is the one thing a silhouette cannot supply and a joint cannot either.** A joint says where a bend is; a
silhouette says how wide the body looks from one side. Neither says how far the chest stands out from the spine, and
that distance is what makes a drawing have a front and a back rather than a cut-out.

**Why the full mesh is not kept.** A character GLB is 26 MB and almost all of it is textures; the vertices of one model
are about 1.3 MB and the profile of those vertices is about 4 KB. What a drawing needs from a surface is a width at a
height, so the surface is measured and the measurement is what stays. **The mesh can be measured again at any time**,
which is the same rule the rest of `model/` follows.

    python tools/mesh_profile.py --src "E:\\ANMS\\Zome_Ver1.3_by_Yo\\Zome.vrm" --out model/shape/zome.json
"""
import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import vrm_look as vl

#: How many bands the height is cut into. **Sixty-four is one per two per cent of a figure**, which is finer than any
#: outline is drawn and coarse enough that the numbers are a shape rather than noise.
BANDS = 64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', default='', help='keep only meshes whose name contains this')
    ap.add_argument('--bands', type=int, default=BANDS)
    args = ap.parse_args()

    _version, js, blob = vl.load_glb(args.src)
    # **Two sets of vertices: the one that fixes the height, and the one that is measured.** A body mesh stops at the
    # top of the skull while the figure reaches the tip of a horn, so measuring the body against its own extent would
    # give a body that is 100 per cent of a body. The height is taken from every mesh and the widths from the ones
    # asked for.
    every = []
    measured = []
    per_mesh = []
    for m, mesh in enumerate(js.get('meshes', [])):
        name = mesh.get('name', 'mesh%d' % m)
        for prim in mesh.get('primitives', []):
            pos = prim.get('attributes', {}).get('POSITION')
            if pos is None:
                continue
            pts = vl.accessor_array(js, blob, pos).astype(np.float64)
            every.append(pts)
            if not args.only or args.only.lower() in name.lower():
                measured.append(pts)
                per_mesh.append((name, len(pts)))
    if not measured:
        print('  no vertices%s' % (' matching %r' % args.only if args.only else ''))
        return 1

    whole = np.concatenate(every, axis=0)
    lo, hi = whole.min(axis=0), whole.max(axis=0)
    pts = np.concatenate(measured, axis=0)
    height = float(hi[1] - lo[1])
    # **Centred on the figure's own x and z midpoints**, so a profile is a shape and not a placement -- where a model
    # sits in its own file is a fact about the file, and a drawing would only subtract it.
    cx = float((lo[0] + hi[0]) / 2.0)
    cz = float((lo[2] + hi[2]) / 2.0)

    rows = []
    for b in range(args.bands):
        y0 = lo[1] + height * b / args.bands
        y1 = lo[1] + height * (b + 1) / args.bands
        band = pts[(pts[:, 1] >= y0) & (pts[:, 1] < y1)]
        if not len(band):
            continue
        rows.append({
            'y': round((y0 + y1) / 2.0 - lo[1], 4),
            'w': round(float(band[:, 0].max() - band[:, 0].min()), 4),
            'd': round(float(band[:, 2].max() - band[:, 2].min()), 4),
            'x': round(float((band[:, 0].min() + band[:, 0].max()) / 2.0 - cx), 4),
            'z': round(float((band[:, 2].min() + band[:, 2].max()) / 2.0 - cz), 4),
        })

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # **The pose is recorded with the profile because the profile is only comparable within one pose.** A T-pose
    # measures 0.82 of a body across the arms and an A-pose measures 0.55, so the same figure yields two different
    # numbers and neither is wrong. **The ratio of the arm band to the hip band is what tells them apart**: arms held
    # out reach three or more times the hips, arms held down reach about twice.
    arm = max([r['w'] for r in rows if 0.66 <= r['y'] / height <= 0.88] or [0.0])
    hip = max([r['w'] for r in rows if 0.38 <= r['y'] / height <= 0.56] or [0.0])
    arm_ratio = (arm / hip) if hip else 0.0
    pose = 'arms out' if arm_ratio >= 3.0 else ('arms down' if arm_ratio > 0 else 'unknown')
    payload = {
        'source': args.src,
        'model': pathlib.Path(args.src).stem,
        'note': 'one row per height band, bottom to top; y is measured from the feet and divided by the height; '
                'w is the width and d the depth, both divided by the height; x and z are how far the band\'s own '
                'centre sits from the figure\'s, also divided by the height',
        'height': 1.0,
        'bands': len(rows),
        'vertices': int(len(pts)),
        'pose': pose,
        'arm_over_hip': round(arm_ratio, 2),
        'meshes': [n for n, _c in per_mesh],
        'rows': [{'y': round(r['y'] / height, 4), 'w': round(r['w'] / height, 4),
                  'd': round(r['d'] / height, 4), 'x': round(r['x'] / height, 4),
                  'z': round(r['z'] / height, 4)} for r in rows],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('  %-28s %6d vertices, %d bands, %.1f KB'
          % (out.name, len(pts), len(rows), out.stat().st_size / 1024.0))
    print('    pose %-9s arm band %.3f over hip band %.3f (ratio %.2f)'
          % (pose, arm / height, hip / height, arm_ratio))
    widest = max(rows, key=lambda r: r['w'])
    deepest = max(rows, key=lambda r: r['d'])
    print('    widest band at y=%.2f of the height: w %.3f   deepest at y=%.2f: d %.3f'
          % (widest['y'] / height, widest['w'] / height, deepest['y'] / height, deepest['d'] / height))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
