"""A first real drawing: a posed skeleton, stroked, layered, shaded, and put through the gate.

**Why this exists.** Everything in the library has been tested in pieces. Nothing has been drawn from end to end --
`body` knows what a body is, `layers` knows the order, `figure` binds them, `cel` knows the shading, and `project` has
the gate. What has never happened is a single flow that uses all of them, and the question this answers is not "does
it work" but **"what does the gate catch when something is really being drawn"**.

**The pose is invented and that is stated rather than hidden.** The figure carries the *hierarchy* -- which bone
hangs off which -- and the corpus carries which bones exist and how they branch. **No joint position exists anywhere in
this project**, because the census read parent links out of the rig files and never read transforms. So the positions
below are a hand-written standing pose, and they are the one part of this drawing that is not measured from anything.

    python first_drawing.py [out.json]
"""
import json
import math
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import cel, core, figure, project

# --------------------------------------------------------------------------------------------------------------------
# The pose. `None` in the joint table means "carried by the figure"; every bone in the 34-bone variant gets one.
#
# Proportions are the ordinary ones for this style -- roughly seven heads, the head being the unit below -- and the
# figure runs from y = 0 at the top of the head to y = 1 at the sole. **The pose is an A-pose**, arms about 40 degrees
# off vertical, because a T-pose puts the arms at a right angle to the body and the shoulder is the one joint where
# that reads as wrong.
HEAD = 0.143
# **The pose is written normalised and scaled on the way out, because the canvas is in pixels.** The first version of
# this file emitted the normalised numbers directly and drew a figure 0.85 units tall on an 800x600 canvas -- about a
# pixel. **`--render` reported it** ("17 px covered, 0.0%"), which is the one place in this flow that noticed.
FIG_TOP, FIG_BOTTOM = 0.0, 1.02
CANVAS_W, CANVAS_H = 800.0, 600.0
MARGIN = 40.0
SCALE = (CANVAS_H - 2 * MARGIN) / (FIG_BOTTOM - FIG_TOP)
ORIGIN_X, ORIGIN_Y = CANVAS_W / 2, MARGIN


def place(pt):
    """Normalised pose -> canvas pixels."""
    return (ORIGIN_X + pt[0] * SCALE, ORIGIN_Y + pt[1] * SCALE)


POS = {
    # **Seven heads, measured from the top of the skull.** Head 0.00-0.143, so the chin is at 0.143 and every other
    # landmark follows from it: shoulders at a head and a half, waist at three, hip at three and a half, knee just
    # past five, ankle at seven. The first version had the legs running from 0.59 to 1.0 and the torso only 0.27,
    # which drew a figure whose waist was where its chest should be.
    'Bip001':              (0.0, 0.48),
    'Bip001 Pelvis':       (0.0, 0.470),
    'Bip001 Spine':        (0.0, 0.395),
    'Bip001 Spine1':       (0.0, 0.300),
    'Bip001 Neck':         (0.0, 0.215),
    'Bip001 Head':         (0.0, 0.175),
    # arms: shoulder -> elbow -> wrist, about 35 degrees off vertical
    'Bip001 L Clavicle':   (0.042, 0.270),
    'Bip001 L UpperArm':   (0.078, 0.285),
    'Bip001 L Forearm':    (0.150, 0.385),
    'Bip001 L Hand':       (0.205, 0.478),
    'Bip001 L Finger0':    (0.228, 0.512),
    'Bip001 L Finger01':   (0.243, 0.532),
    'Bip001 L Finger1':    (0.233, 0.505),
    'Bip001 L Finger11':   (0.249, 0.524),
    'Bip001 L Finger2':    (0.229, 0.497),
    'Bip001 L Finger21':   (0.244, 0.515),
    # legs: hip -> knee -> ankle -> toe
    'Bip001 L Thigh':      (0.052, 0.450),
    'Bip001 L Calf':       (0.065, 0.700),
    'Bip001 L Foot':       (0.070, 0.930),
    'Bip001 L Toe0':       (0.076, 0.980),
}
for name in list(POS):
    if ' L ' in name:
        x, y = POS[name]
        POS[name.replace(' L ', ' R ')] = (-x, y)

# Which layer each bone's stroke lands on. The library requires a layer and requires the figure to declare it, so this
# table is where the drawing says what it is drawing.
LAYER_OF = {
    'Pelvis': 'torso', 'Spine': 'torso', 'Spine1': 'torso',
    'Neck': 'neck', 'Head': 'head',
    'Clavicle': 'torso', 'UpperArm': 'arm', 'Forearm': 'arm',
    'Hand': 'hand', 'Finger': 'hand',
    'Thigh': 'leg', 'Calf': 'leg', 'Foot': 'leg', 'Toe': 'leg',
}

