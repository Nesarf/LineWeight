"""A skeleton read off one traced reference, drawn next to the one this project had hard-coded.

**What is being compared and why it is worth doing.** The project's proportions came from measuring eleven 3D rigs in the
Blue Archive corpus -- a rest pose shared by 860 characters. That is a good source for a population's average and a poor
source for any particular character, **because a rest pose is never a pose**. This tool puts the two side by side: the
rig average on the left, the reference on the right, **and both as the same nine marks so the difference is a distance
rather than an impression**.

**Where the reference numbers come from, and what each one is a measurement of.** Three tools produced four heights and
none of them measured a bone:

* `silhouette_profile` found the **narrowest place above the shoulders**, which is where the outline pinches at the neck
* the same tool found the **widest place below that**, which is where the outline is broadest across the chest and
  upper skirt
* `colour_profile` scanned one column and found where **cloth gives way to skin**, which is the hem

**So the reference heights are outline features, and the rig heights are bone positions.** They are not the same kind of
thing, and the tool prints that sentence rather than hiding it in a comment.

    python tools/reference_skeleton.py
    python tools/reference_skeleton.py --render
"""
import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project as project_mod

OUT = pathlib.Path(r'E:\DaShaoHuo\cache\skeleton-compare.json')
PNG = pathlib.Path(r'E:\DaShaoHuo\cache\skeleton-compare.png')

#: The rig average, measured over eleven Blue Archive rigs. **Bone positions**, from the top of the figure.
RIG = {'head': 0.184, 'rib': 0.447, 'pelvis': 0.567}

#: The reference, read off `Cache_7cef975685e2f0c2.png` -- a **full length** figure, so its height runs from the crown to
#: the sole and the ratios are directly comparable with the rig's.
#:
#: **The first attempt used a half-length portrait and produced differences of 0.10 to 0.16 that meant nothing**, because
#: its "height" ran from a rabbit ear to the bottom of the frame. The drawing that exposed it is in `TODO.md`; the lesson
#: is that two ratios may only be subtracted when they share a ruler, and that a picture shows a shared ruler at a glance
#: where a table does not.
REF = {'neck': 0.218, 'widest': 0.513, 'hem': 0.533}

#: The head's centre sits halfway between the top of the figure and the narrowing below it. **The narrowing includes the
#: hair and the ears**, so this is an outline feature and the comparison says so.
REF_HEAD = REF['neck'] / 2.0

#: The rib cage's centre is placed a third of the way from the widest point up towards the neck: the widest point is where
#: the rib cage meets the skirt, and the centre of the mass is above it.
REF_RIB = REF['neck'] + (REF['widest'] - REF['neck']) * 0.42

#: The pelvis sits just below the hem of the clothing, since a garment ends at the pelvis and not below it.
REF_PELVIS = REF['hem']

REF_MASSES = {'head': REF_HEAD, 'rib': REF_RIB, 'pelvis': REF_PELVIS}


def draw(proj, masses, origin, height, label, colour):
    """Nine marks: three masses and the two chains that join them."""
    ox, oy = origin
    scale = height
    # widths as fractions of the figure's height: a sphere for the head, an egg for the rib cage, a flat egg for the pelvis
    sizes = {'head': (0.105, 0.115), 'rib': (0.105, 0.150), 'pelvis': (0.115, 0.070)}
    for name, frac in masses.items():
        cx = ox
        cy = oy + frac * scale
        rx, ry = sizes[name]
        ring = []
        import math
        for i in range(41):
            t = i / 40.0 * 2 * math.pi
            ring.append((cx + rx * scale * math.cos(t), cy + ry * scale * math.sin(t)))
        rec = core.stroke_record(ring, 'fine', seed=abs(hash((label, name))) % 9973, resolution=10,
                                 width_profile=[2.6] * (10 * (len(ring) - 1) + 1))
        proj.add_stroke(rec, stage='line', layer=label, note='%s %s' % (label, name))
    # the two chains, as S curves: pelvis to rib, rib to head
    for a, b in (('pelvis', 'rib'), ('rib', 'head')):
        ax, ay = ox, oy + masses[a] * scale
        bx, by = ox, oy + masses[b] * scale
        mid = ((ax + bx) / 2.0 + 0.022 * scale, (ay + by) / 2.0)
        pts = [((ax + bx) / 2.0 + 0.022 * scale * math.sin(i / 20.0 * math.pi * 2), 0) for i in range(21)]
        rec = core.stroke_record([(ax, ay), mid, (bx, by)], 'fine', seed=abs(hash((label, a, b))) % 9973,
                                 resolution=10, width_profile=[2.2] * (10 * 2 + 1))
        proj.add_stroke(rec, stage='line', layer=label, note='%s %s-%s' % (label, a, b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    proj = project_mod.Project(width=760, height=900, title='rig average vs reference')
    draw(proj, RIG, (250.0, 60.0), 760.0, 'rig average', 'rig')
    draw(proj, REF_MASSES, (520.0, 60.0), 760.0, 'reference', 'ref')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    project_mod.save_project(proj, str(OUT))

    print('  left: the rig average over eleven Blue Archive rigs (bone positions)')
    print('  right: read off one reference picture (outline features)')
    print()
    print('  %-10s %10s %10s %10s' % ('mass', 'rig', 'reference', 'difference'))
    for name in ('head', 'rib', 'pelvis'):
        print('  %-10s %10.3f %10.3f %10.3f' % (name, RIG[name], REF_MASSES[name], REF_MASSES[name] - RIG[name]))
    print()
    print('  the reference heights used, and what each one measured:')
    print('    neck             %.3f   the narrowest place above the shoulder' % REF['neck'])
    print('    chest widest     %.3f   the widest place below that' % REF['widest'])
    print('    hem              %.3f   where cloth gives way to skin on one column' % REF['hem'])
    print()
    print('  written to %s' % OUT)
    if args.render:
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(OUT), '--out', str(PNG)],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % PNG)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
