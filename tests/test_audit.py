"""Tests for the independent referee.

**What these can and cannot establish.** They establish that `raster.fill_polygon` agrees with cairo about the same
points, and that `outline()` agrees with cairo's stroker about the same centreline. They cannot establish that either
is *right* -- cairo is a second opinion, not the truth. The tests are written so that a disagreement is a number
rather than a vibe, because the one thing this project keeps getting wrong is believing a check that had no way to
fail.

The determinism tests are here because a render that is not reproducible makes "I looked at it" an anecdote, and this
module exists specifically so that looking at something counts as evidence.
"""

import hashlib
import io
import math
import os
import subprocess
import sys
import textwrap

import pytest

from lineweight import audit, raster
from lineweight.core import BRUSHES, outline_points, parse_path, polygon_to_path, stroke_record

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INK = float(BRUSHES['ink']['width'])     # the `ink` brush's width, used as the constant for referee B


# -------------------------------------------------------------------------------------------------------- fixtures

def a_stroke(control, seed=3, mark_id='m0001', seq=1, state='live'):
    """A stroke mark built through the product's own record rather than by hand.

    Hand-built geometry would let a test agree with itself about a shape the library never produces. `stroke_record`
    is where catmull smoothing and the pressure model live, and the referee's findings change completely once those
    are in the path -- a 90-degree control point is only a 25-degree sampled turn.
    """
    return {'id': mark_id, 'kind': 'stroke', 'stage': 'line', 'seq': seq, 'state': state,
            'geometry': stroke_record(control, 'ink', seed=seed),
            'appearance': {'colour': '#1A1620'}, 'provenance': {}}


def a_drawing():
    return [
        a_stroke([(10, 50), (70, 20), (130, 70), (190, 40)], seed=1, mark_id='m0001', seq=1),
        a_stroke([(20, 100), (100, 120), (180, 90)], seed=2, mark_id='m0002', seq=2),
        a_stroke([(30, 30), (90, 130), (150, 30)], seed=3, mark_id='m0003', seq=3),
    ]


def a_hairpin():
    """The shape the referee found the bug with: a stroke that doubles back on itself."""
    return a_stroke([(10, 50), (190, 50), (10, 50)], seed=3)


def png_bytes(surface):
    """A surface as PNG bytes, without touching the filesystem.

    `write_to_png` takes a file object, so the determinism tests never have to invent a path -- and a test that wrote
    files would be a test that could pass because of a file it found.
    """
    handle = io.BytesIO()
    surface.write_to_png(handle)
    return handle.getvalue()


def coverage_of(polygons, size, fill_rule='nonzero'):
    """`raster.fill_polygon`'s coverage in pixels, at a chosen fill rule.

    Local rather than `audit.coverage_raster` because the whole point of the negative control below is to run the
    shipping rasteriser with the rule it *used* to have.
    """
    layer = raster.Layer(*size)
    for points in polygons:
        raster.fill_polygon(layer, points, (255, 255, 255), 1.0, 1.0, fill_rule)
    return sum(layer.data[3::4]) / 255.0


# ----------------------------------------------------------------------------------------------------- determinism

def test_the_same_marks_render_to_the_same_bytes():
    """Two renders of one drawing are byte-identical.

    Pinned because "I looked at the render" is only evidence if the render is the same thing next time. cairo writes
    no timestamp, but that is a property of someone else's library and this asserts it rather than trusting it.
    """
    view = audit.View.whole(200, 160)
    first = png_bytes(audit.render(a_drawing(), view, colours=audit.stroke_colours(3)))
    second = png_bytes(audit.render(a_drawing(), view, colours=audit.stroke_colours(3)))
    assert first == second
    assert len(first) > 1000, 'a picture this small means nothing was drawn'