#: **How thick each bone is, at the end that meets its parent and at the end that meets its child**, in units of the
#: figure's height. A limb is not a line of constant width: a thigh is twice the thickness of the shin below it, and
#: the taper from one to the other is most of what makes a limb read as a limb rather than as a pipe.
#:
#: **These are hand-authored, and so is the pose.** The corpus measures the *width of a line* -- `ref.py` reports a
#: median of 4.0 and a p90 of 11.0 on real artwork -- and a limb's thickness is a different quantity that nothing here
#: has measured. The proportions are the ordinary ones for a seven-head figure; they are not fitted to anything.
BONE_WIDTH = {
    'Pelvis':   (0.112, 0.105),
    'Spine':    (0.105, 0.098),
    'Spine1':   (0.098, 0.086),
    'Neck':     (0.050, 0.044),
    'Head':     (0.095, 0.115),
    'Clavicle': (0.058, 0.050),
    'UpperArm': (0.050, 0.039),
    'Forearm':  (0.039, 0.029),
    'Hand':     (0.029, 0.024),
    'Finger':   (0.011, 0.008),
    'Thigh':    (0.088, 0.061),
    'Calf':     (0.061, 0.037),
    'Foot':     (0.037, 0.029),
    'Toe':      (0.029, 0.022),
}

#: The bones whose far end is the end of the body, so the stroke there really does exit. **Everywhere else a bone
#: meets another bone**, and tapering into a joint would draw a pinch at the knee that the body does not have.
TIP_BONES = ('Finger01', 'Finger11', 'Finger21', 'Toe0')

#: How much of the length an entry or an exit takes, when there is one.
ENTRY = 0.30
EXIT = 0.22


def bone_profile(bone: str, n: int, taper_from=0.0) -> list[float]:
    """The thickness along a bone, in canvas pixels, sampled at the `n` points the stroke has.

    **The width profile is used as given, so the brush's own entry and exit do not apply** -- which is why the taper
    is written here rather than left to the brush. A profile that set a constant width would draw a limb as a length
    of pipe: worse than the thin line it replaced, because a thin line at least has the brush's taper at its ends.
    """
    top, bottom = 0.0, 0.0
    for key in ('Finger', 'Toe', 'Head', 'Neck', 'Clavicle', 'UpperArm', 'Forearm', 'Hand',
                'Thigh', 'Calf', 'Foot', 'Spine1', 'Spine', 'Pelvis'):
        if key in bone:
            top, bottom = BONE_WIDTH[key]
            break
    if not top:
        top = bottom = 0.030
    out = []
    for i in range(n):
        t = i / max(1, n - 1)
        w = top + (bottom - top) * t
        # **An entry where the stroke actually starts, and an exit where the body actually ends.** The first bone of
        # a chain enters the paper; every later one continues from the bone before it, so only `taper_from` and a tip
        # are tapered and a knee is not pinched.
        if t < ENTRY:
            w *= 1.0 - taper_from * (1.0 - t / ENTRY)
        if bone in TIP_BONES and t > 1.0 - EXIT:
            w *= 1.0 - 0.55 * ((t - (1.0 - EXIT)) / EXIT)
        out.append(w * SCALE)
    return out


# The brush a bone is drawn with. Weight follows the bone: a thigh is heavy, a finger is not.
def brush_for(bone: str) -> str:
    if 'Finger' in bone:
        return 'fine'
    if 'Toe' in bone:
        return 'fine'
    if any(k in bone for k in ('Thigh', 'Spine', 'Pelvis')):
        return 'ink'
    return 'pencil'


def layer_for(bone: str) -> str:
    for key, layer in LAYER_OF.items():
        if key in bone:
            return layer
    return ''


def bone_pairs(fig):
    """(child, parent) for every joint whose parent is also placed."""
    for child, parent in fig.joints.items():
        if child in POS and parent in POS and child != 'Bip001':
            yield child, parent


def arm_outline(points, brush_name, scale=1.0):
    """The brush's width at the two ends, so a limb tapers in the direction it is drawn."""
    b = core.BRUSHES[brush_name]
    return b['width'] * scale


