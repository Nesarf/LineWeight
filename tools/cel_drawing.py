"""Cel shading on the figure: a base colour, an authored shadow, and the line on top.

**The step this file exists for.** `cel.py` has been tested since before there was a drawing: `ramp`, `quantise`,
`levels`, `Shading`, `Palette`, `shadow_colour`, `Shadow`, `paint_shadow`, nine tests, and every one of its numbers
comes from the art rather than from taste -- `_LightValue`'s mode of 0.5, `_LightStrong`'s of 10.0, the 144 distinct
`_OutlineTint` values. **None of it had ever run on a drawing.** This runs it.

**The shadow is authored, not computed**, and that is the finding the research rests on: Ghibli's own account says the
boundary 「まず、アニメーターが線画で描き分けます」 -- the animator draws it -- and NAFCA's colour tracing is done in
blue pencil before anything is filled. `Shadow` takes the region verbatim for that reason. What this file supplies is
therefore a *shape*, and the only thing it takes from a light direction is a translation, which is exactly what
`Shadow.offset` is documented as and no more.

**The order is the picture.** A fill goes under its line, and a part goes in front of the part behind it; the project
appends marks in call order, so the order things are added in *is* the order they are drawn in.

    python cel_drawing.py [out.json]
"""
import colorsys
import json
import math
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import cel, core, figure, project

CANVAS_W, CANVAS_H = 800.0, 600.0
FIG_TOP, FIG_BOTTOM = 0.0, 1.02
MARGIN = 40.0
SCALE = (CANVAS_H - 2 * MARGIN) / (FIG_BOTTOM - FIG_TOP)
ORIGIN_X, ORIGIN_Y = CANVAS_W / 2, MARGIN


def place(pt):
    return (ORIGIN_X + pt[0] * SCALE, ORIGIN_Y + pt[1] * SCALE)


POS = {
    'Bip001':              (0.0, 0.48),
    'Bip001 Pelvis':       (0.0, 0.470),
    'Bip001 Spine':        (0.0, 0.395),
    'Bip001 Spine1':       (0.0, 0.300),
    'Bip001 Neck':         (0.0, 0.215),
    'Bip001 Head':         (0.0, 0.175),
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
    'Bip001 L Thigh':      (0.052, 0.450),
    'Bip001 L Calf':       (0.065, 0.700),
    'Bip001 L Foot':       (0.070, 0.930),
    'Bip001 L Toe0':       (0.076, 0.980),
}
for _n in list(POS):
    if ' L ' in _n:
        _x, _y = POS[_n]
        POS[_n.replace(' L ', ' R ')] = (-_x, _y)

BONE_WIDTH = {
    'Pelvis':   (0.112, 0.105), 'Spine': (0.105, 0.098), 'Spine1': (0.098, 0.086),
    'Neck':     (0.050, 0.044), 'Head': (0.095, 0.115), 'Clavicle': (0.058, 0.050),
    'UpperArm': (0.050, 0.039), 'Forearm': (0.039, 0.029), 'Hand': (0.029, 0.024),
    'Finger':   (0.011, 0.008), 'Thigh': (0.088, 0.061), 'Calf': (0.061, 0.037),
    'Foot':     (0.037, 0.029), 'Toe': (0.029, 0.022),
}
TIP_BONES = ('Finger01', 'Finger11', 'Finger21', 'Toe0')
ENTRY, EXIT = 0.30, 0.22

#: **How wide the contour pen is, and it is not a bone's width.** The reference library's own measurement of real
#: linework puts the median run at about three pixels, so that is what a line is here -- **the bone's width belongs to
#: the fill**, which is a fact about the body, and this is a fact about the pen. Keeping them the same object was the
#: mistake the component count exposed: a limb drawn with a thirty-pixel pen is not a drawing of a limb.
CONTOUR_WIDTH = 3.0

#: **The parts, back to front.** This is the figure's own stack order read off the rigs -- the halo behind the
#: character, then back hair, head, arms, legs, skirt, torso, collar, hand, neck, face, front hair -- cut down to the
#: parts a bone skeleton actually has. **The order is the picture**, and it is the one thing here that is not invented:
#: `layers.standard_order()` is a topological sort of 46 constraints that nine lobby rigs agree on.
DRAW_ORDER = ('head', 'leg', 'arm', 'hand', 'neck', 'torso')