def test_the_same_marks_render_to_the_same_bytes_in_a_fresh_process():
    """And byte-identical across processes, under different hash seeds.

    **A different process is the only way to catch the class of non-determinism that matters here**: iteration over a
    set or a dict keyed by string can depend on `PYTHONHASHSEED`, and it would never show up in one process. Two seeds
    and the parent's own result have to agree.
    """
    script = textwrap.dedent('''
        import hashlib, io, sys
        sys.path.insert(0, %r)
        from lineweight import audit
        from lineweight.core import stroke_record
        marks = [{'id': 'm%%04d' %% i, 'kind': 'stroke', 'stage': 'line', 'seq': i, 'state': 'live',
                  'geometry': stroke_record(ctrl, 'ink', seed=i),
                  'appearance': {'colour': '#1A1620'}, 'provenance': {}}
                 for i, ctrl in enumerate(
                     ([(10, 50), (70, 20), (130, 70), (190, 40)],
                      [(20, 100), (100, 120), (180, 90)],
                      [(30, 30), (90, 130), (150, 30)]), start=1)]
        surface = audit.render(marks, audit.View.whole(200, 160),
                               colours=audit.stroke_colours(3))
        handle = io.BytesIO()
        surface.write_to_png(handle)
        sys.stdout.write(hashlib.sha256(handle.getvalue()).hexdigest())
    ''') % REPO
    digests = set()
    for seed in ('0', '12345'):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=REPO)
        # `stdin=DEVNULL` is not tidiness: pytest replaces `sys.stdin` with an object whose `fileno()` is not a real
        # handle, and subprocess tries to duplicate it before it ever reaches the command -- WinError 6, which reads
        # as a problem with the render rather than with who is running the test.
        out = subprocess.run([sys.executable, '-c', script], cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=180)
        assert out.returncode == 0, out.stderr[-2000:]
        digests.add(out.stdout.strip())
    here = hashlib.sha256(png_bytes(
        audit.render(a_drawing(), audit.View.whole(200, 160), colours=audit.stroke_colours(3)))).hexdigest()
    assert digests == {here}, 'the render depends on the process it ran in: %r vs %r' % (digests, here)


# ------------------------------------------------------------------------------------------------------------ view

def test_a_whole_view_is_one_to_one():
    """`View.whole` with no pixel count is exactly 1:1, not "about".

    It matters because a coverage buffer compared against `raster.fill_polygon` has to be compared on identical pixel
    centres. At 1.02 scale every edge lands half a pixel off and the whole comparison is about resampling.
    """
    view = audit.View.whole(200, 160)
    assert view.scale == 1.0
    assert view.size() == (200, 160)


def test_a_zoom_puts_the_point_it_is_centred_on_in_the_middle():
    """A zoom is a rectangle, and the geometry of that rectangle is checkable without drawing anything."""
    view = audit.View.around(120.0, 80.0, 40.0, 400)
    width, height = view.size()
    assert (width, height) == (400, 400), 'a square window should give a square image'
    middle = view.transform([(120.0, 80.0)])[0]
    assert middle == pytest.approx((width / 2.0, height / 2.0))


def test_a_zoom_shows_the_same_drawing_at_a_different_resolution():
    """The picture does not change when you zoom in; only the number of pixels it is drawn with does.

    **This is the check that the zoom is not a second code path.** A zoom that quietly resampled, or that moved the
    origin, would still produce a plausible picture -- and it would be a picture of something else, which is worse than
    no picture, because a zoom exists precisely to look closely at a disagreement.

    Measured on coverage rather than on the image so that the two renders are numbers of the same kind: pixels of ink,
    which has to scale with the square of the zoom if nothing else moved.
    """
    polygons = [audit.mark_polygon(a_stroke([(60, 50), (110, 70), (140, 90)], seed=5))]
    view = audit.View.around(100.0, 70.0, 120.0, 480)
    # **Containment is asserted, not assumed.** The first version of this test zoomed into a window the stroke ran
    # straight out of, so the zoomed picture legitimately held less ink and the test failed on a wrong premise.
    for x, y in polygons[0]:
        assert view.x <= x <= view.x + view.w and view.y <= y <= view.y + view.h, \
            'the mark leaves the window being zoomed into, so the two coverages are not comparable'
    whole = sum(audit.coverage_cairo(polygons, (200, 160), view=audit.View.whole(200, 160))) / 255.0
    zoom = sum(audit.coverage_cairo(polygons, (200, 160), view=view)) / 255.0
    assert whole > 100, 'nothing was drawn, so this test is measuring nothing'
    assert zoom == pytest.approx(whole * view.scale ** 2, rel=0.05)


