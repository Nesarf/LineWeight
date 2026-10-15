"""What the 860 character rigs actually look like, measured rather than assumed.

**The drawing's pose is twenty hand-written coordinates.** The corpus has 860 rigged characters, and their rest poses
were shown to be readable and verified against the meshes' bind poses. So the question is what those rest poses are --
and there are two answers it could give, which mean opposite things:

  * **A pipeline convention.** If every character's shoulders, elbows and knees sit at the same angles, the rest pose
    is a production default -- an A-pose or a T-pose that the riggers agree on -- and it carries no information about
    how anybody is drawn. Taking a pose from it would replace one invention with another, more precisely recorded.
  * **A design.** If the angles spread, the rest pose encodes something about the character, and a measured
    distribution is a real source.

**The spread is therefore the measurement**, not the values. This writes out both: the numbers and how much they
vary, so the decision between the two answers is made on the numbers rather than on which one sounds better.

Only `Bip001` bones are used. Everything else in the bundle -- cameras, lights, props, hair and skirt bones -- is not
a body, and a direction light's coordinate looks exactly like a plausible body height.

    python measure_rigs.py --limit 40
    python measure_rigs.py                 # all 860, about half an hour
"""
import argparse
import json
import math
import pathlib
import statistics
import sys
import time

import UnityPy

BUNDLES = pathlib.Path(r'E:\~Harumi~Desuwa~\bluearchive\files\AssetBundles')
OUT = pathlib.Path(r'E:\DaShaoHuo\cache\tmp\rig-census.json')
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import importlib.util

spec = importlib.util.spec_from_file_location('rr', str(pathlib.Path(__file__).parent / 'read_rig.py'))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

#: The joints a pose is read from. Names are the corpus's own, and they are the same ones the drawing's hand-written
#: `POS` uses, which is what makes a substitution direct rather than a mapping problem.
JOINTS = ('Bip001', 'Bip001 Pelvis', 'Bip001 Spine', 'Bip001 Spine1', 'Bip001 Neck', 'Bip001 Head',
          'Bip001 L Clavicle', 'Bip001 L UpperArm', 'Bip001 L Forearm', 'Bip001 L Hand',
          'Bip001 R Clavicle', 'Bip001 R UpperArm', 'Bip001 R Forearm', 'Bip001 R Hand',
          'Bip001 L Thigh', 'Bip001 L Calf', 'Bip001 L Foot', 'Bip001 L Toe0',
          'Bip001 R Thigh', 'Bip001 R Calf', 'Bip001 R Foot', 'Bip001 R Toe0')