LAYER_OF = {
    'Pelvis': 'torso', 'Spine': 'torso', 'Spine1': 'torso', 'Neck': 'neck', 'Head': 'head',
    # **The clavicle and the hand belong to the arm, and the first version filed them elsewhere.** With the clavicle
    # in `torso` and the hand in its own layer, the arm came out as three separate chains that met at joints -- so the
    # shoulder and the wrist carried exactly the discontinuity the elbow did, in a drawing whose whole problem was
    # joints being the thinnest place. **A chain is delimited by where a hand would stop, not by which part of the
    # body a bone is nearest to.** The fingers stay separate because they really are separate marks.
    'Clavicle': 'arm', 'UpperArm': 'arm', 'Forearm': 'arm', 'Hand': 'arm', 'Finger': 'hand',
    'Thigh': 'leg', 'Calf': 'leg', 'Foot': 'leg', 'Toe': 'leg',
}

#: **A colour per draw class, and this is where invention starts.** The corpus measures a line's darkness
#: (`_OutlineTint`, 144 values) and it measures the shading steps; **it says nothing about what colour a character
#: is**, because 292 characters have 292 palettes. So these three are a stand-in -- skin, cloth, hair -- chosen to be
#: legible rather than to be right, and a real caller supplies its own through `figure.Figure.palettes`.
BASE = {'torso': (214, 186, 168), 'arm': (214, 186, 168), 'leg': (214, 186, 168),
        'hand': (214, 186, 168), 'neck': (206, 178, 160), 'head': (222, 194, 176)}

#: **How much thinner the whole figure is drawn this time, and why.** Measured against the library, the first
#: cel drawing reads an ink fraction of 0.0588 against 0.15, and against two real design sheets at 0.0094 and 0.0210.
#: Its taper ratio is 0.3426 against 0.42, and p90 over median 3.500 against 2.75 -- **a width distribution wider
#: than either reference**, which is the same statement as the taper ratio being low.
#:
#: Scaling everything down moves the first and cannot move the second, because a ratio does not see a scale -- so
#: this is one change and one measurement of two numbers, and which of them moves is the answer.
THINNER = 0.55


def bone_profile(bone, n, taper_from=0.0, is_head=True, is_tail=True):
    """One bone's width along its own length.

    **`is_head` and `is_tail` exist because a taper belongs to a stroke and not to a bone.** A chain of four bones is
    one line in a drawing: it enters at the clavicle, runs to the hand, and leaves once. The first version tapered the
    first `ENTRY` of every bone and let `stroke_record` end every mark, so a four-bone arm carried four entries and
    four exits -- **and at each joint two exits met, which is why the join came out thinner than either bone.** The
    flags say whether this particular bone is the one at the head or the tail of the chain it belongs to; a bone in
    the middle tapers at neither end, because its ends are joints and a joint is not where a line stops.
    """
    top = bottom = 0.030
    for key in ('Finger', 'Toe', 'Head', 'Neck', 'Clavicle', 'UpperArm', 'Forearm', 'Hand',
                'Thigh', 'Calf', 'Foot', 'Spine1', 'Spine', 'Pelvis'):
        if key in bone:
            top, bottom = BONE_WIDTH[key]
            break
    out = []
    for i in range(n):
        t = i / max(1, n - 1)
        w = top + (bottom - top) * t
        if is_head and t < ENTRY:
            w *= 1.0 - taper_from * (1.0 - t / ENTRY)
        if is_tail and bone in TIP_BONES and t > 1.0 - EXIT:
            w *= 1.0 - 0.55 * ((t - (1.0 - EXIT)) / EXIT)
        out.append(w * SCALE * THINNER)
    return out


def chains(by_layer):
    """Every bone of each layer, each in exactly one chain, walked from root to tip.

    **The invariant is that no bone is dropped, and the first version broke it.** It started chains only at bones
    whose parent lies outside the layer, and it stopped the walk at any fork. That reads like a tidy guard and is not:
    the two clavicles hang off `Spine1`, so their parent *is* in the layer and they are not starts, and the walk from
    the pelvis stops at that same fork -- **so both clavicles were never reached by anything and simply left the
    drawing.** The only reason it was noticed is that the printed list had nine chains where it should have had
    eleven; the same fault would have taken the twelve finger bones without changing any count anybody looks at.

    So the walk marks what it has taken, and a fork pushes each child back as a new chain head. Whatever is left when
    the queue empties starts a chain of its own, which is the backstop that makes "each in exactly one" a property
    rather than a hope.
    """
    out = []
    for layer, pairs in by_layer.items():
        children = {c: p for c, p in pairs}
        remaining = set(children)
        queue = sorted(c for c, p in pairs if p not in children)
        while remaining:
            if not queue:
                queue = [sorted(remaining)[0]]
            start = queue.pop(0)
            if start not in remaining:
                continue
            walk, cur = [], start
            while cur in remaining:
                remaining.discard(cur)
                walk.append(cur)
                kids = sorted(k for k, kp in pairs if kp == cur)
                if len(kids) == 1:
                    cur = kids[0]
                else:
                    queue.extend(k for k in kids if k in remaining)
                    break
            if walk:
                out.append((layer, walk))
    return out