def main():
    out_path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r'E:\DaShaoHuo\cache\first-drawing.json')
    fig = figure.standard()

    print('=== the figure the drawing declares')
    print(figure.describe(fig))
    problems = fig.errors()
    if problems:
        print('REFUSED: %d problem(s)' % len(problems))
        for p in problems:
            print('   %s' % p)
        return 1

    proj = project.Project()
    proj.set_figure(fig)
    print('set_figure accepted it (it raises on one that could not exist)')

    # ---- the strokes: one per bone, in the layer the bone belongs to
    drawn, skipped = 0, []
    for child, parent in sorted(bone_pairs(fig)):
        layer = layer_for(child)
        if not layer:
            skipped.append(child)
            continue
        brush = brush_for(child)
        a, b = place(POS[parent]), place(POS[child])
        # **A slight bow on the long bones.** A skeleton of straight segments reads as a diagram, which is the failure
        # this library exists to prevent, so the limb bends by a few percent of its length toward the outside.
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        bow = 0.045 if 'Thigh' in child or 'UpperArm' in child else 0.022
        mx += -dy / length * bow * (1 if a[0] >= 0 else -1)
        my += dx / length * bow * (1 if a[0] >= 0 else -1)
        pts = [a, (mx, my), b]
        # **The bone's own thickness, sampled at the points the stroke will have.** `stroke_record` expands the
        # control points through a Catmull-Rom curve at `resolution`, so the profile has to be as long as the
        # expanded path or it is read short -- `stroke_layer` indexes it by the point it is drawing.
        n = 16 * (len(pts) - 1) + 1
        rec = core.stroke_record(pts, brush, seed=abs(hash(child)) % 9973, resolution=16,
                                 width_profile=bone_profile(child, n,
                                                            taper_from=0.55 if parent == 'Bip001' else 0.0))
        proj.add_stroke(rec, stage='line', layer=layer, note='bone %s' % child)
        drawn += 1

    print('strokes: %d drawn, %d bones had no layer' % (drawn, len(skipped)))
    if skipped:
        print('   skipped: %s' % ', '.join(s.split()[-1] for s in skipped[:8]))

    # ---- hair: the one thing not on the skeleton, and it belongs on its own layers
    # **Behind the head and to one side.** The first version ran it down the centre of the figure with a 22-unit
    # wash, which covered the torso and read as a smear rather than as hair.
    hair_back = [place(p) for p in [(0.055, 0.045), (0.088, 0.100), (0.095, 0.190), (0.088, 0.290),
                                    (0.070, 0.380), (0.048, 0.440)]]
    hair_front = [place(p) for p in [(-0.058, 0.055), (-0.048, 0.095), (0.020, 0.070), (0.058, 0.100)]]
    proj.add_stroke(core.stroke_record(hair_back, 'ink', seed=11, resolution=24),
                    stage='line', layer='back_hair', note='the mass behind the head')
    proj.add_stroke(core.stroke_record(hair_front, 'pencil', seed=12, resolution=18),
                    stage='line', layer='front_hair', note='the fringe')

    # ---- face: eyes, brows, mouth, each on the layer its class belongs to
    for side in (1, -1):
        ex = 0.030 * side
        proj.add_stroke(core.stroke_record([place(p) for p in [(ex - 0.016, 0.245), (ex, 0.241), (ex + 0.016, 0.245)]],
                                           'ink', seed=20 + side, resolution=14),
                        stage='line', layer='eye', note='eye')
        proj.add_stroke(core.stroke_record([place(p) for p in [(ex - 0.018, 0.222), (ex, 0.217), (ex + 0.018, 0.222)]],
                                           'pencil', seed=30 + side, resolution=14),
                        stage='line', layer='eyebrow', note='brow')
    proj.add_stroke(core.stroke_record([place(p) for p in [(-0.012, 0.196), (0.0, 0.193), (0.012, 0.196)]],
                                       'fine', seed=40, resolution=14),
                    stage='line', layer='mouth', note='mouth')
    # **The jaw is a closed curve from cheek to chin to cheek, not a triangle.** Drawn as a peak it read as a pointed
    # hat -- the single most visible thing wrong with the first render.
    jaw = [place(p) for p in [(-0.062, 0.075), (-0.050, 0.115), (-0.020, 0.140), (0.020, 0.140),
                              (0.050, 0.115), (0.062, 0.075)]]
    proj.add_stroke(core.stroke_record(jaw, 'fine', seed=41, resolution=20),
                    stage='line', layer='face', note='the jaw')

    print('marks: %d' % len(proj.marks))
    print('layers in use: %s' % sorted(set(m.layer for m in proj.marks)))
    declared = fig.layer_names()
    undeclared = sorted(set(m.layer for m in proj.marks) - declared)
    print('layers used that the figure does NOT declare: %s' % (undeclared or 'none'))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out_path))
    print()
    print('written to %s' % out_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
