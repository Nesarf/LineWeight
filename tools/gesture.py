"""The first stage: gesture. Eight parts, three kinds of line, and three masses off the centre of gravity.

**Why this is a separate tool and not a change to `cel_drawing.py`.** That tool starts from a pose that is a constant and
draws volume from it; this one draws the layer underneath -- **what the figure is doing** -- and nothing else. Keeping them
apart means the gesture can be judged on its own terms before any volume is drawn over it, which is the order every
reference book uses and the one this project has never had.

**What the six rules from `learn/facts.json` turn into here, one at a time:**

* **eight parts** -- head, spine, arms (2), pelvis, rib cage, legs (2). Every mark belongs to one of them and nothing
  else is drawn.
* **three kinds of line** -- the C curve, the straight, and the S curve. A mark whose path is not one of those is a
  mistake, not a variation.
* **sphere, line, joint** -- the head is a sphere, a limb is a line, and where two meet there is a joint.
* **three masses off the centre** -- a sphere for the head, an egg for the rib cage, a horizontal egg for the pelvis,
  and **each one sits off the vertical** rather than on it.
* **the "about to" moment** -- a pose is chosen as a moment in the middle of an action, not as a resting attitude.
* **rough first, then clean** -- each pose is drawn twice: a loose pass whose lines are allowed to be wrong, then a
  cleaned pass on the same gesture. **The cleaned pass is not a second drawing; it is the same one with the mistakes
  taken out**, which is why the loose pass is kept in the project as its own layer.

    python gesture.py                  # write the gesture project and measure it
    python gesture.py --render         # and render it
"""
import argparse
import math
import pathlib
import subprocess
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project as project_mod

OUT = pathlib.Path(r'E:\DaShaoHuo\cache\gesture.json')
PNG = pathlib.Path(r'E:\DaShaoHuo\cache\gesture.png')

#: **A pose is three masses and four limbs, all placed relative to one vertical.** The numbers are offsets from that
#: vertical in figure units, and a positive x is to the viewer's right -- **and every one of them is away from zero on
#: purpose**, because a mass sitting on the centre line is the mistake the reference names.
#:
#: `y` is measured downward from the top of the figure, so 0.10 is near the top and 0.94 is near the ground.
#: The four limb entries give the two ends of a line and which of the three curves to use; the knee and elbow are found
#: by bending that line rather than being placed, which is what keeps a limb one stroke.
POSES = [
    {
        'name': 'about to step',
        'story': 'weight already moving onto the front foot, back heel lifting, one hand out for balance',
        'head':   (0.012, 0.085),
        'rib':    (-0.026, 0.300),
        'pelvis': (0.034, 0.560),
        'arm_r':  ('C', (0.150, 0.320), (0.245, 0.520), 0.06),
        'arm_l':  ('C', (-0.140, 0.330), (-0.200, 0.470), -0.05),
        'leg_r':  ('straight', (0.070, 0.570), (0.120, 0.980), 0.0),
        'leg_l':  ('C', (-0.060, 0.575), (-0.150, 0.900), -0.07),
    },
    {
        'name': 'about to turn',
        'story': 'mid-turn, shoulders already past the hips, head following',
        'head':   (0.030, 0.080),
        'rib':    (0.052, 0.295),
        'pelvis': (-0.018, 0.565),
        'arm_r':  ('S', (0.165, 0.310), (0.215, 0.500), 0.09),
        'arm_l':  ('C', (-0.155, 0.320), (-0.115, 0.505), -0.06),
        'leg_r':  ('straight', (0.060, 0.575), (0.080, 0.985), 0.0),
        'leg_l':  ('straight', (-0.070, 0.580), (-0.095, 0.985), 0.0),
    },
    {
        'name': 'about to reach',
        'story': 'leaning out, one arm not yet extended, the other pulled back',
        'head':   (-0.040, 0.095),
        'rib':    (-0.070, 0.310),
        'pelvis': (0.046, 0.570),
        'arm_r':  ('C', (0.150, 0.330), (0.290, 0.400), 0.10),
        'arm_l':  ('C', (-0.135, 0.335), (-0.230, 0.430), -0.08),
        'leg_r':  ('C', (0.080, 0.575), (0.135, 0.975), 0.05),
        'leg_l':  ('straight', (-0.065, 0.580), (-0.100, 0.985), 0.0),
    },
]

#: **The three kinds of line, as curvature.** A straight line has one control point; a C has one bowed to one side; an
#: S has two bowed to opposite sides. **There is no fourth option**, which is the rule the reference states flatly.
def bend(a, b, curve, amount):
    """The control points for one of the three line kinds between two points."""
    ax, ay = a
    bx, by = b
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    if curve == 'straight':
        return [a, (mx, my), b]
    if curve == 'C':
        return [a, (mx + nx * amount * L, my + ny * amount * L), b]
    # S: two bows in opposite directions, so the line turns twice
    t1, t2 = 1.0 / 3.0, 2.0 / 3.0
    return [a,
            (ax + dx * t1 + nx * amount * L, ay + dy * t1 + ny * amount * L),
            (ax + dx * t2 - nx * amount * L * 0.7, ay + dy * t2 - ny * amount * L * 0.7),
            b]