def test_the_referee_compares_the_rule_the_renderer_uses():
    """The fill rule is one decision written in four modules, so it is asserted to be one value.

    `raster.fill_polygon` was even-odd and `audit`'s defaults were even-odd; the fix moved the renderer to nonzero and
    would have left the referee comparing nonzero against even-odd -- **a referee reporting a mismatch that is entirely
    its own**. Two places holding one decision is the failure this project has already had once, with `check`.

    **`render` is in this list because it was the one that actually broke.** It had no `fill_rule` parameter at all and
    hardcoded even-odd inside the drawing loop, so the numeric referee said a double-back stroke was correct while the
    picture of it was erased. Checking the three functions that *had* a parameter would have missed exactly the one
    that did not.
    """
    import inspect
    renderer = inspect.signature(raster.fill_polygon).parameters['fill_rule'].default
    assert renderer == 'nonzero'
    for fn in (audit.compare_fillers, audit.draw_polygons, audit.coverage_cairo, audit.render):
        assert inspect.signature(fn).parameters['fill_rule'].default == renderer, \
            '%s would compare or draw under a different rule than the renderer' % fn.__name__


def test_the_referee_and_the_renderer_agree_about_a_double_back():
    """The end-to-end version of the test above, on the shape that exposed it.

    Both sides have to say the same thing about the same mark: the shipping rasteriser fills the band, and the audit's
    picture paints the band. The first version of this pair disagreed, and only the picture was looked at.
    """
    mark = a_stroke([(30, 120), (250, 120), (30, 120)], seed=3)
    polygon = audit.mark_polygon(mark)
    size = (320, 220)
    ship = coverage_of([polygon], size)
    picture = sum(audit.coverage_cairo([polygon], size,
                                       view=audit.View.whole(*size))) / 255.0
    assert ship > 0.9 * picture, (
        'the renderer covers %.0f px and the audit picture %.0f -- they are not drawing the same region'
        % (ship, picture))
    # and the band is a band, not a hairline: 220 units long and ~6 wide
    assert ship > 900, 'a double-back stroke should cover most of a 220x6 band, got %.0f px' % ship


def painted_pixels(surface, background=audit.DEFAULT_PAPER) -> int:
    """How many pixels of a rendered RGB surface are not paper.

    Reads the surface rather than a coverage buffer, because the thing being checked is *the picture* -- the failure
    this catches was a drawing function that painted the wrong region while every coverage function said otherwise.
    RGB24 is stored B, G, R, X and rows are padded, so both of those are handled here and nowhere else.
    """
    surface.flush()
    data = bytes(surface.get_data())
    stride = surface.get_stride()
    painted = 0
    for y in range(surface.get_height()):
        row = y * stride
        for x in range(surface.get_width()):
            i = row + x * 4
            if (data[i + 2], data[i + 1], data[i]) != tuple(background):
                painted += 1
    return painted


def test_the_picture_holds_the_ink_the_geometries_say_it_should():
    """End to end: the picture paints the pixels the mark's own outline covers.

    **This is the test that would have caught the hardcoded fill rule**, and nothing above it would have. Every other
    check here compares two coverage buffers, and both of them were right; the drawing function was the odd one out.
    A plausible-looking picture is exactly the thing that needs an arithmetic check against something else.

    **Compared as *touched pixels*, not as area.** The first version of this test set the painted count against
    `sum(coverage)/255` and failed on correct code by 25%: that sum is the enclosed *area*, while a painted count
    includes the whole antialiased rim -- roughly a perimeter's worth of extra pixels. Two quantities that are both
    right and not the same quantity is the same mistake this project keeps finding in its thresholds.
    """
    mark = a_stroke([(30, 50), (90, 20), (150, 60), (190, 40)], seed=1)
    buffer = audit.coverage_cairo([audit.mark_polygon(mark)], (200, 160))
    touched = sum(1 for v in buffer if v > 0)
    painted = painted_pixels(audit.render([mark], audit.View.whole(200, 160)))
    assert touched > 500, 'the sample stroke covers nothing, so this test proves nothing'
    assert painted == pytest.approx(touched, rel=0.02), (
        'the picture paints %d px but the geometry touches %d' % (painted, touched))


# ------------------------------------------------------------------------------------------- referee A: the filler

def test_the_two_fillers_agree_on_a_simple_polygon():
    """cairo and the hand-written scanline filler, on a shape with an obvious answer."""
    square = [(10.0, 10.0), (90.0, 10.0), (90.0, 70.0), (10.0, 70.0)]
    assert audit.compare_fillers([square], (140, 100)).ok