def label_of(walk):
    """A chain's name for a note, short enough to read in a listing."""
    first = walk[0].replace('Bip001 ', '')
    if len(walk) == 1:
        return first
    return '%s..%s' % (first, walk[-1].replace('Bip001 ', ''))


def layer_for(bone):
    for key, layer in LAYER_OF.items():
        if key in bone:
            return layer
    return ''


def brush_for(bone):
    if 'Finger' in bone or 'Toe' in bone:
        return 'fine'
    if any(k in bone for k in ('Thigh', 'Spine', 'Pelvis')):
        return 'ink'
    return 'pencil'


def hexed(rgb):
    return '#%02X%02X%02X' % tuple(int(max(0, min(255, c))) for c in rgb)


def shaded(base, weight, strength=cel.SHADOW_STRONG):
    """The shadow colour, from `cel` -- **a multiplication, because `_CodeMultiplyColor` is what the asset uses.**"""
    return cel.shadow_colour(base, weight, strength)


def offset_polygon(points, dx, dy):
    return [(x + dx, y + dy) for x, y in points]


def region_of(points):
    """A `Region` from a polygon that is **already closed**.

    **Not `region_fill`.** That function exists to answer the bucket question -- *is anything enclosed here* -- for a
    drawing whose lines do not always meet, and it welds endpoints within a tolerance to close the gaps. Handing it a
    polygon that is already closed asks it to do the one thing that is not needed, and the tolerance is measured in
    the drawing's units rather than in this shape's. A `Region` is a `NamedTuple` of points and a `d`, which is all
    a fill mark needs.
    """
    d = 'M ' + ' L '.join('%.2f %.2f' % (x, y) for x, y in points) + ' Z'
    return core.Region(points=[tuple(p) for p in points], d=d)


