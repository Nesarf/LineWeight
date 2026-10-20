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


#: **Every vertical here is the corpus's own segment, scaled to the figure.** Measured over eleven rigs as the drop
#: from the top of the head over the whole height: head 0.180, neck 0.222, spine1 0.354, spine 0.438, pelvis 0.556,
#: thigh 0.557, calf 0.761, foot 0.941, toe 1.000, upper arm 0.282, hand 0.448. Multiply by `FIG_BOTTOM` and that is
#: where each bone goes.
#:
#: **The previous values were not those, and the error was mine to have caught sooner.** The pelvis sat at 0.461 where
#: the corpus puts it at 0.556 -- seventeen per cent adrift -- which made the trunk short and the legs long, and a
#: short trunk then disappeared behind a head drawn at the corpus's ratio. **The two measurements agreed with each
#: other and both disagreed with this table.**
#:
#: **The horizontal for the arm is the one width ratio that could be measured**: shoulder half-width over head
#: half-width is 0.816, so with a head half-width of 0.124 figure units the shoulder sits at 0.101 -- and the corpus's
#: own 0.096 agrees, which is the check that it is not an invention.
POS = {
    'Bip001':              (0.0, 0.55),
    'Bip001 Pelvis':       (0.0, 0.567),
    'Bip001 Spine':        (0.0, 0.447),
    'Bip001 Spine1':       (0.0, 0.361),
    'Bip001 Neck':         (0.0, 0.226),
    'Bip001 Head':         (0.0, 0.184),
    'Bip001 L Clavicle':   (0.054, 0.312),
    'Bip001 L UpperArm':   (0.098, 0.288),
    'Bip001 L Forearm':    (0.170, 0.392),
    'Bip001 L Hand':       (0.228, 0.457),
    'Bip001 L Finger0':    (0.252, 0.492),
    'Bip001 L Finger01':   (0.268, 0.512),
    'Bip001 L Finger1':    (0.258, 0.485),
    'Bip001 L Finger11':   (0.274, 0.504),
    'Bip001 L Finger2':    (0.253, 0.477),
    'Bip001 L Finger21':   (0.269, 0.495),
    'Bip001 L Thigh':      (0.058, 0.568),
    'Bip001 L Calf':       (0.070, 0.776),
    'Bip001 L Foot':       (0.074, 0.960),
    'Bip001 L Toe0':       (0.080, 1.000),
}
for _n in list(POS):
    if ' L ' in _n:
        _x, _y = POS[_n]
        POS[_n.replace(' L ', ' R ')] = (-_x, _y)