def ellipse(cx, cy, rx, ry, tilt=0.0, count=41):
    out = []
    c, s = math.cos(tilt), math.sin(tilt)
    for i in range(count):
        t = i / (count - 1.0) * 2 * math.pi
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cx + x * c - y * s, cy + x * s + y * c))
    return out


def draw_pose(proj, pose, scale, origin, rough=False):
    """One pose, as a rough pass or a clean one. The rough pass is deliberately off by a few pixels."""
    ox, oy = origin
    jitter = (lambda k: math.sin(k * 12.9898) * 2.5) if rough else (lambda k: 0.0)
    width = 2.2 if rough else 3.4
    n = 0

    def place(p):
        return (ox + p[0] * scale, oy + p[1] * scale)

    # **The three masses.** A sphere, an egg, and a horizontal egg -- and each is off the vertical by its own amount,
    # which is the whole of what makes the pose dynamic.
    hx, hy = place(pose['head'])
    rx, ry = pose['rib']
    px, py = place(pose['pelvis'])
    masses = [
        ('head', ellipse(hx + jitter(1), hy + jitter(2), 0.062 * scale, 0.070 * scale, 0.10)),
        ('rib', ellipse(rx + jitter(3), ry + jitter(4), 0.052 * scale, 0.105 * scale, -0.16)),
        ('pelvis', ellipse(px + jitter(5), py + jitter(6), 0.062 * scale, 0.045 * scale, 0.22)),
    ]
    for name, ring in masses:
        rec = core.stroke_record(ring, 'fine', seed=abs(hash((pose['name'], name, rough))) % 9973,
                                 resolution=12, width_profile=[width * 0.8] * (12 * (len(ring) - 1) + 1))
        proj.add_stroke(rec, stage='line', layer='rough' if rough else 'gesture', note='%s, %s' % (pose['name'], name))
        n += 1

    # **The spine, as an S from the pelvis to the rib cage.** The one line in the figure that is always the same kind.
    spine = bend((px, py), (rx, ry), 'S', 0.16)
    rec = core.stroke_record(spine, 'fine', seed=abs(hash((pose['name'], 'spine', rough))) % 9973, resolution=12,
                             width_profile=[width] * (12 * (len(spine) - 1) + 1))
    proj.add_stroke(rec, stage='line', layer='rough' if rough else 'gesture', note='%s, spine' % pose['name'])
    n += 1

    # **Four limbs, each one of the three kinds of line.** The elbow and the knee are the bend in the line and are
    # never placed as points of their own.
    for key, part in (('arm_r', 'arm right'), ('arm_l', 'arm left'), ('leg_r', 'leg right'), ('leg_l', 'leg left')):
        curve, a, b, amount = pose[key]
        pts = [place(p) for p in bend(a, b, curve, amount)]
        if rough:
            pts = [(x + jitter(k), y + jitter(k + 1)) for k, (x, y) in enumerate(pts)]
        rec = core.stroke_record(pts, 'fine', seed=abs(hash((pose['name'], key, rough))) % 9973, resolution=12,
                                 width_profile=[width] * (12 * (len(pts) - 1) + 1))
        proj.add_stroke(rec, stage='line', layer='rough' if rough else 'gesture',
                        note='%s, %s' % (pose['name'], part))
        n += 1
    return n


def offsets(pose):
    """How far each of the three masses sits off the vertical, in figure units."""
    return {
        'head': abs(pose['head'][0]),
        'rib': abs(pose['rib'][0]),
        'pelvis': abs(pose['pelvis'][0]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    proj = project_mod.Project(width=900, height=1200, title='gesture')
    scale, gap = 320.0, 300.0
    marks = 0
    for i, pose in enumerate(POSES):
        origin = (40.0 + i * gap, 40.0)
        marks += draw_pose(proj, pose, scale, origin, rough=True)
        marks += draw_pose(proj, pose, scale, origin, rough=False)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    project_mod.save_project(proj, str(OUT))
    print('  %d poses, %d marks, written to %s' % (len(POSES), marks, OUT))
    print()
    print('  the three numbers this stage is judged by:')
    print('    %-18s %8s %8s %8s' % ('pose', 'head', 'rib', 'pelvis'))
    for pose in POSES:
        off = offsets(pose)
        print('    %-18s %8.3f %8.3f %8.3f' % (pose['name'], off['head'], off['rib'], off['pelvis']))
    # **The count of masses that sit on the centre line.** The reference calls a mass on the line a common mistake, so
    # the number to drive to zero is how many of them are there rather than how far the others are.
    on_line = sum(1 for p in POSES for v in offsets(p).values() if v < 1e-9)
    print()
    print('  masses sitting exactly on the centre line: %d of %d' % (on_line, 3 * len(POSES)))
    print('  poses drawn: %d   (a figure with one pose is the fault this stage exists to fix)' % len(POSES))

    if args.render:
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(OUT), '--out', str(PNG)],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % PNG)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