def test_the_two_fillers_agree_on_a_real_stroke_outline():
    """And on a polygon the library actually produces, which is the case that counts.

    A hand-written rasteriser agreeing on a convex square proves very little. A stroke outline has dense nearly-collinear
    edges, vertices a fraction of a pixel apart, and its two spines meeting at the ends -- which is where a scanline
    filler loses a pixel or gains one. `mark_polygon` goes through `outline_polygon`, so this is the **tapered** shape,
    not a constant-width stand-in: the widths here run 1.97 to 6.31.

    **`mean` is asserted and `differing` deliberately is not.** The first version of this test asserted that fewer
    pixels differed than there were vertices, which is nonsense -- an 86-vertex outline has hundreds of pixels along its
    edges, and it failed on code that was correct. What the pair of numbers should say is: no pixel disagrees about
    *shape* (`gross`), and every disagreement is sub-pixel rounding (`mean`).
    """
    mark = a_stroke([(10, 50), (70, 20), (130, 70), (190, 40)], seed=3)
    polygon = audit.mark_polygon(mark)
    agreement = audit.compare_fillers([polygon], (210, 110))
    assert agreement.ok, 'the fillers disagree about the shape: %s' % agreement
    assert agreement.mean < 5.0, 'the fillers differ by more than rounding: %s' % agreement


def test_a_bow_tie_cannot_distinguish_the_fill_rules():
    """**A control that cannot fail, kept as a test so it is not trusted again.**

    A self-crossing quadrilateral looks like the obvious way to tell even-odd from nonzero, and it was written into
    `audit.filler_rule_difference`'s first draft as exactly that. It measures zero, and it has to: the two lobes wind
    +1 and -1, and **nonzero fills any winding that is not zero**, so both rules fill both lobes.

    The numbers are asserted rather than described because the first version of that check printed
    "0 gross px of MY error" and the zero read like a pass.
    """
    bow_tie = [(10.0, 10.0), (90.0, 70.0), (10.0, 70.0), (90.0, 10.0)]
    signed_area = sum(bow_tie[i][0] * bow_tie[(i + 1) % 4][1] - bow_tie[(i + 1) % 4][0] * bow_tie[i][1]
                      for i in range(4)) / 2.0
    assert signed_area == 0.0, 'the lobes cancel, so no rule can separate them'
    assert audit.filler_rule_difference([bow_tie], (140, 100)).gross == 0


def test_a_pentagram_is_what_distinguishes_the_fill_rules():
    """The shape that can: it winds twice in the middle, which is the only place the rules differ.

    Kept next to the bow tie so that the pair reads as one statement -- *this* is what a fill-rule control has to be,
    and the obvious candidate is not it.
    """
    star = [(100 + 80 * math.cos(math.radians(-90 + 144 * i)), 100 + 80 * math.sin(math.radians(-90 + 144 * i)))
            for i in range(5)]
    difference = audit.filler_rule_difference([star], (200, 200))
    assert difference.gross > 100, 'a pentagram must separate the rules, got %s' % difference


def test_the_fill_rule_is_reported_rather_than_assumed():
    """An unknown rule is refused instead of silently falling back to one of them.

    `raster.fill_polygon` compares the rule against a string. A typo would otherwise pick nonzero and the caller would
    never know which question had been answered -- the same shape of failure as the `check` name collision.
    """
    layer = raster.Layer(40, 40)
    with pytest.raises(ValueError):
        raster.fill_polygon(layer, [(5.0, 5.0), (35.0, 5.0), (35.0, 35.0)], (255, 255, 255), 1.0, 1.0, 'zero')


# ------------------------------------------------------------------------------------------ referee B: the offset

def test_the_offsetter_agrees_with_cairos_stroker_where_the_path_is_smooth():
    """`outline()` against cairo's stroker, at constant width, on a path that does not double back.

    **This is the only place in the project where the offset maths has been compared against anyone else's.** It is a
    real second implementation: cairo's stroker tessellates, `outline()` takes a central difference and pushes out
    perpendicular. Agreement at ordinary curvature is the finding; the next test is the boundary of it.
    """
    centre = [(float(x), float(y)) for x, y in
              stroke_record([(10, 50), (70, 20), (130, 70), (190, 40)], 'ink', seed=3)['centre']]
    report = audit.compare_stroker(centre, INK, (210, 110))
    assert report.turn < 45.0, 'this path was meant to be smooth, its sharpest turn is %.1f deg' % report.turn
    assert report.agreement.ok, 'the offset maths disagrees with cairo on a smooth path: %s' % report.agreement


