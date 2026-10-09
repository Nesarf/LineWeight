"""The independent referee -- 独立裁判.

Every check this project has had until now shares code with the thing it checks. The SVG bridge proves Illustrator
*accepted* a file; it never proved the geometry inside it was right, because that geometry came out of the same
functions that would have been wrong. A check with one implementation behind it is a consistency check, and this
project has already paid for that lesson: `__init__` exported `check` from two modules and the collision was silent.

This module is the second implementation. It rasterises with **cairo**, which knows nothing about `lineweight`, and it
lives outside `raster.py` on purpose. **A check that shares code with its subject is not a check.**

## What it can and cannot decide

Stated before it is used, because a referee with an unstated jurisdiction gets believed about the wrong question:

| given | decides | does not decide |
|---|---|---|
| the **same polygon points** | whether the **filler** is right -- two unrelated rasterisers agreeing about one polygon is evidence about the fillers | whether those points bound the right shape |
| a **constant-width** centreline | whether the **offsetter** is right -- cairo's stroker is a second offsetter, written by other people | the tapered case at all |
| a drawing, per-stroke colours | nothing automatic. It makes the topology legible so that an eye can disagree | nothing |

`cairo.stroke()` is itself an offsetter, so it referees the equal-width case only. That is a real limit, and it is why
`outline()`'s tapered output is still judged by `tests/test_lineweight.py::_holes` rather than here.

**And a limit that is easy to miss**: this module is handed the *points* a stroke expands to, never the `d` string.
`polygon_to_path` is therefore still unverified by anything in here -- see `TODO.md` P0b.
"""

from __future__ import annotations

import colorsys
import math
from typing import NamedTuple, Sequence

from . import curve, raster
from .roles import DEFAULT_INK
from .core import mark_ink, outline_chain_of, outline_polygon, outline_points, stroke_widths

# The same paper `raster.save_png` uses. Not a style choice: two pictures with different paper cannot be compared, and
# the comparison is the only reason either exists.
DEFAULT_PAPER = (244, 241, 233)

# A coverage difference, 0..255, small enough that two rasterisers are describing the same edge by different rounding.
AA_TOL = 8
# Above this, a pixel is called painted; below `EMPTY`, unpainted. The gap between them is the antialiased rim, and
# deliberately left unjudged -- an edge pixel is not evidence about a shape.
OPAQUE = 200
EMPTY = 24


def _cairo():
    """Imported at the point of use. **cairo is a development dependency and the library is not allowed one** -- the
    renderer that ships is `raster.py`, in pure Python, and this module is the thing that disagrees with it."""
    try:
        import cairo
    except ImportError as exc:  # pragma: no cover - depends on the machine
        raise RuntimeError('the audit path needs pycairo (`pip install pycairo`); lineweight itself does not') from exc
    return cairo


# ------------------------------------------------------------------------------------------------------------ views