def angle_at(a, b, c):
    """The interior angle at `b`, in degrees. 180 is a straight limb, 90 a right angle."""
    v1 = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    v2 = (c[0] - b[0], c[1] - b[1], c[2] - b[2])
    n1 = math.sqrt(sum(x * x for x in v1))
    n2 = math.sqrt(sum(x * x for x in v2))
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    cos = sum(v1[i] * v2[i] for i in range(3)) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def measure(world):
    """The pose as a handful of numbers that could replace a hand-written coordinate."""
    have = {n: world[n] for n in JOINTS if n in world}
    if 'Bip001 Pelvis' not in have or 'Bip001 Head' not in have:
        return None
    bip = {k: v for k, v in world.items() if k.startswith('Bip001')}
    ys = [v[1] for v in bip.values()]
    height = max(ys) - min(ys)
    if height <= 1e-6:
        return None
    out = {'bones': len(bip), 'height': height, 'foot_y': min(ys)}

    def g(n):
        return have.get(n)

    # **The shape of the body, as ratios, because the corpus is in Unity units and the drawing is in its own.** A
    # raw coordinate from one rig is comparable with nothing; a ratio of two lengths inside the same rig is comparable
    # with every other rig and with the drawing.
    if g('Bip001 Head') and g('Bip001 L Toe0'):
        out['head_y_over_height'] = (g('Bip001 Head')[1] - min(ys)) / height
    if g('Bip001 L UpperArm') and g('Bip001 R UpperArm'):
        out['shoulder_width_over_height'] = abs(g('Bip001 L UpperArm')[0] - g('Bip001 R UpperArm')[0]) / height
    if g('Bip001 Pelvis'):
        out['pelvis_y_over_height'] = (g('Bip001 Pelvis')[1] - min(ys)) / height
    if g('Bip001 L Thigh') and g('Bip001 R Thigh'):
        out['hip_width_over_height'] = abs(g('Bip001 L Thigh')[0] - g('Bip001 R Thigh')[0]) / height
    if g('Bip001 Head') and g('Bip001 Neck'):
        out['head_height_over_height'] = (g('Bip001 Head')[1] - g('Bip001 Neck')[1]) / height

    # **The default bend of every limb.** These are the numbers a hand-written pose gets wrong: an arm that is
    # straight when it should hang at forty-five degrees, a knee with no bend at all in it.
    for side in ('L', 'R'):
        sh, el, wr = g('Bip001 %s UpperArm' % side), g('Bip001 %s Forearm' % side), g('Bip001 %s Hand' % side)
        if sh and el and wr:
            out['elbow_%s' % side] = angle_at(sh, el, wr)
        cl = g('Bip001 %s Clavicle' % side)
        if cl and sh and wr:
            out['arm_drop_%s' % side] = angle_at(cl, sh, wr)
        th, ca, fo = g('Bip001 %s Thigh' % side), g('Bip001 %s Calf' % side), g('Bip001 %s Foot' % side)
        if th and ca and fo:
            out['knee_%s' % side] = angle_at(th, ca, fo)

    # **And the centre of mass, which is where a stiff figure comes from.** The pelvis's X against the mean of the two
    # feet says whether the weight is over the feet or off to one side.
    if g('Bip001 Pelvis') and g('Bip001 L Toe0') and g('Bip001 R Toe0'):
        foot_x = (g('Bip001 L Toe0')[0] + g('Bip001 R Toe0')[0]) / 2.0
        out['balance_over_height'] = (g('Bip001 Pelvis')[0] - foot_x) / height
    if g('Bip001 L Toe0') and g('Bip001 R Toe0'):
        out['stance_width_over_height'] = abs(g('Bip001 L Toe0')[0] - g('Bip001 R Toe0')[0]) / height
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    files = sorted(BUNDLES.glob('character-*prefabs*.bundle'))
    if args.limit:
        files = files[:args.limit]
    print('  %d prefab bundles' % len(files))

    rows, skipped = [], 0
    t0 = time.time()
    for i, p in enumerate(files, 1):
        try:
            env = UnityPy.load(str(p))
            world = rr.compose(env)
            m = measure(world)
            if m:
                m['name'] = p.name.split('-')[1] if '-' in p.name else p.stem
                rows.append(m)
            else:
                skipped += 1
        except Exception as exc:
            skipped += 1
            if skipped <= 5:
                print('    %-52s %s' % (p.name[:52], str(exc)[:40]))
        if i % 25 == 0 or i == len(files):
            el = time.time() - t0
            print('    %4d/%d  %5.1fs  %.1f/s  %d measured  %d skipped'
                  % (i, len(files), el, i / el if el else 0, len(rows), skipped), flush=True)

    print()
    print('  %d rigs measured, %d skipped' % (len(rows), skipped))
    if not rows:
        return 1
    keys = [k for k in rows[0] if k not in ('name', 'bones')]
    print()
    print('  %-28s %9s %9s %9s %9s %9s' % ('measure', 'p05', 'p25', 'median', 'p75', 'p95'))
    stats = {}
    for k in keys:
        vals = sorted(v for v in (r.get(k) for r in rows) if isinstance(v, (int, float)))
        if len(vals) < 5:
            continue
        n = len(vals)
        def q(p): return vals[int(p * (n - 1))]
        stats[k] = {'n': n, 'p05': q(.05), 'p25': q(.25), 'median': q(.5), 'p75': q(.75), 'p95': q(.95),
                    'mean': statistics.mean(vals), 'stdev': statistics.pstdev(vals)}
        print('  %-28s %9.4f %9.4f %9.4f %9.4f %9.4f'
              % (k, q(.05), q(.25), q(.5), q(.75), q(.95)))

    print()
    print('  ** whether a rest pose is a pipeline convention or a design is the spread.** A measure whose p05 and p95')
    print('     sit on top of each other is something the riggers agreed on; one that spreads is something the')
    print('     character carries. The stdev beside each median says which of the two this is, per measure. **')
    print()
    for k, st in sorted(stats.items(), key=lambda kv: kv[1]['stdev'] / max(1e-9, abs(kv[1]['median']))):
        # **The spread is reported robustly, and the reason is visible in the first version's output.** It divided
        # the stdev by the mean and labelled the result convention / mixed / design. For `foot_y` that produced 4.310
        # and "design" -- but the median there is -0.000669 and the mean is 0.064070, a hundredfold apart, so what
        # the divisor caught was a handful of outliers rather than any property of the material. Its stdev is 0.276
        # against an interquartile range of about 0.009, thirty times larger: **the stdev of this quantity is a
        # statement about the tails and nothing else.**
        #
        # So the label uses the interquartile range, which ignores the tails, and both ratios are printed so that a
        # heavy tail shows up as the two disagreeing rather than as a label nobody can check.
        iqr = st['p75'] - st['p25']
        p95p05 = st['p95'] - st['p05']
        if abs(st['median']) < 1e-9 or iqr <= 0:
            print('    %-28s iqr %.6f   median is near zero, so no relative spread is defined' % (k, iqr))
            continue
        rel = iqr / abs(st['median'])
        tail = p95p05 / iqr if iqr else float('inf')
        kind = 'convention' if rel < 0.05 else ('mixed' if rel < 0.20 else 'design')
        flag = '   <- heavy tails, the range is %.0fx the core' % tail if tail > 3 else ''
        print('    %-28s iqr/median %.3f   %s%s' % (k, rel, kind, flag))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'rows': rows, 'stats': stats}, ensure_ascii=False), encoding='utf-8')
    print()
    print('  raw rows written to %s' % OUT)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