def test_a_control_point_corner_is_not_a_sharp_turn():
    """Why the smooth-path test above is not dodging the hard case.

    A 90-degree corner **in the control points** is not a 90-degree turn in the path: `catmull` smooths through it and
    the sampled turn is around 25 degrees. Worth pinning because "it agrees at ordinary curvature" would be a much
    weaker claim if ordinary curvature secretly excluded every corner an artist draws -- and because it was the wrong
    assumption made twice while building this referee.
    """
    corner = [(float(x), float(y)) for x, y in
              stroke_record([(10, 10), (180, 10), (180, 100)], 'ink', seed=3)['centre']]
    assert audit.sharpest_turn(corner) < 40.0
    assert audit.compare_stroker(corner, INK, (200, 120)).agreement.ok


def test_the_offsetter_and_cairo_part_company_where_the_path_doubles_back():
    """The boundary of referee B's jurisdiction, stated as a number rather than as a caveat.

    Where the path reverses, `outline()` offsets the inside of the turn past the centreline. cairo's stroker has a
    join rule for that; `outline()` does not. **A disagreement here is the known invalid-loop problem measured, not a
    regression** -- and it is what P1 has to move, which it can only do against a number.
    """
    centre = [(float(x), float(y)) for x, y in
              stroke_record([(10, 50), (190, 50), (10, 50)], 'ink', seed=3)['centre']]
    report = audit.compare_stroker(centre, INK, (210, 110))
    assert report.turn > 120.0, 'this path was meant to double back, sharpest turn is %.1f' % report.turn
    assert report.agreement.gross > 0, 'either the geometry changed or this stopped testing anything'


# ----------------------------------------------------------- the finding: even-odd erased 91% of a hairpin stroke

def test_a_hairpin_stroke_keeps_its_area():
    """**The regression the referee found on its first real run.**

    `outline()` crosses itself at a reversal, and `raster.fill_polygon` was even-odd, so the crossed half had crossing
    number two and was erased. Measured against cairo's stroker as the reference, on a canvas of 210x110:

        before the fix     1094 -> 116 px   (9% of the stroke)
        after the fix      1094 -> 1094 px  (84% of the reference)

    The reference is a **constant** 6.5-wide stroke while the shape drawn is the tapered outline, whose widths run
    1.97 to 6.31 -- so a tapered stroke legitimately covers less, and the bar is set at half rather than at "nearly
    all". The margin is wide on purpose: this test exists to fail loudly if the rule goes back, not to pin a constant.
    """
    mark = a_hairpin()
    centre = [(float(x), float(y)) for x, y in mark['geometry']['centre']]
    polygon = audit.mark_polygon(mark)
    cairo_px = sum(audit.coverage_cairo_strokes([centre], [INK], (210, 110))) / 255.0
    ship_px = coverage_of([polygon], (210, 110))
    assert cairo_px > 1000, 'the reference stroke is missing, so this test is measuring nothing'
    assert ship_px > 0.5 * cairo_px, (
        'a hairpin stroke covers %.0f px against cairo\'s %.0f -- the fill rule has regressed' % (ship_px, cairo_px))


def test_even_odd_would_still_erase_a_hairpin():
    """The negative control for the fix.

    Without this, `test_a_hairpin_stroke_keeps_its_area` would also pass if the hairpin stopped self-crossing for some
    unrelated reason -- the test would be green and measuring nothing. Running the *same* polygon through the *same*
    rasteriser under the old rule has to reproduce the loss, or the fix was not the fix.
    """
    polygon = audit.mark_polygon(a_hairpin())
    even_odd = coverage_of([polygon], (210, 110), fill_rule='even-odd')
    nonzero = coverage_of([polygon], (210, 110), fill_rule='nonzero')
    assert even_odd < 0.2 * nonzero, (
        'the two rules no longer differ on a hairpin (%.0f vs %.0f), so the regression test above proves nothing'
        % (even_odd, nonzero))


# --------------------------------------------------------------------------------------------------- the colours