class View(NamedTuple):
    """The rectangle of drawing space to show, and how many pixels to show it in.

    A rectangle rather than a scale factor, because the two pictures this module has to make are different in kind: all
    of a drawing at a size that fits, and one stroke blown up until its edges are steps. Both come out of one
    transform, so a zoom is not a second code path that could disagree with the unzoomed picture about where things
    are -- which is the failure that would matter, since a zoom exists precisely to look closely at a disagreement.
    """
    x: float
    y: float
    w: float
    h: float
    pixels: int

    @classmethod
    def whole(cls, width: int, height: int, pixels: int = 0) -> 'View':
        """All of a canvas, at 1:1 unless asked otherwise. `pixels=0` means exactly 1:1, so that a coverage buffer
        compared against `raster.fill_polygon` is compared on identical pixel centres rather than on resampled ones."""
        return cls(0.0, 0.0, float(width), float(height), int(pixels) or max(width, height))

    @classmethod
    def around(cls, cx: float, cy: float, span: float, pixels: int) -> 'View':
        """A square window of side `span` centred on a point. How one stroke gets looked at."""
        return cls(cx - span / 2.0, cy - span / 2.0, float(span), float(span), int(pixels))

    @property
    def scale(self) -> float:
        if self.w <= 0 or self.h <= 0:
            raise ValueError('a view needs a positive extent, got %rx%r' % (self.w, self.h))
        return self.pixels / max(self.w, self.h)

    def size(self) -> tuple[int, int]:
        s = self.scale
        return max(1, int(round(self.w * s))), max(1, int(round(self.h * s)))

    def transform(self, points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        """Drawing space to pixel space, written out so both rasterisers can be given the same numbers when a
        comparison has to happen somewhere other than the whole canvas."""
        s = self.scale
        return [((x - self.x) * s, (y - self.y) * s) for x, y in points]


def surface_for(view: View, background: tuple[int, int, int] = DEFAULT_PAPER, alpha: bool = False):
    """A cairo surface for a view. `alpha=True` gives FORMAT_A8, which is coverage and nothing else.

    **Coverage is a separate format on purpose.** An RGB surface would drag premultiplication and colour arithmetic
    into a comparison that is not about colour, and every extra operation in a comparison is somewhere for the
    comparison to be wrong instead of the code.
    """
    cairo = _cairo()
    width, height = view.size()
    if alpha:
        return cairo.ImageSurface(cairo.FORMAT_A8, width, height)
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
    context = cairo.Context(surface)
    context.set_source_rgb(*(c / 255.0 for c in background))
    context.paint()
    return surface


def _context(surface, view: View):
    cairo = _cairo()
    context = cairo.Context(surface)
    scale = view.scale
    context.scale(scale, scale)
    context.translate(-view.x, -view.y)
    return context


def _path(context, points: Sequence[tuple[float, float]]) -> None:
    context.move_to(points[0][0], points[0][1])
    for x, y in points[1:]:
        context.line_to(x, y)
    context.close_path()


def _shape(context, chain) -> None:
    """A closed shape given as a chain of cubics. Every closed shape goes through here, including polygons.

    Polygons are converted rather than special-cased: a cubic whose control points sit at the thirds *is* a straight
    line, so one code path draws both the fitted outline and a flat fill, and there is no second way for a shape to
    reach cairo and be drawn slightly differently.
    """
    context.move_to(chain[0][0][0], chain[0][0][1])
    for segment in chain:
        context.curve_to(segment[1][0], segment[1][1], segment[2][0], segment[2][1], segment[3][0], segment[3][1])
    context.close_path()


def as_chain(points) -> list:
    """A polygon as a closed chain of line-segments."""
    points = list(points)
    if len(points) < 3:
        return []
    return [curve.line_segment(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


def _polyline(context, points: Sequence[tuple[float, float]]) -> None:
    context.move_to(points[0][0], points[0][1])
    for x, y in points[1:]:
        context.line_to(x, y)


# ----------------------------------------------------------------------------------------------------------- drawing


def draw_polygons(surface, view: View, polygons: Sequence[Sequence[tuple[float, float]]],
                  colours: Sequence[tuple[float, float, float]], alpha: float = 1.0,
                  fill_rule: str = 'nonzero'):
    """Fills closed polygons, in the order given.

    **`fill_rule` is a parameter and it is not cosmetic.** `raster.fill_polygon` is even-odd, because that is what a
    bucket tool does and because `outline()` can hand back a polygon that touches itself; cairo's default is nonzero.
    Comparing the two without setting this produces disagreement that is entirely the caller's fault, and it would
    look exactly like a bug in the filler. Passing it explicitly puts the choice at every call site.
    """
    cairo = _cairo()
    context = _context(surface, view)
    context.set_fill_rule(cairo.FILL_RULE_EVEN_ODD if fill_rule == 'even-odd' else cairo.FILL_RULE_WINDING)
    context.set_antialias(cairo.ANTIALIAS_DEFAULT)
    for points, colour in zip(polygons, colours):
        if len(points) < 3:
            continue
        context.set_source_rgba(colour[0], colour[1], colour[2], alpha)
        _path(context, points)
        context.fill()
    return surface


def draw_shapes(surface, view: View, shapes, colours: Sequence[tuple[float, float, float]],
                alpha: float = 1.0, fill_rule: str = 'nonzero'):
    """Fills shapes given as chains of cubics -- **what actually ships**, and therefore what the pictures show.

    `raster.render_marks` draws a stroke with dabs along the centreline, so its picture is a *sampling* of the stroke
    rather than its outline. The vector exports are the outline, and `--audit` exists to show those. Drawing the
    polyline here after the outline became curves would have meant the audit showed a shape nothing ships -- which is
    bug ② of this module all over again, one representation further along.
    """
    cairo = _cairo()
    context = _context(surface, view)
    context.set_fill_rule(cairo.FILL_RULE_EVEN_ODD if fill_rule == 'even-odd' else cairo.FILL_RULE_WINDING)
    context.set_antialias(cairo.ANTIALIAS_DEFAULT)
    for chain, colour in zip(shapes, colours):
        if len(chain) < 2:
            continue
        context.set_source_rgba(colour[0], colour[1], colour[2], alpha)
        _shape(context, chain)
        context.fill()
    return surface


def draw_strokes(surface, view: View, polylines: Sequence[Sequence[tuple[float, float]]],
                 widths: Sequence[float], colours: Sequence[tuple[float, float, float]],
                 alpha: float = 1.0, line_join: str = 'miter'):
    """**cairo's own stroker, which is the whole reason this function exists**: a second offsetter, written by other
    people, for `outline()` to be compared against.

    There is no way to ask cairo for a *variable* width, so this is usable only where the width profile is constant.
    That is not a limitation of this function; it is the boundary of the referee's jurisdiction, and the reason
    `stroke_agreement` is a test of the offset maths rather than of the tapered output.
    """
    cairo = _cairo()
    context = _context(surface, view)
    context.set_antialias(cairo.ANTIALIAS_DEFAULT)
    context.set_line_join({'miter': cairo.LINE_JOIN_MITER, 'round': cairo.LINE_JOIN_ROUND,
                           'bevel': cairo.LINE_JOIN_BEVEL}[line_join])
    context.set_line_cap(cairo.LINE_CAP_BUTT)
    for points, width, colour in zip(polylines, widths, colours):
        if len(points) < 2:
            continue
        context.set_source_rgba(colour[0], colour[1], colour[2], alpha)
        context.set_line_width(width)
        _polyline(context, points)
        context.stroke()
    return surface


# ------------------------------------------------------------------------------------------------------------- marks


def drawable(marks: Sequence[dict]) -> list[dict]:
    """What a render would draw, in the order given.

    Mirrors `raster.render_marks`, which skips non-live marks. **This refuses to invent an order** for the same reason
    that one does: order is the picture, `Project.in_stage` and `Project.upto` are the only authorities on it, and a
    referee that quietly re-sequenced would be auditing a different drawing than the renderer made.
    """
    return [m for m in marks if m.get('state', 'live') == 'live']


def stroke_record_of(mark: dict) -> dict:
    """The `stroke_record`-shaped view of a mark's geometry, **so that `stroke_widths` and `outline_polygon` -- the
    product's own geometry code -- can be called on it** rather than a second copy of the width formula being written
    here. A referee that re-derived the geometry would be able to be right about it while the drawing was wrong, which
    is the one failure this module must not be capable of."""
    geometry = mark['geometry']
    return {'brush': geometry['brush'], 'centre': geometry['centre'], 'pressure': geometry['pressure']}


def mark_polygon(mark: dict) -> list[tuple[float, float]]:
    """The shape a mark covers, in drawing space."""
    kind = mark.get('kind')
    if kind == 'fill':
        points = mark['geometry'].get('points')
        if not points:
            raise ValueError('fill mark %r has no points' % (mark.get('id'),))
        return [(float(x), float(y)) for x, y in points]
    if kind == 'stroke':
        return outline_polygon(stroke_record_of(mark))
    raise ValueError('cannot audit a mark of kind %r' % (kind,))


def mark_shape(mark: dict):
    """**The shape that ships**, as a closed chain of cubics.

    A `fill` mark stores a polygon, which becomes a chain of lines; a `stroke` mark stores a record and expands
    through `core.outline_chain_of` -- the fitted curves. Both go through the code the product uses, so the picture is
    of the drawing rather than of a re-derivation that could be right while the drawing is wrong.
    """
    kind = mark.get('kind')
    if kind == 'fill':
        return as_chain(mark['geometry'].get('points') or [])
    if kind == 'stroke':
        return outline_chain_of(stroke_record_of(mark))
    raise ValueError('cannot audit a mark of kind %r' % (kind,))


def mark_centre(mark: dict) -> list[tuple[float, float]]:
    """The line the mark was aimed along, for marks that have one."""
    geometry = mark['geometry']
    points = geometry.get('centre') or geometry.get('points')
    if not points:
        raise ValueError('mark %r has no centreline' % (mark.get('id'),))
    return [(float(x), float(y)) for x, y in points]


def mark_colour(mark: dict) -> tuple[float, float, float]:
    """A mark's own colour as floats. **The mark's, not a default** -- an audit render that invented a colour would be
    a picture of a drawing that does not exist."""
    appearance = mark.get('appearance', {})
    if mark.get('kind') == 'fill':
        r, g, b = raster.parse_hex(appearance.get('fill', '#808080'))
    else:
        r, g, b = raster.parse_hex(mark_ink(mark))
    return (r / 255.0, g / 255.0, b / 255.0)


def stroke_colours(n: int, seed: float = 0.0,
                   values: Sequence[float] = (1.0, 0.62, 0.82)) -> list[tuple[float, float, float]]:
    """`n` colours that are **mutually exclusive by construction**, after Metzger 2024 (CESCG) Figure 5.

    Hue steps by the golden angle, so any two strokes *adjacent in draw order* -- which are the two that can touch --
    land far apart in hue, and the separation does not degrade as the stroke count grows the way an even division
    does. Every third stroke also drops in value, so the hue wheel coming back around does not put two similar colours
    side by side.

    **Why this deserves a function rather than a line.** Visual similarity hides structure: a stroke that has merged
    into its neighbour, or crossed itself into a pinhole, is a couple of slightly-off pixels in an honest render and
    nobody would ever see it. Painted its own colour, a pinhole becomes **a hole in a solid field** -- and a hole in a
    solid field is the one kind of defect that cannot be mistaken for antialiasing.
    """
    out = []
    for i in range(int(n)):
        hue = (seed + i * 0.38196601125010515) % 1.0
        out.append(colorsys.hsv_to_rgb(hue, 0.95, values[i % len(values)]))
    return out


def render(marks: Sequence[dict], view: View, background: tuple[int, int, int] = DEFAULT_PAPER,
           colours: Sequence[tuple[float, float, float]] | None = None, style: str = 'outline',
           alpha: float = 1.0, fill_rule: str = 'nonzero'):
    """A picture of what the marks cover, drawn by cairo instead of by `raster.py`.

    `style`:
      `'outline'`  each mark's filled shape. **The honest one** -- this is the same region `raster.render_marks` paints
      `'stroke'`   cairo's equal-width stroke along each centreline
      `'centre'`   the centreline as a hairline, which is the only way to see that a stroke went where it was aimed

    **`'stroke'` is not a rendering of the drawing and must not be read as one.** A tapered stroke has no single
    width, so the mean is used, and the result is a different drawing. It is here to be compared against `'outline'`
    at constant pressure, not to be looked at as the picture.

    `fill_rule` is a parameter here for the same reason it is one on `draw_polygons`, and it was made one the hard way:
    this function used to hardcode even-odd, so once the renderer moved to nonzero **the first per-stroke-coloured
    picture showed a double-back stroke erased**. The referee had just measured the same geometry as correct, and the
    picture was the thing that was wrong. Two checks disagreeing says one of them is broken, not which -- settling it
    took rendering that single polygon through both rules at identity scale. A hardcoded rule inside the drawing
    function was the entire cause, which is also why the contract test now checks this function too.
    """
    marks = drawable(marks)
    if colours is None:
        colours = [mark_colour(m) for m in marks]
    colours = list(colours)
    if len(colours) != len(marks):
        raise ValueError('got %d colours for %d marks' % (len(colours), len(marks)))
    if style not in ('outline', 'stroke', 'centre'):
        raise ValueError('unknown style %r' % (style,))

    cairo = _cairo()
    surface = surface_for(view, background)
    context = _context(surface, view)
    context.set_fill_rule(cairo.FILL_RULE_EVEN_ODD if fill_rule == 'even-odd' else cairo.FILL_RULE_WINDING)
    context.set_antialias(cairo.ANTIALIAS_DEFAULT)
    context.set_line_join(cairo.LINE_JOIN_ROUND)
    context.set_line_cap(cairo.LINE_CAP_ROUND)

    for mark, colour in zip(marks, colours):
        kind = mark.get('kind')
        if style == 'outline' or kind == 'fill':
            chain = mark_shape(mark)
            if len(chain) < 2:
                continue
            context.set_source_rgba(colour[0], colour[1], colour[2], alpha)
            _shape(context, chain)
            context.fill()
            continue
        centre = mark_centre(mark)
        if len(centre) < 2:
            continue
        if style == 'stroke':
            widths = stroke_widths(stroke_record_of(mark))
            context.set_line_width(sum(widths) / len(widths) if widths else 1.0)
        else:
            context.set_line_width(1.0 / view.scale)   # one pixel on screen whatever the zoom
        context.set_source_rgba(colour[0], colour[1], colour[2], 1.0)
        _polyline(context, centre)
        context.stroke()
    return surface


def save(surface, path: str) -> str:
    """Writes the picture out.

    **Byte-identical for the same input**, which is what makes "I looked at the render" a reproducible piece of
    evidence rather than an anecdote: cairo embeds no timestamp in the PNG it writes, and
    `tests/test_audit.py` asserts that across two processes rather than taking it on faith.
    """
    import os
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    surface.write_to_png(path)
    return path


# ------------------------------------------------------------------------------------------------- referee: filler


class Agreement(NamedTuple):
    """Two rasterisers put in front of the same polygons.

    **`gross`, not a mean.** An average over all pixels cannot tell one structural disagreement from ten thousand
    antialiasing ones, and this project has already been bitten by exactly that shape of error -- one coverage number
    could not separate a faded reference from line art. cairo and a hand-written scanline filler will never agree to
    the last bit along a slanted edge and should not have to, so the number that decides anything is `gross`: pixels
    where one rasteriser says *painted* and the other says *empty*. That is a statement about shape. The rest is a
    statement about rounding.
    """
    pixels: int
    differing: int      # coverage differs by more than the antialiasing tolerance
    gross: int          # one side painted, the other empty
    worst: int          # largest single-pixel coverage difference
    mean: float

    @property
    def ok(self) -> bool:
        return self.gross == 0

    def __str__(self) -> str:
        return ('%d px | %d differ | **%d gross** | worst %d | mean %.3f'
                % (self.pixels, self.differing, self.gross, self.worst, self.mean))


def compare(a: bytes, b: bytes, tol: int = AA_TOL, opaque: int = OPAQUE, empty: int = EMPTY) -> Agreement:
    """Two coverage buffers. Same length, one byte per pixel, row-major."""
    if len(a) != len(b):
        raise ValueError('coverage buffers of different sizes: %d vs %d' % (len(a), len(b)))
    differing = worst = total = gross = 0
    for x, y in zip(a, b):
        if x == y:
            continue                      # the overwhelmingly common case: both empty, or both solid
        d = x - y
        if d < 0:
            d = -d
        total += d
        if d > worst:
            worst = d
        if d > tol:
            differing += 1
        if (x >= opaque and y <= empty) or (y >= opaque and x <= empty):
            gross += 1
    return Agreement(len(a), differing, gross, worst, total / len(a) if a else 0.0)


def _a8_bytes(surface) -> bytes:
    """A surface's coverage, one byte per pixel, **without the row padding**.

    `surface.get_stride()` is not the width: cairo pads rows to a 4-byte boundary, so a 33-pixel-wide A8 surface is 36
    bytes per row. Reading it as 33 shears the image diagonally -- a defect that reads as a geometry bug and would be
    entirely mine.
    """
    surface.flush()
    data = bytes(surface.get_data())
    width, height = surface.get_width(), surface.get_height()
    stride = surface.get_stride()
    if stride == width:
        return data
    return b''.join(data[y * stride: y * stride + width] for y in range(height))


def coverage_cairo(polygons: Sequence[Sequence[tuple[float, float]]], size: tuple[int, int],
                   view: View | None = None, fill_rule: str = 'nonzero') -> bytes:
    """What cairo thinks the polygons cover."""
    return coverage_cairo_shapes([as_chain(p) for p in polygons], size, view=view, fill_rule=fill_rule)


def coverage_cairo_shapes(shapes, size: tuple[int, int], view: View | None = None,
                          fill_rule: str = 'nonzero') -> bytes:
    """What cairo thinks a set of cubic chains covers. The same machinery the filler referee uses, so the *fit* can
    be refereed by it too rather than by a second, differently-shaped comparison."""
    view = view or View.whole(*size)
    surface = surface_for(view, alpha=True)
    draw_shapes(surface, view, list(shapes), [(1.0, 1.0, 1.0)] * len(shapes), fill_rule=fill_rule)
    return _a8_bytes(surface)


def compare_fit(polygon: Sequence[tuple[float, float]], chain, size: tuple[int, int]) -> Agreement:
    """**Does the fitted curve cover the same region as the exact offset?**

    The fit has a stated tolerance and `curve.deviation` measures it as a distance, but a distance bound and a
    *coverage* bound are different statements -- a curve can stay within a hair of the polyline everywhere and still
    fill differently where the two cross it at an angle. This asks cairo the same question twice about the same
    region, exactly as `compare_fillers` does, so the answer is in the same units as every other geometry finding in
    this project.
    """
    return compare(coverage_cairo_shapes([as_chain(polygon)], size),
                   coverage_cairo_shapes([chain], size))


def coverage_cairo_strokes(polylines: Sequence[Sequence[tuple[float, float]]], widths: Sequence[float],
                           size: tuple[int, int], view: View | None = None,
                           line_join: str = 'miter') -> bytes:
    """What cairo's stroker covers."""
    view = view or View.whole(*size)
    surface = surface_for(view, alpha=True)
    draw_strokes(surface, view, list(polylines), list(widths),
                 [(1.0, 1.0, 1.0)] * len(polylines), line_join=line_join)
    return _a8_bytes(surface)


def coverage_raster(polygons: Sequence[Sequence[tuple[float, float]]], size: tuple[int, int],
                    scale: float = 1.0) -> bytes:
    """What `raster.fill_polygon` covers, in the same encoding.

    All polygons go into **one** layer, in order, and so do cairo's, so that overlaps composite the same way on both
    sides. Comparing them one at a time would miss any disagreement that only appears where shapes meet -- which is
    where this project's geometry actually fails.
    """
    width, height = size
    layer = raster.Layer(width, height)
    for points in polygons:
        if len(points) < 3:
            continue
        raster.fill_polygon(layer, points, (255, 255, 255), 1.0, scale)
    return bytes(layer.data[3::4])


def compare_fillers(polygons: Sequence[Sequence[tuple[float, float]]], size: tuple[int, int],
                    fill_rule: str = 'nonzero') -> Agreement:
    """**Referee A. Is the filler right?**

    `raster.fill_polygon` is a hand-written scanline rasteriser; cairo's is analytic coverage. Given identical points
    and an identical fill rule they are answering the same question with no shared code, so agreement here is evidence
    and disagreement is a finding. **It says nothing about whether the points are the right outline** -- that is
    `outline()`'s job, and `compare_stroker` is the referee entitled to an opinion about it.
    """
    return compare(coverage_raster(polygons, size), coverage_cairo(polygons, size, fill_rule=fill_rule))


# ------------------------------------------------------------------------------------------------- referee: offset


def sharpest_turn(points: Sequence[tuple[float, float]]) -> float:
    """The largest direction change along a polyline, in degrees.

    **The number that decides whether referee B is entitled to an opinion.** cairo mitres a corner; `outline()` takes a
    central difference across it and pushes both sides out along that one direction. Those two agree while the turn is
    gentle and cannot agree at a sharp one, so a stroke disagreement read without this number is a number with no
    meaning -- the same confounding this project already caught once in `taper_ratio`, where a ratio moved for the
    wrong reason and looked like a result.
    """
    worst = 0.0
    for i in range(1, len(points) - 1):
        ax, ay = points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]
        bx, by = points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la == 0 or lb == 0:
            continue
        cos = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
        worst = max(worst, math.degrees(math.acos(cos)))
    return worst


class OffsetReport(NamedTuple):
    """Referee B's answer, with the number that says whether to believe it."""
    width: float
    turn: float                 # sharpest direction change along the centreline, degrees
    agreement: Agreement


def compare_stroker(centre: Sequence[tuple[float, float]], width: float, size: tuple[int, int],
                    line_join: str = 'round') -> OffsetReport:
    """**Referee B. Is the offsetter right?**

    `outline()` and cairo's stroker both turn "a path plus a width" into a filled region, and they were written by
    people who never saw each other's code. At constant width the two are directly comparable, which is the only place
    in this project where the offset maths has been compared against anything at all.

    Read it with `turn`: agreement is expected while the path is smooth, and **disagreement at a sharp corner is the
    known invalid-loop problem, measured rather than described**. That number is what P1 has to move.

    **`line_join='round'` is not the flattering choice, it is the same pen.** `raster.stroke_layer` draws a stroke as
    radial dabs, which is a round nib by construction, so the vector outline is a vectorisation of a round-nibbed
    stroke and a round join is what it has to be compared against. Cairo defaults to a miter and that is a *different
    pen*: at the 161-degree reversal of a hairpin a miter has a ratio of 6.11, i.e. a spike 16.6 units long, which is
    not a shape an artist drew. All three are reported by the numbers below rather than asserted, because a referee
    whose settings were chosen to make its subject agree would be worth nothing -- on the same hairpin the shipped
    outline measures **0 gross against round, 28 against miter and 7 against bevel**, and on every gentler shape all
    three are 0 because a join only matters where the turn is sharp.
    """
    points = [(float(x), float(y)) for x, y in centre]
    polygon = outline_points(points, [width] * len(points))
    return OffsetReport(width, sharpest_turn(points),
                        compare(coverage_raster([polygon], size),
                                coverage_cairo_strokes([points], [width], size, line_join=line_join)))


def filler_rule_difference(polygons: Sequence[Sequence[tuple[float, float]]], size: tuple[int, int]) -> Agreement:
    """Even-odd against nonzero, on the same polygons and by the same rasteriser.

    **A control, not a check.** It answers "how much of this shape is self-overlap" -- and it is here so that the day
    referee A reports gross disagreement, the first question (is the fill rule the caller meant?) has an answer
    already measured rather than argued about. On a simple polygon this is zero, and on a tight curve it is the
    invalid-loop area.
    """
    return compare(coverage_cairo(polygons, size, fill_rule='even-odd'),
                   coverage_cairo(polygons, size, fill_rule='nonzero'))