#: **The trunk's widths come from a silhouette, and they are three times what they were.**
#:
#: A rig gives bones, and a bone is a point -- it has no width. The widths here were derived from the corpus's head
#: ratio and came out at 0.098 for the upper chest, which is **a third of the shoulder span in a real illustration**:
#: the traced reference is 0.282 of the figure's own height across the shoulders. With a trunk that narrow the
#: shoulders had to be carried by the clavicle, drawn as a 0.058 stroke, and the render showed exactly that -- two thick
#: bars meeting at the sternum, reading as a spike rather than as a chest.
#:
#: **So the upper chest is the shoulder span minus one upper arm on each side** (0.282 - 2 x 0.05 = 0.232), and the
#: clavicle drops to a thin bone that the chest now covers. The waist and hip below it are a pinch between two measured
#: ends -- the reference's waist cannot be read on its own because the arms hang beside it -- and are named as a choice.
BONE_WIDTH = {
    'Pelvis':   (0.180, 0.170), 'Spine': (0.170, 0.200), 'Spine1': (0.200, 0.232),
    'Neck':     (0.050, 0.044), 'Head': (0.095, 0.115), 'Clavicle': (0.085, 0.062),
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

#: **How many points a stroked contour is reduced to.** The outline of a thick stroke carries four figures' worth of
#: points and a thin one a few dozen, so stroking both as they come gives one an edge so dense it reads as a jag and the
#: other an outline that covers its own fill. Reducing both to the same count makes the pen independent of the limb --
#: which is the whole point of separating the pen from the body.
CONTOUR_POINTS = 240

#: **The head is taller than it is wide, and it is a third of the figure.** Both came out of the corpus and both were
#: wrong in the other direction before. Measured over eleven rigs: the head's height is 0.361 of the body, the eye
#: separation 0.111, so a head is 3.25 eye-separations tall, and with a width of 2.2 separations its width over height
#: is 0.677.
#:
#: **This drawing had a head 32 wide by 22 high -- wider than tall, and a twentieth of the figure.** So it was wrong in
#: proportion and wrong in style: the corpus is drawn at about three heads tall and this was drawn at twenty. The
#: difference is not a measurement error, it is the difference between a chibi style and a realistic one, and the style
#: asked for is the corpus's.
#: **The head is 0.218 of the figure, and that number came out of a silhouette rather than a rig.**
#:
#: The rigs gave 0.361 and it was wrong in a way that only a picture could show: with the head hanging 0.361 downward
#: from the head bone at 0.184, the chin landed at **0.575 -- the pelvis** -- so the head covered the whole trunk, the
#: arms came out of the lower half of a skull, and no torso was visible at all.
#:
#: **Two sources, independent of each other, put the chin at about 0.22 instead**: the rigs' own neck bone sits at
#: 0.222, and the traced silhouette's narrowest point above the shoulders -- which is what a neck is -- is at 0.218 on
#: a real full-body illustration. **A head that ends at 0.575 and a neck bone at 0.222 cannot both be right**, and the
#: two that agree are the ones to keep. So the rig figure was measuring something other than the head's own height; it
#: is retained here only as the record of what was read wrongly.
HEAD_HEIGHT_OF_BODY = 0.218

#: **And it hangs from the top of the figure, not from the head bone.** In the rigs the head bone sits roughly at the
#: ear line -- 0.184 of the way down when the whole skull is 0.22 -- so anchoring to it would put the chin below the
#: neck whichever height is used.
HEAD_ANCHOR_OF_BODY = FIG_TOP

#: **The head's width over its height, and the rigs were 18 per cent too narrow.**
#:
#: The old figure of 0.677 came from an arithmetic chain: the rigs put a head at 3.25 eye-separations tall and 2.2
#: separations wide. **Three character meshes measured directly disagree.** Their face mesh -- the skin of the face,
#: chin to brow -- gives width over height as 0.810, 0.853 and 0.822, and they agree with each other on everything else
#: too: the chin sits at 0.781 to 0.797 of the figure's height, and the face is 0.131 to 0.147 of it.
#:
#:     Zome          face height 0.147   width 0.119   ratio 0.810   chin 0.794
#:     Cian          face height 0.147   width 0.125   ratio 0.853   chin 0.797
#:     RINDO         face height 0.131   width 0.108   ratio 0.822   chin 0.781
#:
#: **A mesh is not a chain of ratios.** The 2.2 eye-separations is a skull's width; a face as drawn carries cheeks and
#: ears, and an anime face is wider still at the cheekbone than its eye spacing suggests. So this is the measured
#: average of the three, and the reason it is trusted over the derivation is that it was measured on the thing itself.
HEAD_WIDTH_OVER_HEIGHT = 0.83

#: **The thinnest a limb may be and still keep its fill.** Below this the outline is wider than the shape and covers it
#: completely, which is what turned the hands into a solid black mass. A finger's fill is about three pixels across
#: here, so a three-pixel outline leaves nothing. Where the shape is thinner than that, the contour alone is the mark.
MIN_FILL_WIDTH = 7.0

#: **Hair is what makes an arm come out from behind something instead of out of a head.** The head is a filled ellipse
#: and the arms are laid across it, which reads as limbs emerging from inside a skull; in the corpus the sides of the
#: head are covered by hair and the arms sit in front of it. So this is a layer **wider than the head and drawn before
#: it**, and what shows is a band down each side.
#:
#: **Its width is a choice and it is named as one.** The corpus's layer order puts back hair and hair before the head
#: and the arms after it, so the arms are in front of the hair -- a band about a third wider than the head is what that
#: leaves visible. Nothing in the corpus measures it, because in the corpus hair is a mesh and not an ellipse.
HAIR_WIDTH_OF_HEAD = 1.34
HAIR_HEIGHT_OF_HEAD = 1.16
HAIR_COLOUR = (58, 52, 74)      # the ink-blue this character is described in, and a choice rather than a measurement
HAIR_SHADOW_COLOUR = (36, 32, 48)

#: **The fringe, and it is the single change that most makes a head read as a character.** A bare ellipse of skin with
#: two eyes in it is a mask; what turns it into a person is something covering the forehead with an edge of its own.
#:
#: **The edge is a chain of arcs and not a straight line.** A fringe cut straight across reads as a bowl; a real one is
#: a series of locks, each of which ends in a point, and they start and stop at different heights. The heights below
#: are chosen -- the corpus has hair meshes, and meshing is not something a bone skeleton describes.
FRINGE_LOCKS = 7
FRINGE_LOW = 0.30       # how far down the locks reach, in head radii below the head's centre
FRINGE_HIGH = 0.62      # and how far up the shortest of them stops
FRINGE_DIP = 0.09       # how far each lock's point hangs below its neighbours' meeting

#: The iris, and the one colour on a face that carries the most weight. The character's eyes are described as blue
#: with a violet cast, which is a description and not a measurement -- the corpus has 292 palettes and says nothing.
EYE_COLOUR = (74, 66, 132)

#: **The parts, back to front.** This is the figure's own stack order read off the rigs -- the halo behind the
#: character, then back hair, head, arms, legs, skirt, torso, collar, hand, neck, face, front hair -- cut down to the
#: parts a bone skeleton actually has. **The order is the picture**, and it is the one thing here that is not invented:
#: `layers.standard_order()` is a topological sort of 46 constraints that nine lobby rigs agree on.
DRAW_ORDER = ('hair', 'neck', 'torso', 'leg', 'arm', 'hand', 'head')

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
THINNER = 1.0


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


def smooth_closed(points, passes=3, keep=None):
    """A closed polygon with its corners knocked off, and resampled to a workable number of points.

    **Two faults in one place, and both came from the same thing.** The contour was stroked along the outline the fill
    produced, which is right -- a contour follows the boundary of a shape and not its centreline -- but that outline is
    a per-pixel approximation of a thick stroke's edge, so stroking it reproduced every pixel step as a jag. And its
    point count scales with the pen: a thigh drawn twenty-five pixels wide has four figures' worth of points while a
    finger has a few dozen, so one command produced an over-dense jagged edge on the thick limbs and an outline that
    swallowed the fill on the thin ones.

    So the outline is averaged around its own ring and then resampled evenly. **Averaging on a closed ring has to wrap
    at the seam** -- treating it as an open polyline pulls the polygon's start and end toward each other and leaves a
    visible pinch, which is the sort of thing that is easy to write and hard to notice.

    `keep` caps the number of points so that a thick limb and a thin one are stroked at comparable density.
    """
    pts = list(points)
    if len(pts) < 4:
        return pts
    for _ in range(max(0, passes)):
        n = len(pts)
        pts = [((pts[(i - 1) % n][0] + 2 * pts[i][0] + pts[(i + 1) % n][0]) / 4.0,
                (pts[(i - 1) % n][1] + 2 * pts[i][1] + pts[(i + 1) % n][1]) / 4.0) for i in range(n)]
    if keep and len(pts) > keep:
        step = len(pts) / float(keep)
        pts = [pts[int(i * step)] for i in range(keep)]
    return pts


def add_fringe(proj, cx, cy, rx, ry):
    """The fringe: one filled shape whose lower edge is a chain of locks.

    **One shape, not seven.** Drawing seven locks as seven marks leaves seven outlines, and locks share their edges --
    so what is filled here is a single region whose lower boundary zigzags. That is also what makes the lock points
    read as points instead of as the ends of sticks.

    **It covers the top of the head down past the brow line**, and the brow sits at +0.500 head radii above the
    centre, so the locks reach below that: a fringe that stops short of the brows leaves a band of forehead and the
    face reads as bald.
    """
    far = rx * 1.06
    edge = []
    for i in range(FRINGE_LOCKS):
        # each lock's outer point, then the notch between it and the next
        t0 = i / float(FRINGE_LOCKS)
        t1 = (i + 0.5) / float(FRINGE_LOCKS)
        t2 = (i + 1) / float(FRINGE_LOCKS)
        drop0 = FRINGE_LOW + (FRINGE_HIGH - FRINGE_LOW) * ((i * 37) % 5) / 4.0
        edge.append((cx - far + 2 * far * t0, cy - ry * drop0))
        edge.append((cx - far + 2 * far * t1, cy - ry * (drop0 - FRINGE_DIP)))
    edge.append((cx + far, cy - ry * (FRINGE_LOW + (FRINGE_HIGH - FRINGE_LOW) * ((FRINGE_LOCKS * 37) % 5) / 4.0)))
    # **The top edge follows the head's own arc, not a straight line.** A rectangle over a round head leaves two
    # square corners standing outside it, which is what the first version looked like -- a helmet rather than hair.
    cap = []
    for i in range(25):
        t = math.pi * (1.0 - i / 24.0)          # from the left of the arc over the top to the right
        cap.append((cx + far * math.cos(t), cy - ry * 1.02 * math.sin(t)))
    shape = cap + edge[::-1]
    proj.add_fill(region_of(shape), stage='colour', colour=hexed(HAIR_COLOUR), note='fringe')
    return 1


def add_face(proj, cx, cy, rx, ry):
    """Eyes, brows and a mouth on the head's own ellipse, placed by the corpus and shaped here.

    **The positions are measured and the shapes are not**, and that split is deliberate. Eleven rigs give the eye at
    (+/-0.308, -0.126) in head radii, the brow at (+/-0.299, +0.500) and the halo at (0.000, +2.003), with the brows
    moving only a tenth of a head radius between characters. **The corpus has no data for how large an eye is**,
    because a rig carries a bone where the eye sits and nothing where its outline goes -- so the sizes below are
    chosen, and named as chosen.

    **An eye is three marks, not one arc.** The first version drew an upward curve, which reads as a closed eye or as
    an eyebrow; a drawn eye at this size is an upper lid, an iris under it, and a highlight in the iris. That is the
    difference between a face and two lines on a head.
    """
    made = 0
    #: sizes in head radii; chosen, since the corpus gives position and not extent
    EYE_W, EYE_H = 0.17, 0.13
    #: **Eye width is set by the space between the eyes, not the other way round.** The articles give the gap as one
    #: eye-width, or 1.3 for a youthful face -- and this drawing measured 2.05, which is past the point where the
    #: articles say the face turns into a flounder. Two constraints fix the number: the gap is 0.616 head radii, so an
    #: iris half-width of 0.237 gives 0.616 / 0.474 = 1.30.
    #:
    #: **And the enlargement is the point rather than a side effect.** Half the head's width is now eye, which is what a
    #: chibi face is; the other articles say the same thing from the other side -- make the pupil larger and the face
    #: reads softer.
    IRIS_W = 0.237
    #: **An almond is not a flattened ellipse.** The upper edge turns tightly and the lower one runs nearly level --
    #: two different curvatures meeting at the corners, which is what makes an eye an almond and a circle a circle.
    #: So the iris is built from those two edges rather than from one radius, and the asymmetry is the whole point.
    IRIS_UP = 0.190       # how far the upper edge rises above the eye's line
    IRIS_DOWN = 0.075     # how far the lower edge falls below it
    SPARK_W, SPARK_H = 0.045, 0.045
    BROW_W, BROW_LIFT = 0.20, 0.06
    MOUTH_W, MOUTH_DROP = 0.10, 0.26

    for side in (-1, 1):
        ex = cx + side * 0.308 * ry
        ey = cy + 0.126 * ry            # screen y grows downward, so a negative corpus y is a positive offset
        # the iris: an almond, the darkest thing on the face
        iris = []
        for i in range(19):             # the upper edge, running from the outer corner to the inner
            t = math.pi * i / 18.0
            iris.append((ex - IRIS_W * ry * math.cos(t), ey - IRIS_UP * ry * math.sin(t)))
        for i in range(1, 19):          # the lower edge, back the other way and much flatter
            t = math.pi * (1.0 - i / 18.0)
            iris.append((ex - IRIS_W * ry * math.cos(t), ey + IRIS_DOWN * ry * math.sin(t)))
        proj.add_fill(region_of(iris), stage='colour', colour=hexed(EYE_COLOUR), note='iris %d' % side)
        made += 1
        # the highlight, off-centre toward the light, which is what makes an eye look wet
        sx = ex - side * 0.07 * ry
        sy = ey - 0.09 * ry
        spark = [(sx + SPARK_W * ry * math.cos(i / 16.0 * 2 * math.pi),
                  sy + SPARK_H * ry * math.sin(i / 16.0 * 2 * math.pi)) for i in range(17)]
        proj.add_fill(region_of(spark), stage='colour', colour='#F6F2EA', note='highlight %d' % side)
        made += 1
        # **The lid follows the iris's own upper edge**, so the two cannot drift apart when either is adjusted. The
        # first version gave the lid its own curvature and the two disagreed -- a lid that does not sit on the iris
        # reads as a line drawn near an eye rather than as the eye's edge.
        lid = [(ex - IRIS_W * ry * 1.06, ey - IRIS_UP * ry * 0.10),
               (ex, ey - IRIS_UP * ry * 1.10),
               (ex + IRIS_W * ry * 1.06, ey - IRIS_UP * ry * 0.10)]
        rec = core.stroke_record(lid, 'fine', seed=abs(hash(('lid', side))) % 9973, resolution=16,
                                 width_profile=[1.6, 3.4, 1.6])
        proj.add_stroke(rec, stage='line', layer='head', note='lid %d' % side)
        made += 1
        # **The brow is the same pen as the lid and only slightly lighter.** It was drawn with the pencil brush at a
        # width of 1.6 to 2.6 and came out nearly invisible -- the brush's alpha, not its width, was what made it
        # faint, and a brow that is fainter than the eye it belongs to reads as a smudge.
        bx = cx + side * 0.299 * ry
        by = cy - 0.500 * ry
        brow = [(bx - BROW_W * ry, by + BROW_LIFT * ry * 0.4),
                (bx, by - BROW_LIFT * ry),
                (bx + BROW_W * ry, by + BROW_LIFT * ry * 0.4)]
        rec = core.stroke_record(brow, 'fine', seed=abs(hash(('brow', side))) % 9973, resolution=16,
                                 width_profile=[1.4, 2.6, 1.4])
        proj.add_stroke(rec, stage='line', layer='head', note='brow %d' % side)
        made += 1

    # the mouth, a shallow curve below the eyes; its place is a ratio rather than a bone
    mx, my = cx, cy + MOUTH_DROP * ry
    mouth = [(mx - MOUTH_W * ry, my), (mx, my + 0.06 * ry), (mx + MOUTH_W * ry, my)]
    rec = core.stroke_record(mouth, 'fine', seed=abs(hash('mouth')) % 9973, resolution=16,
                             width_profile=[1.2, 2.0, 1.2])
    proj.add_stroke(rec, stage='line', layer='head', note='mouth')
    made += 1
    return made


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
            # **The head is an ellipse of its own, not the outline of a bone's stroke.** A bone describes an axis and a
            # thickness; a head is not described by that, and the difference shows -- the same machinery produced a
            # rounded rectangle where an ellipse belongs. Its size is the corpus's ratio of the body, and it hangs
            # downward from the head bone, which sits at the top of the figure.
            if walk == ['Bip001 Head']:
                body_px = (FIG_BOTTOM - FIG_TOP) * SCALE
                h = HEAD_HEIGHT_OF_BODY * body_px
                hx, hy = place((POS['Bip001 Head'][0], HEAD_ANCHOR_OF_BODY))
                # **0.218 is the whole head, hair included**, and the skin ellipse is that divided by the hair's own
                # growth. Applying the whole-head figure to the skin was the earlier fault: the hair was then sized
                # up from the skin, so the visible head came out larger than the number it was given.
                hh_skin = h / HAIR_HEIGHT_OF_HEAD
                hy_skin = hy + (h - hh_skin) / 2.0
                cy = hy_skin + hh_skin / 2.0
                rx = hh_skin * HEAD_WIDTH_OVER_HEIGHT / 2.0
                ry = hh_skin / 2.0
                shape = [(hx + rx * math.cos(i / 48.0 * 2 * math.pi),
                          cy + ry * math.sin(i / 48.0 * 2 * math.pi)) for i in range(49)]
            else:
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

            # **The hair, drawn for the head only and as a layer of its own.** It is wider than the head and comes
            # before it in `DRAW_ORDER`, so the head covers its middle and a band shows down each side -- which is
            # what stops the arms from looking as if they emerge from inside a skull. It has no shadow band: hair is
            # one flat colour here, and inventing a second one would be inventing twice.
            if walk == ['Bip001 Head']:
                body_px = (FIG_BOTTOM - FIG_TOP) * SCALE
                hh = HEAD_HEIGHT_OF_BODY * body_px
                hx, hy = place((POS['Bip001 Head'][0], HEAD_ANCHOR_OF_BODY))
                hp_ry = hh * HAIR_HEIGHT_OF_HEAD / 2.0
                hp_rx = hh * HEAD_WIDTH_OVER_HEIGHT * HAIR_WIDTH_OF_HEAD / 2.0
                hp_cy = hy + hh / 2.0
                hair_shape = [(hx + hp_rx * math.cos(i / 48.0 * 2 * math.pi),
                               hp_cy + hp_ry * math.sin(i / 48.0 * 2 * math.pi)) for i in range(49)]
                proj.add_fill(region_of(hair_shape), stage='colour', colour=hexed(HAIR_COLOUR),
                              note='hair, behind the head')
                marks += 1

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
            # polygon the fill produced. **But not raw**: the first version stroked that polygon as it came, and it
            # showed three faults in the render -- a jagged edge, a head turned into a square, and hands turned into
            # solid black. All three were the same thing: the polygon is a per-pixel approximation whose point count
            # scales with the pen, so a twenty-five-pixel thigh was stroked with four figures' worth of steps while a
            # three-pixel finger had so few that the outline swallowed its fill. **Smoothing and a fixed cap make the
            # pen independent of the limb.**
            ring = smooth_closed(shape, passes=3, keep=CONTOUR_POINTS)
            contour = ring + [ring[0]]
            # **The pen narrows where the limb does.** A three-pixel outline around a three-pixel finger covers it
            # entirely, which is what made the hands a solid black mass -- and no fixed width fixes that, because the
            # same three pixels are right on a thigh and wrong on a finger. Capping the pen at a fraction of the
            # shape's own thinnest point keeps a sliver of fill visible at every width, so the rule scales instead of
            # needing a table.
            cwidth = min(CONTOUR_WIDTH, MIN_FILL_WIDTH and 0.55 * min(profile))
            contour_profile = [cwidth] * (16 * (len(contour) - 1) + 1)
            rec = core.stroke_record(contour, 'fine', seed=abs(hash(label)) % 9973, resolution=16,
                                     width_profile=contour_profile)
            proj.add_stroke(rec, stage='line', layer=layer, note='contour %s' % label)
            marks += 1

    # **The face comes last, after every body layer, because it is in front of all of them.** Drawn where the head is
    # drawn, the neck and the trunk were laid over its lower half -- laid out on the crop of the head it was plain that
    # the eyes had been buried under the shoulders. The corpus agrees: its own order puts `face` at 16, after `neck`
    # at 14, with only `front_hair` in front of it. So this is not a preference, it is the order the asset uses.
    body_px = (FIG_BOTTOM - FIG_TOP) * SCALE
    hh = HEAD_HEIGHT_OF_BODY * body_px
    hh_skin = hh / HAIR_HEIGHT_OF_HEAD
    hx, hy = place((POS['Bip001 Head'][0], HEAD_ANCHOR_OF_BODY))
    face_cy = hy + (hh - hh_skin) / 2.0 + hh_skin / 2.0
    face_rx = hh_skin * HEAD_WIDTH_OVER_HEIGHT / 2.0
    face_ry = hh_skin / 2.0
    # **The fringe goes on before the face and after every body layer**, which is the one place in the order that is
    # both: the corpus has `face` at 16 and `front_hair` at 18, so the fringe is over the body and the face is over the
    # fringe -- and a fringe drawn after the face would cover the eyes it is framing.
    marks += add_fringe(proj, hx, face_cy, face_rx, face_ry)
    marks += add_face(proj, hx, face_cy, face_rx, face_ry)

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