def test_every_stroke_gets_its_own_colour():
    """Mutually exclusive colours, and the property that makes them worth it: neighbours in draw order are far apart.

    Adjacent strokes are the two that can touch, so they are the pair whose colours decide whether a merge is visible.
    An even division of the hue wheel would separate the first two strokes and leave the last two nearly identical.
    """
    colours = audit.stroke_colours(24)
    assert len(set(colours)) == 24, 'two strokes share a colour, which is the one thing this must not do'
    for i in range(len(colours) - 1):
        a, b = colours[i], colours[i + 1]
        distance = math.dist(a, b)
        assert distance > 0.35, 'strokes %d and %d are %.2f apart -- too close to tell apart' % (i, i + 1, distance)


def test_the_colour_count_has_to_match_the_mark_count():
    """A mismatch is refused, because the failure mode is a drawing coloured from the wrong list.

    Padding or truncating would produce a picture where stroke 40 is painted stroke 1's colour -- plausible, wrong, and
    invisible to anything but an eye that already knew what it was looking for.
    """
    with pytest.raises(ValueError):
        audit.render(a_drawing(), audit.View.whole(200, 160), colours=audit.stroke_colours(2))


def test_a_mark_can_be_drawn_in_its_own_colour():
    """The honest render uses the mark's appearance, and a fill and a stroke read different fields."""
    stroke = a_stroke([(10, 10), (50, 10)], seed=1)
    fill = {'id': 'm0002', 'kind': 'fill', 'stage': 'colour', 'seq': 2, 'state': 'live',
            'geometry': {'points': [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]},
            'appearance': {'fill': '#FF0000'}, 'provenance': {}}
    assert audit.mark_colour(stroke) == pytest.approx((26 / 255, 22 / 255, 32 / 255))
    assert audit.mark_colour(fill) == (1.0, 0.0, 0.0)


def test_a_mark_that_is_not_live_is_not_drawn():
    """A draft is invisible, and the referee has to agree with the renderer about that or every later comparison is
    about the difference."""
    drawn = audit.drawable(a_drawing()[:1] + [a_stroke([(0, 0), (10, 10)], mark_id='m9999', seq=9, state='draft')])
    assert [m['id'] for m in drawn] == ['m0001']


# ---------------------------------------------------------------------------------- the serialiser, as far as it goes

def test_a_stroke_outline_survives_being_written_as_path_data():
    """`polygon_to_path` puts back what it was given, checked by parsing rather than by eye.

    **The gap this closes and the one it does not.** cairo is handed the *points*, never the `d` string, so the
    serialiser had nothing watching it -- the rule this project already has a name for: *a helper that is right plus a
    serialiser that ignores its argument is a contract nothing checks.* This catches dropped points, wrong order, a
    wrong command letter and a broken subpath. It does **not** catch a number format an application misreads; for that
    Illustrator is the only referee and the bridge already asks it.

    The tolerance is the writer's own precision and is asserted rather than loosened: exactly 0.005, so a change to
    fewer decimals fails here instead of in a drawing.
    """
    points = audit.mark_polygon(a_stroke([(10, 50), (70, 20), (130, 70), (190, 40)], seed=3))
    subpaths = parse_path(polygon_to_path(points))
    assert len(subpaths) == 1, 'a single closed outline became %d subpaths' % len(subpaths)
    back = subpaths[0]
    assert len(back) == len(points) + 1, 'the closing point should repeat the first'
    assert back[0] == back[-1]
    for (ax, ay), (bx, by) in zip(points, back):
        assert abs(ax - bx) <= 0.005 and abs(ay - by) <= 0.005


def test_the_outline_points_are_the_ones_the_path_data_describes():
    """`outline()` and `outline_points()` cannot drift apart, because one is the other written down.

    Split so that the referee could be given points instead of a string. That split is exactly the kind of change that
    silently leaves a second implementation behind -- `outline()` could have kept its own copy of the offset loop.
    """
    path = [(0.0, 0.0), (40.0, 10.0), (80.0, 0.0)]
    widths = [4.0, 8.0, 4.0]
    from lineweight.core import outline
    written = parse_path(outline(path, widths))[0][:-1]
    points = outline_points(path, widths)
    assert len(written) == len(points)
    for (ax, ay), (bx, by) in zip(written, points):
        assert abs(ax - bx) <= 0.005 and abs(ay - by) <= 0.005