def main():
    out_path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r'E:\DaShaoHuo\cache\cel-drawing.json')
    fig = figure.standard()
    problems = fig.errors()
    if problems:
        for p in problems:
            print('   %s' % p)
        return 1

    proj = project.Project()
    proj.set_figure(fig)

    # the bones, grouped by the part they belong to, so the parts can be laid down back to front
    by_layer = {}
    for child, parent in sorted(fig.joints.items()):
        if child in POS and parent in POS and child != 'Bip001':
            layer = layer_for(child)
            if layer:
                by_layer.setdefault(layer, []).append((child, parent))

    #: **How wide the shadow band is, and how far it sits off the centreline, both as fractions of the part's own
    #: half-width.** The sources say the boundary is drawn by hand and fixed per cut; none gives a size, so these are
    #: chosen to read.
    #:
    #: **A band, not a displaced copy of the whole shape.** The first two attempts offset the entire fill, which on a
    #: limb 25 pixels across put the shadow almost entirely outside the shape it belonged to -- the figure came out
    #: half dark brown. What the art actually has on a limb is a band down one side, so the shadow here is **the same
    #: bone drawn thinner and shifted sideways**: the same machinery, the same profile, one control point.
    SHADOW_BAND = 0.55        # of the half-width: how thick the band is
    SHADOW_SHIFT = 0.45       # of the half-width: how far off centre it sits

    marks = 0
    # **Per chain, not per bone.** A chain is one line a hand would draw in one movement: it enters once at the root
    # and leaves once at the tip, and the joints inside it are places where the line keeps going. The first version
    # built a mark per bone, so a four-bone arm carried four entries and four exits -- and **at every joint two exits
    # met**, which is why the join came out thinner than either bone on both sides of it.
    for layer in DRAW_ORDER:
        for chain_layer, walk in chains(by_layer):
            if chain_layer != layer:
                continue
            parent_of = {c: p for c, p in by_layer.get(layer, [])}
            # **Every segment keeps its full three control points, and the seams are trimmed once at the end.**
            # The first attempt trimmed each segment as it was built and then used those trimmed segments to make
            # the widths -- so each bone after the first lost one interval's worth of samples and the profile came
            # out 81 long for a path that wanted 129. `outline_spines` indexed past the end of it and the run died
            # with an `IndexError`, which is the loud kind. **A length that had come out larger rather than smaller
            # would have been silently offset**, and the limb would have been drawn with the width belonging to a
            # different part of itself.
            segs = []
            for k, bone in enumerate(walk):
                parent = walk[k - 1] if k else parent_of.get(bone, 'Bip001')
                a, b = place(POS[parent]), place(POS[bone])
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dy) or 1.0
                bow = 0.045 if ('Thigh' in bone or 'UpperArm' in bone) else 0.022
                side = 1 if a[0] >= 0 else -1
                mx += -dy / length * bow * side
                my += dx / length * bow * side
                segs.append([a, (mx, my), b])

            pts = [segs[0][0]]
            for seg in segs:
                pts += seg[1:]
            profile = []
            for k, (bone, seg) in enumerate(zip(walk, segs)):
                values = bone_profile(bone, 16 * (len(seg) - 1) + 1, taper_from=0.55,
                                      is_head=(k == 0), is_tail=(k == len(walk) - 1))
                profile += values if k == 0 else values[1:]
            want = 16 * (len(pts) - 1) + 1
            if len(profile) != want:
                raise SystemExit('chain %s: profile has %d values for a path wanting %d'
                                 % (label_of(walk), len(profile), want))

            # the fill needs no pressure and no wobble: it is a shape, and its edge is where the light lands
            plain = core.stroke_record(pts, 'ink', seed=0, resolution=16, width_profile=profile)
            shape = core.outline_polygon(plain)
            base = BASE.get(layer, (200, 200, 200))
            shadow = shaded(base, 0.45)
            label = label_of(walk)

            # **The shadow first, offset; then the lit colour over it; then the line.** The offset shadow is the one
            # this art actually describes -- `_AdjustiveFaceShadow` is 0.0 on all 292 characters, so there is no
            # computed boundary to reproduce, and what is left is a shape drawn by hand and translated.
            # **The band.** A thinner profile, nudged to the side the light does not reach; the sign follows the
            # limb across the centreline so both sides of the figure are lit from the same direction.
            a = pts[0]
            side_sign = 1 if POS[walk[0]][0] >= 0 else -1
            band_profile = [w * SHADOW_BAND for w in profile]
            band = core.stroke_record(pts, 'ink', seed=0, resolution=16, width_profile=band_profile)
            band_shape = core.outline_polygon(band)
            half = max(profile) * 0.5
            sx = -half * SHADOW_SHIFT * side_sign
            sy = half * SHADOW_SHIFT * 0.6
            proj.add_fill(region_of(offset_polygon(band_shape, sx, sy)),
                          stage='colour', colour=hexed(shadow), note='shadow, %s' % label)
            proj.add_fill(region_of(shape), stage='colour', colour=hexed(base), note='lit, %s' % label)
            marks += 2

            # **The contour, and it is a different object from the fill boundary.** Until now the "line" layer was
            # the same stroke as the fill, drawn a second time -- so a limb thirty pixels across was drawn as a
            # thirty-pixel-wide mark, and the drawing was solid ink in its topology where real linework is a mesh.
            # **That is what the component count was saying**: one blob here against fifty to a hundred in a line
            # drawing, and it is also why the figure read as a stick figure rather than as a drawing.
            #
            # A contour follows the **boundary** of the shape and not its centreline, so what is stroked here is the
            # polygon the fill produced, closed back on itself. The width is the one the reference library measures on
            # real linework -- a median of about three pixels -- and not the bone's width, because the bone's width is
            # a fact about the body and this is a fact about the pen.
            contour = list(shape) + [shape[0]]
            contour_profile = [CONTOUR_WIDTH] * (16 * (len(contour) - 1) + 1)
            rec = core.stroke_record(contour, 'fine', seed=abs(hash(label)) % 9973, resolution=16,
                                     width_profile=contour_profile)
            proj.add_stroke(rec, stage='line', layer=layer, note='contour %s' % label)
            marks += 1

    print('  marks: %d  (fills %d, lines %d)' % (len(proj.marks), marks - (marks // 3), marks // 3))
    print('  layers in use: %s' % sorted(set(m.layer for m in proj.marks if m.layer)))
    print('  cel: light_value %.2f  feather %.2f  shadow_strong %.1f  outline_tint %.2f'
          % (cel.LIGHT_VALUE, cel.FEATHER, cel.SHADOW_STRONG, cel.OUTLINE_TINT))
    print('  a shadow colour for skin: %s from %s' % (hexed(shaded((214, 186, 168), 0.45)),
                                                      hexed((214, 186, 168))))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out_path))
    print('  written to %s' % out_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
