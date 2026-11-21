"""A layered raster compositor: dabs into alpha buffers, blended into a picture.

    # inside lineweight, or beside it
    from raster import Layer, stroke_layer, composite, save_png

**Why this exists when the SVG output was the point.** Vector output is resolution-independent, diffable and small,
and it cannot blend. A pencil line over a wash is not a black stroke with an opacity: the two marks meet and mix,
and the mixing is what makes a drawing look like a drawing rather than a diagram with colour in it. That is the whole
of the B tier -- strokes as dabs into per-layer buffers, layers combined by blend mode, and clipping as one alpha
multiply -- and the primitives are small enough that this file is arithmetic rather than an engine.

Deliberately pure Python. numpy would make this ten times faster and would put a dependency on the critical path of a
library whose selling point is that it draws with the standard library; a drawing is a few million pixels, which is
slow but not absurd, and the honest thing is to measure it before optimising it.

Coordinates are pixel centres, colours are 0-255 triples, and alpha is 0-1 throughout, because mixing bytes with
floats is where this kind of code goes wrong.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

#: **numpy is optional and the difference is two orders of magnitude.** The density path keeps one float per pixel of
#: the page and sums a falloff into it; as a Python list that is 3.7 million boxed floats and a loop over every one of
#: them per stroke, which measured 0.7 seconds for a single hairline on a 960 page. As an array the same work is a few
#: milliseconds. Without numpy the code below still runs, only slowly, so the library keeps working on a bare install.
try:
    import numpy as _np
except ImportError:  # pragma: no cover - exercised only on a machine without numpy
    _np = None

from .core import BRUSHES, BRUSH_REFERENCE_LONG, brush_at, mark_ink, stroke_widths
from .roles import DEFAULT_INK


def grain_at(x: float, y: float, seed: int = 0) -> float:
    """A deterministic value in 0..1 for a point on the paper, stable across strokes.

    **Sampled by position rather than by dab index, because grain belongs to the paper.** A texture indexed by how
    many dabs have been stamped makes the speckle travel with the brush, which reads as a moving pattern rather than
    as a rough surface; sampling the canvas means two strokes crossing the same spot share the same tooth, which is
    what a rough sheet actually does.

    A cheap hash rather than a noise library: three multiplies and a sine in each axis is enough to break up a line at
    the scale of a pixel, and the point of this file is that it draws with the standard library.
    """
    a = math.sin((x * 12.9898 + y * 78.233 + seed * 37.719)) * 43758.5453
    b = math.sin((x * 39.3468 + y * 11.1351 + seed * 13.117)) * 24634.6345
    return (a - math.floor(a)) * 0.6 + (b - math.floor(b)) * 0.4


@dataclass
class Paper:
    """The surface. **A property of the sheet, not of the brush.**

    `grain` on a brush says how much a *medium* shows the tooth; this says what the tooth *is*. Without it, "pencil on
    smooth cartridge" and "pencil on rough watercolour paper" are the same drawing -- which is the gap the per-stroke
    specification names as media simulation, and the reason a texture amplitude living only on the brush is not the
    same thing as a surface.

    **The default is the identity, deliberately.** `tooth` 1, `scale` 1, `direction` 0 reproduces the existing sampling
    exactly, so every layer that does not name a paper -- which is every layer written before this existed -- renders
    byte for byte as it did.

    **The four presets are not measurements.** They are round numbers that produce visibly different surfaces, and
    which one is right for a given medium has not been measured here. They are labelled that way in `PAPERS` rather
    than presented as calibrated, because a number that merely looked reasonable is the failure this repository has
    recorded more than once.
    """
    name: str = 'default'
    tooth: float = 1.0          # amplitude multiplier on whatever grain the brush declares
    scale: float = 1.0          # the size of the surface's bumps in pixels; larger is a coarser sheet
    direction: float = 0.0      # 0 isotropic; above 0 stretches the tooth sideways, as a woven or laid sheet does
    bite: float = 0.0           # how much this surface marks even a medium that declares no grain of its own

    def at(self, x: float, y: float, seed: int) -> float:
        """The tooth at a point on the sheet, in 0..1.

        **The identity is special-cased rather than expressed as scale 1**, because dividing by a scale of 1.0 and
        multiplying by a direction of 0.0 would go through the same arithmetic and could differ in the last bit. A
        default that is *nearly* the old behaviour is worse than one that is exactly it.
        """
        if self.scale == 1.0 and self.direction == 0.0:
            return grain_at(x, y, seed)
        return grain_at(x / self.scale, y / (self.scale * (1.0 + self.direction * 4.0)), seed)


# Unmeasured starting points -- see `Paper`. `default` is the identity and every other one is a surface that is
# visibly not it.
PAPERS: dict[str, Paper] = {
    'default': Paper('default'),
    'smooth': Paper('smooth', tooth=0.35, scale=1.0, direction=0.0, bite=0.0),
    'drawing': Paper('drawing', tooth=1.0, scale=1.6, direction=0.0, bite=0.08),
    'rough': Paper('rough', tooth=1.7, scale=3.2, direction=0.0, bite=0.26),
    'canvas': Paper('canvas', tooth=1.5, scale=2.6, direction=0.9, bite=0.20),
    # `bite` is why this field exists at all. The first version had only `tooth`, as a multiplier on the brush's own
    # grain -- and the `ink` brush declares `grain: 0`, so **four different surfaces rendered byte-identically** and
    # the feature was inert for the medium this library mostly draws in. `dab` now takes `max(brush * tooth, bite)`:
    # a rough sheet makes even a loaded pen stutter, which is what the field was supposed to be able to say.
    # These values are round numbers that produce visibly different surfaces, not measurements.
}


def bleed_radius(level: float, paper: 'Paper | None' = None, reach: float = 26.0) -> float:
    """湿边的半径：**由纸的粗糙度与墨的浓度决定，不是手调常数。**

    纸越粗，毛细作用越强，墨走得越远（`tooth` 是纸的粗糙度：`rough` 一点七、`smooth` 零点三五）；而墨越浓走得
    越**近** —— 浓墨里水少，颜料自己就留住了。两条力方向相反，而画面上看到的是**淡墨渗得最远**：那是水多颜料少的
    那一笔，水往纸里走，把淡墨带到笔没到过的地方。

    所以同一个浓度换一张更粗的纸会渗得更开，同一张纸上浓墨几乎不渗 —— 而这两句都不是调出来的，它们分别是
    `tooth` 与 `level` 的函数。**一个人想改这个半径，该改纸或改浓度，而不是改这里。**
    """
    tooth = 1.0 if paper is None else float(paper.tooth)
    level = min(1.0, max(0.0, float(level)))
    return reach * tooth * (1.0 - level) ** 1.5


class Layer:
    """One RGBA buffer. Straight alpha: the colour of a pixel is the colour it actually is."""

    def __init__(self, width: int, height: int, seed: int = 0, paper: 'Paper | None' = None) -> None:
        self.width = width
        self.height = height
        self.seed = seed
        # **The surface belongs to the buffer because a buffer is a surface.** Every caller that makes a layer can
        # name the sheet it is painting on, and `dab` reads it without any signature changing -- which matters
        # because `dab` is the hot loop and the one place a paper has to reach.
        self.paper = paper or PAPERS['default']
        # **A float buffer, used only by the density path.** `dab` writes 8-bit RGBA and summing into 8 bits loses
        # the precision the integral needs -- a hundred dabs each contributing a thousandth would quantise to
        # nothing. It stays None on every other path, so nothing else pays for it.
        self.density: list[float] | None = None
        self.density_ref: list[float] | None = None
        self.density_colour: tuple[int, int, int] | None = None
        # premultiplied would be faster to blend and harder to reason about; this keeps the colour meaningful when
        # alpha is low, which matters as soon as anybody looks at an intermediate buffer
        self.data = bytearray(width * height * 4)
        # **颜料有厚度，而一个装不下厚度的缓冲区只能装颜色。** `relief` 是一层浮点高度，每个像素一个数；
        # `None` 表示这张面是平的 —— 这个文件里此前的每一层都是平的，所以不要求厚度的画法行为完全不变。
        self.relief = None

    def dab(self, x: float, y: float, radius: float, colour: tuple[int, int, int], alpha: float,
            grain: float = 0.0, accumulate: bool = True) -> None:
        """One stamp: a radial falloff, which is what a brush tip is at this level of description.

        **`accumulate` decides whether this dab deepens what is already here.** True is source-over -- two *strokes*
        over each other do darken each other, and that is right. False takes the maximum instead, which is what the
        dabs *of one stroke* have to do.

        **The dabs of one stroke are one deposit sampled many times, not many deposits.** With source-over they
        accumulate, and that makes **spacing a darkness parameter**: the same record measured here at spacing 0.28
        reads a mean alpha of 0.7166 and at 1.10 reads 0.4545, a 37% swing on the ink brush and 59% on the wash --
        while the brush table's spacing was measured by *counting runs of ink*, a criterion about continuity and not
        about darkness. Two properties that should be independent were one knob.
        """
        if radius <= 0 or alpha <= 0:
            return
        x0, x1 = max(0, int(x - radius)), min(self.width - 1, int(x + radius) + 1)
        y0, y1 = max(0, int(y - radius)), min(self.height - 1, int(y + radius) + 1)
        r, g, b = colour
        for py in range(y0, y1 + 1):
            dy = py - y
            row = py * self.width * 4
            for px in range(x0, x1 + 1):
                dx = px - x
                distance = math.hypot(dx, dy)
                if distance > radius:
                    continue
                # a soft edge: full strength in the core, falling to nothing at the rim
                falloff = 1.0 - (distance / radius) ** 2
                a = alpha * falloff
                # **The guard is on the surface, not on the brush.** It used to be `if grain > 0`, which meant a
                # medium declaring no grain of its own was immune to the paper -- and since `ink` declares exactly
                # that, four different surfaces rendered byte-identically. A rough sheet makes even a loaded pen
                # stutter, so the amplitude is `max(brush * tooth, bite)` and an ink line on rough paper is no longer
                # the same picture as the same line on smooth.
                bite = grain * self.paper.tooth
                if self.paper.bite > bite:
                    bite = self.paper.bite
                if bite > 0:
                    # the tooth of the paper, sampled where the dab lands rather than by dab count
                    # **The absolute pixel, not an offset within this dab's own bounding box.** The first version
                    # sampled relative to x0/y0, which are the corners of the dab being stamped -- so the tooth was
                    # local to each dab and travelled with the brush, which is precisely what sampling by position
                    # was supposed to prevent. The property test caught it: the same line drawn in the opposite
                    # direction had its speckle in different places.
                    a *= 1.0 - bite * (1.0 - self.paper.at(px, py, self.seed))
                index = row + px * 4
                old_a = self.data[index + 3] / 255.0
                if not accumulate:
                    # The stroke's deposit is the deepest dab that covers this pixel. The colour is that dab's own,
                    # unpremultiplied by its own alpha, which is the same convention the source-over branch keeps.
                    if a <= old_a:
                        continue
                    self.data[index] = r
                    self.data[index + 1] = g
                    self.data[index + 2] = b
                    self.data[index + 3] = int(a * 255)
                    continue
                new_a = a + old_a * (1 - a)
                if new_a <= 0:
                    continue
                self.data[index] = int((r * a + self.data[index] * old_a * (1 - a)) / new_a)
                self.data[index + 1] = int((g * a + self.data[index + 1] * old_a * (1 - a)) / new_a)
                self.data[index + 2] = int((b * a + self.data[index + 2] * old_a * (1 - a)) / new_a)
                self.data[index + 3] = int(new_a * 255)


    def wet_dab(self, x: float, y: float, radius: float, colour: tuple[int, int, int], alpha: float,
                pickup: float, under: Layer | None = None, grain: float = 0.0,
                accumulate: bool = True) -> None:
        """A dab that first picks up what is already on the layer, then lays down the result.

        **This is the essence of wet mixing, and it is a lerp rather than a physics simulation.** A loaded brush
        crossing a wet wash carries some of that wash with it; the colour it deposits is part way between the paint it
        holds and the paint it found. Sampling the footprint's average and mixing by `pickup` reproduces the thing
        that makes watercolour read as watercolour -- the trail of colour a brush drags out of a shape it passes over
        -- without any of the neighbourhood iteration the tier was expected to need.

        Zero pickup is the dry dab exactly, so one code path covers both.
        """
        if pickup <= 0:
            self.dab(x, y, radius, colour, alpha, grain, accumulate=accumulate)
            return
        x0, x1 = max(0, int(x - radius)), min(self.width - 1, int(x + radius) + 1)
        y0, y1 = max(0, int(y - radius)), min(self.height - 1, int(y + radius) + 1)
        # **Sample the layer underneath, not this one.** The first version averaged this buffer's own footprint,
        # which includes the dabs the stroke laid down a moment ago -- so a red brush crossing a blue wash picked up
        # its own red and stayed red, and the measurement showed a difference of one unit out of 255. A brush carries
        # the paint it is passing over, not the paint it has just put down.
        source = under if under is not None else self
        total = [0.0, 0.0, 0.0]
        weight = 0.0
        for py in range(y0, y1 + 1):
            row = py * source.width * 4
            for px in range(x0, x1 + 1):
                if math.hypot(px - x, py - y) > radius:
                    continue
                index = row + px * 4
                a = source.data[index + 3] / 255.0
                for channel in range(3):
                    total[channel] += source.data[index + channel] * a
                weight += a
        mixed = colour
        if weight > 0:
            found = tuple(c / weight for c in total)
            mixed = tuple(int(colour[c] + (found[c] - colour[c]) * pickup) for c in range(3))
        self.dab(x, y, radius, mixed, alpha, grain, accumulate=accumulate)


def _density_to_alpha(numerator, denominator, cap):
    """The coverage at a pixel: **the alpha of the dabs covering it, weighted by how much each covers it.**

    Both buffers are the same sum -- of the tip's falloff along the path, times the distance each dab stands for,
    over the tip's diameter -- and they differ only in that one is weighted by the dab's alpha and the other is not.
    So the ratio is an average of alpha, and **for a straight stroke of constant alpha it is exactly that alpha, with
    no constant anywhere in the arithmetic.**

    **That is what the first version got wrong, and the measurement is what said so.** It scaled a single accumulated
    density by `-ln(1 - cap) / (2/3)`, taking `2/3` for the integral through a tip of the *nominal* radius. Measured,
    the sum comes to `0.81` to `0.97` of that integral depending on the brush, because the dabs are discrete and a
    coarse Riemann sum of a concave falloff is not its integral -- so the map was wrong by a factor that varied per
    brush, and switching to it made the pencil five times fainter while the opaque ink came out right.

    **A ratio of two sums cannot have that fault**, because whatever the sampling does to one it does to the other.
    The alternative -- clamping a raw sum -- would darken a stroke wherever its own path curves back, which is the
    fault this replaces rather than a fix for it.
    """
    if denominator <= 0 or cap <= 0:
        return 0.0
    return min(cap, numerator / denominator)


def stroke_layer(record: dict, width: int, height: int, scale: float = 1.0,
                 wet: float = 0.0, under: Layer | None = None, paper: Paper | None = None,
                 density: bool = False, width_scale: float = 1.0,
                 absolute_width: bool = False) -> Layer:
    """... **`density` replaces the maximum, and it is justified by measurement -- use it for a wide stroke.**

    Taking the maximum of the dabs makes a stroke's darkness independent of the brush's spacing, which is why it is
    there. **What it also does is bead**: two soft dabs a spacing apart leave the midpoint at
    `1 - (spacing/2r)^2` of full coverage, so a stroke drawn with a 17-pixel tip has a ripple of about 37 percent
    along its length. At a four-pixel brush that is sub-pixel and invisible, which is why it went unnoticed -- and it
    is what turned the first drawing with mass into a string of beads.

    Measured along a straight stroke of the ink brush, ripple as peak-to-peak over the mean through the middle half:

        width  4 px   maximum 0.883     width 40 px   maximum 0.372     density 0.004
        width  6 px   maximum 0.495     width 80 px   maximum 0.371     density 0.004

    **A ninetyfold reduction, and the wider the brush the more it matters** -- which is the opposite of the maximum's
    behaviour, where the ripple is roughly constant because the spacing scales with the radius.

    The sum is of the tip's own falloff **weighted by the distance each dab stands for**, without which it is not an
    integral but a count of dabs and the wash brush comes out thirteen times too faint. That much was established
    earlier and stands. What did not stand was the earlier claim that this path fixes a crease where two feathered
    edges meet: **there is no such crease here**, and that measurement was of dab discretisation on a hairpin. The
    justification is this one, not that one.

    `density=True` still changes what is drawn, so it is not the default and callers choose it -- the drawing uses it
    for bone width, where a limb is thirty to eighty pixels across and the maximum beads visibly.
    """
    """Rasterises a stroke record: dabs along the centre line, spaced by the brush, sized by the pressure.

    **This is the same data the vector expander uses**, which is the point of keeping a record rather than an
    outline: one stroke goes to SVG or to a buffer without being redrawn, and the two outputs cannot disagree about
    what was drawn.
    """
    brush = brush_at(record['brush'], record.get('size', 1.0))
    colour = record.get('colour_int') or (26, 22, 32)
    layer = Layer(width, height, paper=paper)
    if density:
        if _np is not None:
            layer.density = _np.zeros(width * height, dtype=_np.float32)
            layer.density_ref = _np.zeros(width * height, dtype=_np.float32)
        else:
            layer.density = [0.0] * (width * height)
            # **The same sum without the alpha**, so the ratio is an average rather than a magnitude that depends on how
            # finely the path happened to be sampled.
            layer.density_ref = [0.0] * (width * height)
        layer.density_colour = colour
    # **A brush's width is fixed on a page, and the page is the record's to state.** The canvas does not overrule it --
    # a thumbnail or a crop fills a canvas smaller than the drawing -- so a record without a page is read against the
    # one the table itself was drawn on, which is the behaviour every record written before the field existed had. Only
    # the brush table is affected; a supplied profile is already in the units a picture was measured in.
    page_factor = float(record.get('page_long') or BRUSH_REFERENCE_LONG) / BRUSH_REFERENCE_LONG
    gamma = float(brush.get('curve', 1.0))
    centre = record['centre']
    pressure = record['pressure']
    # **The stroke's own median pressure, taken once.** A profile is an absolute width curve and the pressure is a
    # relative one, so dividing by this keeps a caller's width curve meaning what it says while letting the hand's own
    # variation through. A median of zero would mean a stroke with no pressure at all; the fallback keeps the
    # division finite rather than inventing a numerator.
    median_pressure = sorted(pressure)[len(pressure) // 2] if pressure else 1.0
    if median_pressure <= 0:
        median_pressure = 1.0
    # **The profiles are resampled onto the path, not indexed by segment number.** `centre` has been resampled and the
    # profiles have not; reading them by segment number truncated every curve to its first few segments. See
    # `_resample_profile` for the measurement and against what.
    widths = _resample_profile(record.get('width_profile') or [], len(centre))
    alphas = _resample_profile(record.get('alpha_profile') or [], len(centre))
    # **Spacing is measured against the radius, not against the width times a factor.** The first version
    # multiplied the brush width by its spacing factor, which for a 22-pixel wash with a factor of 1.4 drew a
    # dab every 15 pixels -- a string of separate beads. A brush's spacing is how far apart its dabs sit
    # *relative to how big they are*: a tenth of the diameter is smooth, half the diameter is a texture.
    #
    # **And it has to be recomputed per dab once the pressure varies.** It used to be resolved once from the brush's
    # nominal width, which was harmless while every stroke was the same width and became wrong the moment the pressure
    # model started reaching the picture: a contour asked for one and a half pixels narrows its radius below that, the
    # spacing stayed at one pixel, and **the dots stopped touching -- the outline came out as a dotted line.** So the
    # spacing factor is kept here and the distance is derived from the radius each dab is about to be stamped at.
    spacing_factor = brush.get('spacing', 0.7)
    carry = 0.0
    for i in range(1, len(centre)):
        x0, y0 = centre[i - 1]
        x1, y1 = centre[i]
        segment = math.hypot(x1 - x0, y1 - y0)
        if segment <= 0:
            continue
        travelled = carry
        while travelled <= segment:
            t = travelled / segment
            x = (x0 + (x1 - x0) * t) * scale
            y = (y0 + (y1 - y0) * t) * scale
            p = pressure[min(i, len(pressure) - 1)]
            # **The record's own profiles when it has them, the brush's derivation when it does not.** A field the
            # renderer ignores is a comment, and both of these exist to be the place a *measured* profile lands --
            # `ref.py` measures width and darkness distributions out of real artwork, and the brush table is
            # per-brush, so it cannot hold a per-stroke measurement.
            #
            # **But a profile must not silence the hand.** This branch used to take the profile and drop `pressure`
            # entirely, and since every caller in this project supplies a profile, `pressures` -- noise, speed near a
            # fast run, the thinning at a corner -- **never reached the picture at all.** That is why a stroke came out
            # with the same width along ninety-eight per cent of its length: not because the brush asked for it, but
            # because the branch meant to use the brush's dynamics was never taken.
            #
            # So the profile gives the width and the pressure gives the **relative** pressure, divided by the stroke's
            # own median. Multiplying keeps the profile's absolute scale, which is what a caller writing a width curve
            # means, and restores the variation that a hand has and a curve cannot.
            if widths and absolute_width:
                # **The profile is the width and the hand model stays out of it.** A traced stroke's widths are
                # measurements of a line that already exists; scaling them by a pressure would be drawing it again
                # rather than copying it, and a taper the reference does not have would appear at every end.
                base = float(widths[min(i, len(widths) - 1)])
                radius = max(0.5, base * scale * 0.5 * width_scale)
            elif widths:
                base = float(widths[min(i, len(widths) - 1)])
                radius = max(0.5, base * (p / median_pressure) * scale * 0.5 * width_scale)
            else:
                radius = max(0.5, brush['width'] * page_factor * (p ** gamma) * scale * 0.5 * width_scale)
            # **The step is a fraction of the radius this dab will actually be stamped at.** A floor of half a pixel
            # keeps a hairline from spending its whole budget on steps, and the factor comes from the brush because
            # that is where a texture would be chosen.
            spacing = max(0.5, radius * 2.0 * spacing_factor * 0.5)
            if alphas:
                # The profile is the stroke's opacity along its length; the brush's own opacity is the medium and
                # still applies, exactly as it does on the vector side.
                alpha = min(1.0, brush['opacity'] * float(alphas[min(i, len(alphas) - 1)]))
            else:
                alpha = min(1.0, brush['opacity'] * (p ** gamma))
            # **The distance this dab stands for, needed before it is deposited.** It was computed after the
            # deposit, which the maximum path never noticed because it does not use it -- and the density path
            # failed with `cannot access local variable 'dab_step'` on its first run.
            # **The density path deposits far more finely than the maximum path, and it has to.**
            # `min(cap, num/den)` saturates wherever any dab covers, so the stroke's silhouette is **the union of the
            # dab discs** -- and the boundary of a union of overlapping circles is scalloped. That is invisible along
            # the centreline, which is why it survived so many one-dimensional measurements: measuring the alpha
            # along the stroke says nothing about the shape of its edge. Seen in two dimensions it is unmistakable,
            # and it is the beads.
            #
            # **2.5 percent of the diameter is Compositor's published figure for soft tips**, against this library's
            # 56 -- twenty times finer. Measured here: the direction reversals along the left edge of a bone go
            # 2 -> 1 -> 0 as the spacing goes x1 -> /4 -> /16, and the picture agrees.
            step_factor = DENSITY_STEP if density else brush.get('spacing', 0.7)
            dab_step = max(1.0, radius * 2 * step_factor) * scale
            # **One stroke, one deposit**: the dabs take the maximum rather than compositing over each other, so
            # where the brush's spacing puts them closer together the stroke does not get darker. Strokes still
            # darken strokes, because that happens in the caller when this buffer is composited.
            if density:
                # **Summed, not maximised -- and the sum is of the tip's own falloff, so it is the integral of
                # deposition along the path rather than a count of dabs.** Spacing changes how finely that integral
                # is sampled, not what it comes to.
                _deposit(layer, x, y, radius, alpha, dab_step)
            else:
                layer.wet_dab(x, y, radius, colour, alpha, wet, under,
                              accumulate=False)
            travelled += dab_step
        carry = travelled - segment
    if density:
        _resolve_density(layer, width, height, brush)
    # **The paper bites the finished deposit, once, by position.** Applying it per dab and then taking the maximum
    # lets the *lightest* grain among the overlapping dabs win, so the texture flattens as spacing tightens -- the
    # rough-versus-smooth ratio fell from above 1.5 to 1.48 when the maximum was introduced. That is the same fault
    # the maximum was introduced to fix, one layer down: **the deposit must not depend on how many dabs cover a
    # pixel, and neither must the surface it sits on.**
    bite = max(brush.get('grain', 0.0) * layer.paper.tooth, layer.paper.bite)
    if bite > 0:
        data = layer.data
        for py in range(height):
            row = py * width * 4
            for px in range(width):
                index = row + px * 4
                a = data[index + 3]
                if not a:
                    continue
                data[index + 3] = int(a * (1.0 - bite * (1.0 - layer.paper.at(px, py, layer.seed))))
    return layer


def _deposit(layer, x: float, y: float, radius: float, alpha: float, step: float) -> None:
    """One dab's falloff added into the density buffer -- **the tip's shape, not its result.**

    **`step` is what makes the sum an integral.** A sum over dabs approximates the path integral of the falloff only when each term
    is weighted by the distance it stands for, and dabs along a path are spaced -- `max(1, 2 r spacing)` apart. Without
    the weight the total depends on the spacing, which is the fault `accumulate=False` was introduced to remove, one
    layer down; with it the sum is the path integral however finely the path was sampled.

    Measured before the weight was added: the wash brush, whose radius is about a third of nominal at the measured
    pressure, came out at a peak alpha of 0.020 against 0.263 for the maximum -- **faint by a factor of thirteen**,
    and the factor is exactly the ratio of the step to the diameter that the missing weight accounts for.
    """
    if radius <= 0 or alpha <= 0:
        return
    x0, x1 = max(0, int(x - radius)), min(layer.width - 1, int(x + radius) + 1)
    y0, y1 = max(0, int(y - radius)), min(layer.height - 1, int(y + radius) + 1)
    buf = layer.density
    for py in range(y0, y1 + 1):
        dy = py - y
        row = py * layer.width
        for px in range(x0, x1 + 1):
            dx = px - x
            distance = math.hypot(dx, dy)
            if distance > radius:
                continue
            # **Normalised here, by this dab's own radius.** Doing it at the end divides by the brush's nominal
            # radius while the dabs were stamped at `nominal * pressure ** curve` -- which for the wash brush at the
            # measured pressure is about a third of it, so the stroke came out 5.5x too faint and the coverage fell
            # from 2509 pixels to 657. The integral is of deposition per unit length, so the length scale is the one
            # the deposition actually happened at.
            weight = (1.0 - (distance / radius) ** 2) * step / (2.0 * radius)
            buf[row + px] += alpha * weight
            layer.density_ref[row + px] += weight


def _resolve_density(layer, width: int, height: int, brush) -> None:
    """Density to coverage, once, at the end -- and the colour laid down with it."""
    cap = min(1.0, brush.get('opacity', 1.0))
    colour = layer.density_colour or (26, 22, 32)
    if _np is not None:
        # **The whole page at once, because the per-pixel form below walked 3.7 million indices per stroke.** That loop
        # is the other half of the 0.7 seconds a hairline cost: the sum is spent whether a pixel is covered or not.
        buf = layer.density
        ref = layer.density_ref
        active = _np.flatnonzero(buf > 0.0)
        if not len(active):
            return
        denom = ref[active]
        keep = denom > 0.0
        active = active[keep]
        denom = denom[keep]
        if not len(active):
            return
        alpha = _np.minimum(cap, buf[active] / denom)
        keep = alpha > 0.0
        active = active[keep]
        alpha = alpha[keep]
        if not len(active):
            return
        data = _np.frombuffer(layer.data, dtype=_np.uint8)
        idx = active * 4
        data[idx] = colour[0]
        data[idx + 1] = colour[1]
        data[idx + 2] = colour[2]
        data[idx + 3] = _np.clip(alpha * 255.0, 0, 255).astype(_np.uint8)
        return
    buf = layer.density
    ref = layer.density_ref
    data = layer.data
    for i in range(width * height):
        if buf[i] <= 0:
            continue
        a = _density_to_alpha(buf[i], ref[i], cap)
        if a <= 0:
            continue
        j = i * 4
        data[j] = colour[0]
        data[j + 1] = colour[1]
        data[j + 2] = colour[2]
        data[j + 3] = int(a * 255)
    layer.density = None
    layer.density_ref = None


def blend_at(base: Layer, top: Layer, x0: int, y0: int, mode: str = 'normal') -> Layer:
    """Blends `top` into `base` with `top`'s top-left corner at (x0, y0), and returns the base.

    **The offset form exists because a mark does not need the page.** `stroke_layer` allocates a layer the size of the
    whole page and draws a stroke a few hundred pixels long into it; at four thousand strokes that is thirty gigabytes
    of allocation for a picture whose ink covers a twentieth of the page. Drawing into a box the size of the mark and
    blending it at an offset is the same arithmetic over a smaller rectangle -- and the same rule, so a mark rendered
    this way and a mark rendered the old way agree pixel for pixel.

    **`erase` is destination-out, and it is the one mode that takes ink away.** The alpha becomes `base * (1 - top)`
    and the colour is left as the base had it, because a pixel that has been erased to nothing has no colour to state.
    It exists for the eraser mark, which is the only mark in this library that a drawing can only lose ink to -- a line
    can be added anywhere, and every copying error the project has measured is a line in the wrong place rather than a
    line missing one.
    """
    if _np is None:
        raise RuntimeError('blend_at needs numpy')
    h, w = base.height, base.width
    th, tw = top.height, top.width
    x1 = min(w, x0 + tw)
    y1 = min(h, y0 + th)
    x0c = max(0, x0)
    y0c = max(0, y0)
    if x1 <= x0c or y1 <= y0c:
        return base
    b = _np.frombuffer(base.data, dtype=_np.uint8).reshape(h, w, 4)
    t = _np.frombuffer(top.data, dtype=_np.uint8).reshape(th, tw, 4)
    tx0, ty0 = x0c - x0, y0c - y0
    sub_t = t[ty0:ty0 + (y1 - y0c), tx0:tx0 + (x1 - x0c)].astype(_np.float32) / 255.0
    sub_b = b[y0c:y1, x0c:x1].astype(_np.float32) / 255.0
    ba = sub_b[:, :, 3]
    ta = sub_t[:, :, 3]
    block = _np.empty(sub_t.shape, dtype=_np.float32)
    if mode == 'erase':
        block[:, :, :3] = sub_b[:, :, :3]
        block[:, :, 3] = ba * (1.0 - ta)
    else:
        res = sub_b[:, :, :3] * (1.0 - ta)[:, :, None] + sub_t[:, :, :3] * ta[:, :, None]
        empty = (ba <= 0.004)[:, :, None]
        res = _np.where(empty, sub_t[:, :, :3], res)
        block[:, :, :3] = _np.clip(res, 0.0, 1.0)
        block[:, :, 3] = _np.maximum(ba, ta)
    b[y0c:y1, x0c:x1] = (block * 255.0).astype(_np.uint8)
    # **厚度也要跟着搬过来，否则 `render_marks` 这条路会把每一笔的厚度都丢掉。** `blend_at` 是标记往里进的
    # 那条路（`blend` 是图层对图层的），而它此前只搬颜色。颜料在这一条路上同样是累积的，不透明的笔整份加上去，
    # 半透明的按它的覆盖加权。
    if top.relief is not None:
        if base.relief is None:
            base.relief = _np.zeros((h, w), dtype=_np.float64)
        base.relief[y0c:y1, x0c:x1] += top.relief[ty0:ty0 + (y1 - y0c), tx0:tx0 + (x1 - x0c)] * ta
    return base


def blend(base: Layer, top: Layer, mode: str = 'normal', opacity: float = 1.0) -> Layer:
    """Combines two layers. Four modes, because four is what a drawing needs.

    `normal` paints over, `multiply` darkens (shadow, pencil), `screen` lightens (highlights, glow), and `overlay`
    does both according to what is underneath, which is the one that makes colour feel like paint rather than plastic.
    """
    if (base.width, base.height) != (top.width, top.height):
        raise ValueError('layers must be the same size: %sx%s vs %sx%s'
                         % (base.width, base.height, top.width, top.height))
    out = Layer(base.width, base.height)
    if _np is not None:
        # **Only the rectangle the top layer actually touches.** Blending one mark used to sweep every pixel of the
        # page: 3.7 million of them for a mark covering two hundred, and a traced drawing has a thousand marks. The
        # rectangle around the top's non-transparent pixels is found once and the arithmetic happens there; the rest of
        # the result is the base, copied. At 2880 across, the full sweep was minutes per mark and this is a few
        # milliseconds.
        w, h = base.width, base.height
        whole_top = _np.frombuffer(top.data, dtype=_np.uint8).reshape(h, w, 4)
        alpha_top = whole_top[:, :, 3]
        occupied = _np.flatnonzero(alpha_top.ravel())
        out.data = bytearray(base.data)
        # **颜料在颜料上会堆起来，而颜色不会。** 这是厚度与颜色唯一不同的地方：颜色是替换，厚度是累积。
        # 一条不透明的笔触把它自己的厚度整份加上去，半透明的一笔只加一半，而两者都以「下面已经有多厚」为起点。
        # 没有厚度的层按零处理，所以纯线稿的合成路径上这两行什么也没做。
        if base.relief is not None or top.relief is not None:
            under = base.relief if base.relief is not None else _np.zeros((h, w), dtype=_np.float64)
            laid_relief = top.relief if top.relief is not None else _np.zeros((h, w), dtype=_np.float64)
            out.relief = under + laid_relief * (alpha_top.astype(_np.float64) / 255.0) * opacity
        else:
            out.relief = base.relief
        if not occupied.size:
            return out
        rows = occupied // w
        cols = occupied % w
        y0, y1 = int(rows.min()), int(rows.max()) + 1
        x0, x1 = int(cols.min()), int(cols.max()) + 1
        b = _np.frombuffer(base.data, dtype=_np.uint8).reshape(h, w, 4)[y0:y1, x0:x1].astype(_np.float32) / 255.0
        t = whole_top[y0:y1, x0:x1].astype(_np.float32) / 255.0
        ba = b[:, :, 3]
        ta = t[:, :, 3] * opacity
        if mode == 'multiply':
            mixed = b[:, :, :3] * t[:, :, :3]
        elif mode == 'screen':
            mixed = 1.0 - (1.0 - b[:, :, :3]) * (1.0 - t[:, :, :3])
        elif mode == 'overlay':
            mixed = _np.where(b[:, :, :3] < 0.5, 2 * b[:, :, :3] * t[:, :, :3],
                              1.0 - 2 * (1.0 - b[:, :, :3]) * (1.0 - t[:, :, :3]))
        else:
            mixed = t[:, :, :3]
        res = b[:, :, :3] * (1.0 - ta)[:, :, None] + mixed * ta[:, :, None]
        # **Where the base is empty the top goes down as it is**, which is the documented case and not a special one:
        # multiplying with nothing gives the thing.
        empty = (ba <= 0.004)[:, :, None]
        laid = t[:, :, :3] * opacity if opacity < 1.0 else t[:, :, :3]
        res = _np.where(empty, laid, res)
        alpha = _np.maximum(ba, ta)
        block = _np.empty((y1 - y0, x1 - x0, 4), dtype=_np.float32)
        block[:, :, :3] = _np.clip(res, 0.0, 1.0)
        block[:, :, 3] = alpha
        view = _np.frombuffer(out.data, dtype=_np.uint8).reshape(h, w, 4)
        view[y0:y1, x0:x1] = (block * 255.0).astype(_np.uint8)
        return out
    for index in range(0, len(base.data), 4):
        ba = base.data[index + 3] / 255.0
        ta = top.data[index + 3] / 255.0 * opacity
        # **Multiplying with nothing gives the thing.** The first version blended against the base colour whatever
        # its alpha, and a transparent base has a colour of zero, so every multiply over empty space came out black
        # -- a wash crossing a pencil line painted a black smear where there was no pencil line at all. Where the
        # base is empty there is nothing to combine with, and the top layer simply goes down.
        if ba <= 0.004:
            for channel in range(3):
                out.data[index + channel] = top.data[index + channel]
                if opacity < 1.0:
                    out.data[index + channel] = int(top.data[index + channel] * opacity + 0 * (1 - opacity))
            out.data[index + 3] = int(ta * 255)
            continue
        for channel in range(3):
            b = base.data[index + channel] / 255.0
            t = top.data[index + channel] / 255.0
            if mode == 'multiply':
                mixed = b * t
            elif mode == 'screen':
                mixed = 1.0 - (1.0 - b) * (1.0 - t)
            elif mode == 'overlay':
                mixed = 2 * b * t if b < 0.5 else 1.0 - 2 * (1.0 - b) * (1.0 - t)
            else:
                mixed = t
            out.data[index + channel] = int(max(0.0, min(1.0, b * (1 - ta) + mixed * ta)) * 255)
        out.data[index + 3] = int(max(ba, ta) * 255)
    return out


def clip(layer: Layer, mask: Layer, invert: bool = False) -> Layer:
    """Keeps [layer] only where [mask] is opaque: one alpha multiply, which is the whole of clipping.

    Cheaper and more predictable than a mask object, and it composes: clip a wash to a pencil region, clip that to a
    silhouette, and every step is a multiply of two numbers. Inverting covers the case the mask is really a hole --
    light through a window, colour outside a line -- without needing a second mask.

    **The thickness has to be clipped with the colour.** A layer's `relief` is part of that layer; leaving it whole
    after clipping the paint puts thickness outside the shape, and `light` then finds a cliff along the cut and draws
    a bright line exactly where the edge is. It is the one visible artefact a clipped layer can produce, and it turned
    up the first time a contour was drawn here (`AESTHETIC-LIBRARY.md` 4.64). A layer without relief clips exactly as
    it always did.
    """
    if (layer.width, layer.height) != (mask.width, mask.height):
        raise ValueError('layer and mask must be the same size: %sx%s vs %sx%s'
                         % (layer.width, layer.height, mask.width, mask.height))
    out = Layer(layer.width, layer.height)
    if layer.relief is not None:
        if _np is None:
            raise RuntimeError('clipping a layer that carries relief needs numpy')
        gate = _np.frombuffer(mask.data, dtype=_np.uint8).reshape(layer.height, layer.width, 4)[:, :, 3]
        gate = gate.astype(_np.float64) / 255.0
        out.relief = layer.relief * (1.0 - gate if invert else gate)
    for index in range(0, len(layer.data), 4):
        m = mask.data[index + 3] / 255.0
        if invert:
            m = 1.0 - m
        a = layer.data[index + 3] / 255.0 * m
        out.data[index] = layer.data[index]
        out.data[index + 1] = layer.data[index + 1]
        out.data[index + 2] = layer.data[index + 2]
        out.data[index + 3] = int(a * 255)
    return out


def warp(layer: Layer, displacements: list[list[tuple[float, float]]],
         corners: tuple[float, float, float, float]) -> Layer:
    """Resamples a layer through a grid of displacements, bilinearly between the grid's control points.

    **The last piece of the C tier, and the one worth having for a procedural illustrator.** A generated figure is
    assembled from placed elements, and a warp is how one of them bends -- a sleeve following an arm, a pattern
    flowing over a shoulder, a limb adjusted without redrawing it. The grid holds displacements rather than absolute
    positions, because a displacement grid composes with whatever was drawn underneath while an absolute one
    silently moves everything.

    Sampling is inverse: for each *destination* pixel the source position is looked up, which is the only way to fill
    every output pixel exactly once. A zero grid therefore returns the input unchanged, and that identity is asserted
    rather than assumed -- it is the one property that catches a transposed axis or an off-by-one corner, both of
    which still produce a picture that looks like a picture.

    `corners` is (x0, y0, x1, y1): the rectangle the grid's rows and columns span.
    """
    x0, y0, x1, y1 = corners
    rows = len(displacements)
    cols = len(displacements[0])
    out = Layer(layer.width, layer.height, layer.seed)
    for py in range(layer.height):
        for px in range(layer.width):
            u = (px - x0) / (x1 - x0) * (cols - 1) if cols > 1 and x1 != x0 else 0.0
            v = (py - y0) / (y1 - y0) * (rows - 1) if rows > 1 and y1 != y0 else 0.0
            cu = max(0.0, min(cols - 1.001, u))
            cv = max(0.0, min(rows - 1.001, v))
            i0, j0 = int(cu), int(cv)
            fu, fv = cu - i0, cv - j0
            dx = dy = 0.0
            for wi, wj, weight in ((i0, j0, (1 - fu) * (1 - fv)), (i0 + 1, j0, fu * (1 - fv)),
                                   (i0, j0 + 1, (1 - fu) * fv), (i0 + 1, j0 + 1, fu * fv)):
                if wi >= cols or wj >= rows:
                    continue
                dx += displacements[wj][wi][0] * weight
                dy += displacements[wj][wi][1] * weight
            sx = int(round(px - dx))
            sy = int(round(py - dy))
            if not (0 <= sx < layer.width and 0 <= sy < layer.height):
                continue
            source = (sy * layer.width + sx) * 4
            target = (py * layer.width + px) * 4
            out.data[target] = layer.data[source]
            out.data[target + 1] = layer.data[source + 1]
            out.data[target + 2] = layer.data[source + 2]
            out.data[target + 3] = layer.data[source + 3]
    return out


def composite(width: int, height: int, stack: list[tuple[Layer, str, float]]) -> Layer:
    """Stacks layers bottom to top, each with its own mode and opacity."""
    result = Layer(width, height)
    for layer, mode, opacity in stack:
        result = blend(result, layer, mode, opacity) if mode != 'normal' else blend(result, layer, 'normal', opacity)
    return result


def parse_hex(colour: str) -> tuple[int, int, int]:
    """`#RRGGBB` to a triple. Local rather than imported from `doc`, which imports `core`, which this file is beside --
    a three-line parse is cheaper than deciding which module is allowed to know about which."""
    text = colour.lstrip('#')
    if len(text) == 3:
        text = ''.join(c * 2 for c in text)
    if len(text) != 6:
        raise ValueError('not a #RRGGBB colour: %r' % (colour,))
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def fill_polygon(layer: 'Layer', points, colour: tuple[int, int, int], alpha: float = 1.0,
                 scale: float = 1.0, fill_rule: str = 'nonzero', holes=None, gradient=None,
                 tone=None) -> None:
    """Fills a closed polygon into `layer`, by scanline.

    **Nonzero, and this was even-odd until a referee measured it.** The old reasoning was that even-odd is what a
    bucket tool does and that `weld_endpoints` can hand back a loop that touches itself. The first half is true and
    irrelevant; the second was never checked and is false -- `region_fill` returns one *simple* loop per region, and on
    every closed shape tried the two rules agree to the pixel, so even-odd was buying nothing on the fill path.

    What it was costing is a stroke that doubles back. `outline()` offsets the inside of a turn past the centreline, so
    at a hairpin its polygon crosses itself, and under even-odd the crossed half has crossing number 2 and is
    **erased**. Measured on an eyelash-style reversal (165 deg), against cairo's stroker as the reference:

        cairo stroke                    1283 px
        outline() filled nonzero        1233 px
        outline() filled even-odd        138 px
        raster.fill_polygon (was)        116 px     <- 91% of the stroke gone

    **Two independent things already said nonzero and neither had been compared against the renderer.** `_holes`, the
    acceptance test for the outline expansion, counts centreline points with *nonzero* winding -- so the test and the
    renderer disagreed about the contract and both passed. And cairo, which knows nothing about this file, agrees with
    nonzero. That is what `audit.py` is for; this is the first thing it found.

    The two end pixels of each span take partial coverage, so a slanted edge is not a staircase. Edges that are
    horizontal are not anti-aliased, which is a visible limitation and is left in rather than papered over.

    Pure Python, like the rest of this file: one pass over the scanlines the polygon actually occupies.
    """
    n = len(points)
    if n < 3 or alpha <= 0:
        return
    # **A hole forces even-odd, and only then.** With holes, a scanline crossing the outside once and the hole twice
    # has an odd crossing number inside the ring and an even one inside the hole, which is the shape. Without holes the
    # rule stays whatever the caller asked for, because nonzero is what keeps a hairpin's doubled-back half alive.
    rings = [points] + [list(h) for h in (holes or []) if len(h) >= 3]
    if len(rings) > 1:
        fill_rule = 'even-odd'
    if fill_rule not in ('nonzero', 'even-odd'):
        raise ValueError('unknown fill rule %r' % (fill_rule,))
    scaled = [([p[0] * scale for p in ring], [p[1] * scale for p in ring]) for ring in rings]
    y0 = max(0, int(min(min(ys) for _xs, ys in scaled)))
    y1 = min(layer.height - 1, int(max(max(ys) for _xs, ys in scaled)) + 1)
    r, g, b = colour
    grad = None
    if gradient:
        # **Prepared once, applied per pixel.** The two endpoints are scaled like every other coordinate here, so a
        # gradient stated in page units lands where its shape does.
        gx0, gy0 = float(gradient['from'][0]) * scale, float(gradient['from'][1]) * scale
        gx1, gy1 = float(gradient['to'][0]) * scale, float(gradient['to'][1]) * scale
        gdx, gdy = gx1 - gx0, gy1 - gy0
        gden = gdx * gdx + gdy * gdy
        if gden <= 1e-9:
            gden = 1.0
        grad = (gx0, gy0, gdx, gdy, gden, parse_hex(gradient['colour0']), parse_hex(gradient['colour1']))
    for py in range(y0, y1 + 1):
        # **A screen is a lattice on the page, not a texture on the shape.** `tone` arrives already phased to the page,
        # so this loop only reads it: an area drawn beside another at the same pitch continues its neighbour's dots
        # instead of starting a fresh lattice at its own corner.
        tone_row = tone[py] if tone is not None else None
        yc = py + 0.5
        crossings: list[tuple[float, int]] = []
        for xs, ys in scaled:
            n = len(xs)
            for i in range(n):
                j = (i + 1) % n
                ya, yb = ys[i], ys[j]
                if ya == yb:
                    continue
                # half-open in y, so a vertex shared by two edges is counted once and not twice
                if ya <= yc < yb:
                    direction = 1                      # downward on screen, and +y is down
                elif yb <= yc < ya:
                    direction = -1
                else:
                    continue
                t = (yc - ya) / (yb - ya)
                crossings.append((xs[i] + t * (xs[j] - xs[i]), direction))
        if len(crossings) < 2:
            continue
        crossings.sort()
        spans: list[tuple[float, float]] = []
        if fill_rule == 'even-odd':
            for k in range(0, len(crossings) - 1, 2):
                spans.append((crossings[k][0], crossings[k + 1][0]))
        else:
            # Accumulate signed winding; a span is inside wherever it is not zero. This is the whole fix: an offset
            # that overshoots the centreline adds winding instead of cancelling.
            winding = 0
            start = 0.0
            for x, direction in crossings:
                if winding == 0:
                    start = x
                winding += direction
                if winding == 0:
                    spans.append((start, x))
        row = py * layer.width * 4
        for left, right in spans:
            if right <= 0 or left >= layer.width:
                continue
            left = max(0.0, left)
            right = min(float(layer.width), right)
            first = int(left - 0.5)
            last = int(right - 0.5)
            for px in range(max(0, first), min(layer.width - 1, last) + 1):
                # coverage of this pixel's 1-wide box by the span
                cover = min(px + 0.5, right) - max(px - 0.5, left)
                if cover <= 0:
                    continue
                a = alpha * min(1.0, cover)
                if tone_row is not None:
                    a *= tone_row[px]
                index = row + px * 4
                old_a = layer.data[index + 3] / 255.0
                new_a = a + old_a * (1 - a)
                if new_a <= 0:
                    continue
                if grad is not None:
                    # **The value travels across the shape**, which is what a painted garment does inside one piece of
                    # material. Interpolated per pixel, so it costs one multiply and one add here.
                    gx0, gy0, gdx, gdy, gden, c0, c1 = grad
                    t = ((px + 0.5 - gx0) * gdx + (py + 0.5 - gy0) * gdy) / gden
                    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                    cr = c0[0] + (c1[0] - c0[0]) * t
                    cg = c0[1] + (c1[1] - c0[1]) * t
                    cb = c0[2] + (c1[2] - c0[2]) * t
                else:
                    cr, cg, cb = r, g, b
                layer.data[index] = int((cr * a + layer.data[index] * old_a * (1 - a)) / new_a)
                layer.data[index + 1] = int((cg * a + layer.data[index + 1] * old_a * (1 - a)) / new_a)
                layer.data[index + 2] = int((cb * a + layer.data[index + 2] * old_a * (1 - a)) / new_a)
                layer.data[index + 3] = int(new_a * 255)


def fill_layer(mark: dict, width: int, height: int, scale: float = 1.0) -> 'Layer':
    """Rasterises a `fill` mark.

    Takes the mark rather than a bare polygon because the appearance belongs to the mark: colour and opacity are its
    fields, and a renderer that had to be told them separately would be a second place for them to live.
    """
    geometry = mark['geometry']
    appearance = mark.get('appearance', {})
    points = geometry.get('points')
    if not points:
        raise ValueError('fill mark %r has no points' % (mark.get('id'),))
    layer = Layer(width, height)
    # **A screen is built here, once, and handed to the scanline loop row by row.** `tone` on a fill says the area's
    # value is rendered as dots or lines rather than as a flat tint. The pitch and the angle belong to the page, so the
    # lattice is phased to the page as well -- **and that means the origin the screen is given must be the page's,
    # not this shape's corner.** `screen` builds a lattice over the whole layer, so its rows and columns are already
    # page coordinates; passing the shape's own minimum corner offsets the lattice a second time, and two neighbours
    # then start their cells at different phases. Measured: one 200-wide fill and two 100-wide neighbours at pitch 9
    # gave 5809 differing pixels, and a neighbour whose corner is off by half a cell came out half a cell out of step.
    # A screen belongs to the page, which is exactly what leaving `origin` at its default says.
    screen = None
    spec = geometry.get('tone')
    if spec:
        if _np is None:  # pragma: no cover - a screen needs numpy for the lattice
            raise RuntimeError('a tone needs numpy')
        from . import tone as tone_module
        screen = tone_module.screen(spec, width, height, scale=scale)
    # **A shape with holes is filled even-odd**, so a point inside a hole counts as outside. Without them the rule
    # stays nonzero, because an offset outline that doubles back at a hairpin must not be erased -- that measurement is
    # in `fill_polygon`'s own docstring and it still holds for every fill that has no holes.
    fill_polygon(layer, points, parse_hex(appearance.get('fill', '#808080')),
                 float(appearance.get('opacity', 1.0)), scale,
                 holes=geometry.get('holes') or None,
                 gradient=geometry.get('gradient') or None,
                 tone=screen)
    return layer


#: **How far apart the dabs of an integrated stroke sit, as a fraction of the tip's diameter.** The maximum path
#: keeps each brush's own `spacing` because for it the spacing is a *texture* -- overlapping dabs simply do not
#: deepen, so their distance changes how the edge reads and nothing else. The density path has no such freedom: it
#: saturates wherever a dab covers, so the stroke's outline is the union of the tips and the spacing is the
#: scalloping of its edge. **2.5 percent is the figure Compositor publishes for soft tips**, which is where the
#: number comes from rather than from a sweep here -- and it is twenty times finer than the brush table's 56.
DENSITY_STEP = 0.025

#: **The width above which the deposition method is a question worth asking, and the figure it used to hold was wrong.**
#: The reason recorded here was that below some width a stroke is a line and the two methods are the same picture. **A
#: probe on a three-pixel stroke says they are not.** The same 161-pixel stroke carries **60 local minima of alpha on
#: the maximum path** -- alpha swinging 99 to 254 around a mean of 197 -- and **6 on the integral**, whose middle sits
#: at 255. A bead every 2.7 pixels is exactly what a hand-drawn line is not, and **a three-pixel stroke is what an
#: outline is**: the maximum path will not deepen a seam, so two soft tips meeting leave only their falloff there.
#:
#: So the threshold comes down to where no stroke is, and every mark is deposited as an integral. The cost is dab count,
#: and it is small here because the step has a floor of one pixel: on a fine line the step goes from 1.68 to 1.0, which
#: is 1.7 times the dabs and not the 20 the 2.5 percent would ask for on a wide one.
WIDE_STROKE = 1.0


def _resample_profile(values, count):
    """Stretch a per-control-point profile over the stroke's resampled path, by position.

    **This is the repair for a fault that made every width curve a lie.** A record's `centre` is resampled -- a
    four-point stroke becomes forty-three points -- while `width_profile` keeps the four values the caller wrote. The
    dab loop indexes the profile by the resampled segment number, so the profile covered the first three segments and
    the last value covered everything after them: **a curve meant to describe the whole stroke described its first
    per cent, and a variable width produced a string of beads down the middle of an otherwise flat stroke.**
    `tools/probe_stroke_dab.py` holds the measurement -- flat profiles read 0.541 to 0.600 along the centreline with no
    jumps, varying ones read 0.310 to 1.000 with twenty-four.

    **The stretch is by index, not by arc length.** Resampling the path is itself close to uniform in arc length within
    a segment, so the index is a good proxy; measuring each control point's arc length would be more exact and would
    also mean the two resamplings could disagree. A caller who needs a width at a specific point should give enough
    control points that the difference is below a pixel.
    """
    if not values:
        return []
    if len(values) == 1 or count <= 1:
        return [float(values[0])] * max(1, count)
    out = []
    last = len(values) - 1
    for i in range(count):
        position = i * last / (count - 1)
        low = int(math.floor(position))
        high = min(low + 1, last)
        fraction = position - low
        out.append(float(values[low]) * (1.0 - fraction) + float(values[high]) * fraction)
    return out


def render_marks(marks: list[dict], width: int, height: int, scale: float = 1.0,
                 paper: Paper | None = None, outlined: set | None = None,
                 outline_tint: float | None = None, outline_width: float | None = None,
                 sweep: bool = False) -> 'Layer':
    """Composites marks bottom to top **in the order given**, which is the drawing order.

    **Order is the picture.** A later mark covers an earlier one, so this must not sort, group or otherwise reorder
    what it is handed -- a renderer that rendered by kind, or by stage, would produce a perfectly plausible image of
    something that was never drawn. The caller decides the order; `Project.in_stage` and `Project.upto` are how.

    **`outlined` is the set of layer names drawn with their own line, and passing it is the whole of what the
    `Layer.outline` attribute ever needed.** Until now that attribute was declared on all twenty-one layers of the
    standard figure, validated by `layers.check`, written into the project file, and **read by no renderer** -- which
    this project's own rule calls a comment rather than a feature, and which it has been caught by twice now: once for
    a shader capability the material declares and never uses, and once here.

    The line is the part's own shape **drawn again, thicker, in the tint colour, underneath** -- grown rather than
    offset, so that the outline and the shape are the same geometry through the same rasteriser and cannot disagree
    about where the shape is. `cel.outline_colour` multiplies the fill by the tint, which is what the asset's own
    property does, so a hair's outline is a darker hair rather than a grey.
    """
    from .cel import OUTLINE_TINT, OUTLINE_WIDTH, outline_colour

    tint = OUTLINE_TINT if outline_tint is None else outline_tint
    line = OUTLINE_WIDTH if outline_width is None else outline_width
    out = Layer(width, height, paper=paper)
    for mark in marks:
        if mark.get('state', 'live') != 'live':
            continue
        kind = mark.get('kind')
        if kind == 'stroke':
            geometry = mark['geometry']
            record = {'brush': geometry['brush'], 'centre': geometry['centre'], 'pressure': geometry['pressure'],
                      'seed': geometry.get('seed', 0),
                      'width_profile': geometry.get('width_profile') or [],
                      'alpha_profile': geometry.get('alpha_profile') or [],
                      'colour_profile': geometry.get('colour_profile') or [],
                      'height': float(geometry.get('height') or 0.0),
                      'bristle': float(geometry.get('bristle') or 0.0),
                      'bristle_pitch': float(geometry.get('bristle_pitch') or 0.0),
                      'absolute_width': bool(geometry.get('absolute_width', False)),
                      # **Every field the renderer reads has to be named here**, and this is the third place a
                      # record is rebuilt from a document: `stroke_record` writes one, `add_stroke` copies it into a
                      # mark through a whitelist, and this rebuilds a working dict for the rasteriser. A field added
                      # to the first and not to the other two is a field that renders as a default -- measured, twice,
                      # for `page_long` and `edge` in the same afternoon.
                      'page_long': float(geometry.get('page_long') or 0.0),
                      'edge': float(geometry.get('edge') or 0.0),
                      'soft': float(geometry.get('soft') or 0.0),
                      'colour_int': parse_hex(mark_ink(mark))}
            # **Above `WIDE_STROKE` the deposition is integrated, below it the maximum is used.** The ripple along
            # a stroke is the same fraction of its mean at every width -- 0.37 on the ink brush at four pixels and at
            # eighty -- so what the width decides is only whether it can be seen. Measured after the normalisation
            # became a ratio of two sums, the peak agrees between the two methods on all four brushes (229/232,
            # 169/176, 243/245, 85/86) and the residual ripple on pencil and wash is their own paper grain.
            profile = record.get('width_profile') or []
            widest = max(profile) if profile else BRUSHES[record['brush']]['width']
            # **The mark's own box, not the page.** A page-sized allocation per mark is what made a twelve thousand
            # stroke structure render take ten minutes; the arithmetic is identical inside a box the size of the mark,
            # and `blend_at` puts it back at the right offset.
            centre = geometry.get('centre') or []
            if not centre:
                continue
            pad = int(widest * scale) + 4
            xs = [p[0] * scale for p in centre]
            ys = [p[1] * scale for p in centre]
            x0 = max(0, int(min(xs)) - pad)
            y0 = max(0, int(min(ys)) - pad)
            x1 = min(width, int(max(xs)) + pad + 1)
            y1 = min(height, int(max(ys)) + pad + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            shifted = [[p[0] - x0 / scale, p[1] - y0 / scale] for p in centre]
            box_w, box_h = x1 - x0, y1 - y0
            local = dict(record)
            local['centre'] = shifted
            # **The brush's own edge decides the model, not a global switch.** A hard-edged tool -- a pen, a marker, a
            # gel pen -- goes through the distance field, where a width is a width and there is no stamp to quantise. A
            # soft-edged one -- watercolour, an airbrush, a loaded brush -- keeps the stamped model, because the falloff
            # of a soft dab is exactly what that material looks like, and flattening it into a hard edge would be a loss
            # rather than a fix. Watercolour is a class of its own here, not the house style.
            soft = brush_at(record['brush'], record.get('size', 1.0)).get('edge', 'hard') == 'soft'
            if sweep or not soft:
                layer = sweep_layer(local, box_w, box_h, scale, paper=paper)
            else:
                layer = stroke_layer(local, box_w, box_h, scale, paper=paper,
                                     density=widest >= WIDE_STROKE,
                                     absolute_width=record.get('absolute_width', False))
            if outlined and mark.get('layer') in outlined:
                # **The growth is stated in width units, and a stroke's width is its brush's**, so the scale is
                # relative to that rather than absolute -- a fine line and a wash both get the same line around them,
                # which is what the art does: the outline's width does not follow the fill's.
                brush_width = max(0.5, BRUSHES[record['brush']]['width'])
                grown = dict(local)
                grown['colour_int'] = outline_colour(record['colour_int'], tint)
                # **The outline takes the same deposition rule as the fill, and leaving it out is what kept the
                # beads after everything else was fixed.** It is drawn wider than the shape it surrounds, so it is
                # the outermost edge of the mark -- and on the maximum path, whose dabs do not deepen each other, a
                # wider tip means a wider spacing and therefore a scalloped rim standing proud of a smooth fill.
                # Measured on a bone: with the rule the left edge reverses direction 0 times over 66 rows, without
                # it 6 times, and the picture shows a wavy rim that survives every fix applied to the fill.
                behind = stroke_layer(grown, box_w, box_h, scale, paper=paper,
                                      density=widest >= WIDE_STROKE,
                                      width_scale=1.0 + 2.0 * line / brush_width,
                                      absolute_width=record.get('absolute_width', False))
                blend_at(out, behind, x0, y0)
                out = blend_at(out, layer, x0, y0)
            else:
                out = blend_at(out, layer, x0, y0)
            # **The stroke is already on the page.** Falling through to the shared blend below would composite it a
            # second time, over the whole page, which is both a wrong picture and the cost this branch exists to avoid.
            continue
        elif kind in ('fill', 'erase'):
            # **The mark's own box, not the page.** The same argument and the same arithmetic as the stroke branch above:
            # a page-sized buffer per mark is what made twenty-seven thousand fills spend over fifty minutes in the
            # composer on a large reference, and the picture inside a box the size of the mark is identical.
            geometry = mark['geometry']
            pts = geometry.get('points') or []
            if len(pts) < 3:
                continue
            xs = [p[0] * scale for p in pts]
            ys = [p[1] * scale for p in pts]
            pad = 2
            x0 = max(0, int(min(xs)) - pad)
            y0 = max(0, int(min(ys)) - pad)
            x1 = min(width, int(max(xs)) + pad + 1)
            y1 = min(height, int(max(ys)) + pad + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            # **The gradient's endpoints are page coordinates too**, so they move by the same offset as the points. Left
            # behind, a gradient would shade the shape from the wrong direction while still looking perfectly plausible
            # -- a fault that reads as an artistic choice rather than as a bug.
            shift_x = x0 / scale
            shift_y = y0 / scale
            local = dict(mark)
            local_geometry = dict(geometry)
            local_geometry['points'] = [[p[0] - shift_x, p[1] - shift_y] for p in pts]
            if geometry.get('holes'):
                local_geometry['holes'] = [[[p[0] - shift_x, p[1] - shift_y] for p in ring]
                                          for ring in geometry['holes']]
            if geometry.get('gradient'):
                gradient = dict(geometry['gradient'])
                gradient['from'] = [gradient['from'][0] - shift_x, gradient['from'][1] - shift_y]
                gradient['to'] = [gradient['to'][0] - shift_x, gradient['to'][1] - shift_y]
                local_geometry['gradient'] = gradient
            local['geometry'] = local_geometry
            layer = fill_layer(local, x1 - x0, y1 - y0, scale)
            # **The eraser shares every pixel of this branch and differs in one word.** Its geometry is a region like a
            # fill's, so it gets the same box and the same scanline pass; what changes is the compositing, and that is
            # destination-out: the ink goes away instead of more going down.
            out = blend_at(out, layer, x0, y0, mode='erase' if kind == 'erase' else 'normal')
            continue
        else:
            raise ValueError('cannot render a mark of kind %r' % (kind,))
        out = blend(out, layer, 'normal', 1.0)
    return out


def _flatten_ink(ink, red, green, blue, colour, width, height, data):
    """The coverage buffer written into an RGBA layer, one pixel at a time -- **the reference implementation.**

    Kept rather than deleted for one reason: the vectorised version beside it has to prove it produces the same bytes,
    and a comparison against "what it used to do" cannot be made once the old code is gone. `tests/test_flat_ink.py`
    is the only caller, and it is the reason this function still exists.

    **Two different roundings live in these six lines, and they are not interchangeable.** A stroke with no colour
    profile writes the mark's single colour, which needs no rounding at all. One with a profile writes three channels
    through `int()`, which **truncates**; the alpha channel uses `round()`, which does not. Truncation and rounding
    disagree on every value with a fractional part above one half, so a vectorised version that used one for both
    would leave a picture that looks right and differs in most of its pixels.
    """
    r, g, b = colour
    flat = ink.ravel()
    flat_r = red.ravel() if red is not None else None
    flat_g = green.ravel() if green is not None else None
    flat_b = blue.ravel() if blue is not None else None
    for y in range(height):
        row = y * width * 4
        for x in range(width):
            cell = y * width + x
            a = flat[cell]
            if a <= 0.0:
                continue
            index = row + x * 4
            if flat_r is None:
                data[index] = r
                data[index + 1] = g
                data[index + 2] = b
            else:
                data[index] = int(min(255.0, max(0.0, flat_r[cell])))
                data[index + 1] = int(min(255.0, max(0.0, flat_g[cell])))
                data[index + 2] = int(min(255.0, max(0.0, flat_b[cell])))
            data[index + 3] = int(min(255.0, round(a * 255.0)))


def _flatten_ink_numpy(ink, red, green, blue, colour, width, height, data):
    """The same six decisions, applied to the whole layer at once.

    **`np.rint` is the same rounding as Python's `round()`** -- both round a half to even -- and `astype` is the same
    truncation as `int()` on a non-negative value, which is why the two paths agree rather than merely look alike.
    The clipping is restated on both sides because a coverage of exactly zero is skipped by the reference loop rather
    than written, and `np.clip` is what makes "skipped" and "written with zero" the same bytes.
    """
    view = _np.frombuffer(data, dtype=_np.uint8).reshape(height, width, 4)
    # **The test for "did this pixel receive anything" is the raw coverage, not the rounded alpha.** They are not the
    # same question and the difference is most of the pixels at the edge of a stroke: a coverage of 0.001 rounds to an
    # alpha of zero and still writes its colour, because the reference loop skips only on `a <= 0.0` and the colour is
    # written before the alpha is rounded. Judging by the rounded alpha instead skips those pixels and leaves their
    # colour at zero -- invisible, since their alpha is zero, and a byte-level difference in every soft edge.
    on = ink > 0.0
    alpha = _np.rint(ink * 255.0)
    _np.clip(alpha, 0.0, 255.0, out=alpha)
    alpha = alpha.astype(_np.uint8)
    if not on.any():
        return
    if red is None:
        r, g, b = colour
        view[on, 0] = r
        view[on, 1] = g
        view[on, 2] = b
    else:
        # **Truncation, to match the loop's `int()`.** `np.clip` then `astype` is the same operation the reference
        # writes one pixel at a time; using `np.rint` here would be the rounding the alpha channel uses and would
        # make every colour channel one shade light wherever the fraction is over a half.
        for channel, plane in ((0, red), (1, green), (2, blue)):
            value = _np.clip(plane, 0.0, 255.0).astype(_np.uint8)
            view[on, channel] = value[on]
    view[on, 3] = alpha[on]


def sweep_layer(record: dict, width: int, height: int, scale: float = 1.0,
                paper: Paper | None = None) -> Layer:
    """A stroke laid down as **a distance from its centre line**, not as a row of stamped discs.

    **What the discs cost, measured.** A fourteen-pixel brush at 0.35 of a diameter places its dabs 4.9 pixels apart, so
    a single column of the picture is covered by two of them or by three. That count is an integer, and when it steps the
    ink in the column steps with it: **33 per cent by arithmetic, 28 per cent as measured**. It does not go away when the
    spacing is halved (0.25 gives 2.32 pixels of wobble, 0.12 gives 2.29), nor when the breathing is turned off, nor when
    the tremor is -- because it is not any of those, it is the discreteness of the stamp.

    **What replaces it.** The coverage of a pixel is a function of its distance to the centre line, which is continuous in
    the pixel's position: a stroke's edge is a curve, and a curve sampled per pixel has no steps in it. The profile is a
    hard edge with one pixel of anti-aliasing, which is what the dab's own edge did, so the two models agree about a
    narrow stroke and differ only where the stamp's discreteness was visible.

    Widths come from `stroke_widths`, so the pressure model, the role multiplier and `size` all apply exactly as before:
    this changes how a width becomes pixels, not what the width is.
    """
    if _np is None:  # pragma: no cover - the distance field is the whole point, so there is no pure-Python fallback
        raise RuntimeError('sweep_layer needs numpy')

    brush = brush_at(record['brush'], record.get('size', 1.0))
    colour = record.get('colour_int') or (26, 22, 32)
    layer = Layer(width, height, paper=paper)
    centre = record.get('centre') or []
    if len(centre) < 2:
        return layer

    points = _np.asarray([(x * scale, y * scale) for x, y in centre], dtype=_np.float64)
    # **How soft the edge is, from the record, because it is a property of the material.** A line drawn with this
    # renderer's own one pixel of anti-aliasing crosses in 1.75 to 2.00 pixels on measured copies; an artist's line
    # crosses in 2.70 to 4.43 -- see `tools/edge_scale.py` for the same difference read the other way. Zero means the
    # record does not say, and one pixel is what this file has always done.
    edge = max(1e-6, float(record.get('edge') or 1.0))
    # **The shape of the boundary, as a power of its own ramp.** Coverage falls linearly from `half` to the outer
    # edge, which makes a stroke's cross-section a trapezium: flat across the top, straight down the sides. A loaded
    # brush is not that -- the pigment stays near full through the middle of the mark and thins quickly towards both
    # rims -- and the difference is visible the moment a mark is wider than a pencil line. `soft = 0` is the linear
    # ramp every existing drawing was made with; `soft = 1` makes the shoulders fall as the square of the distance,
    # which is close to what a flat oil brush leaves.
    soft = max(0.0, float(record.get('soft') or 0.0))
    # **笔毛：沿笔画走的栅格，每一格是一根毛。** 零表示不画毛，而零是默认 —— 这个字段加进来时，此前画过的
    # 每一笔都没有它，所以它们的像素一个也不动。
    bristle = max(0.0, min(1.0, float(record.get('bristle') or 0.0)))
    # **湿笔：墨在纸里往外走多远。** 干笔的边是 `ramp` 从 `half` 到零，那是一条边界；湿笔在边界之外还留着一圈极淡
    # 的墨 —— 那不是边，是渗出去的那一层。`bleed` 是这个外圈的特征长度（像素），覆盖按 `exp(-d / bleed)` 衰减。
    #
    # **笔心不动。** 湿的是外圈，不是整条笔变软 —— 把 `soft` 调大做出来的「湿」是整笔发灰，而真实的湿笔中心仍然
    # 浓、只是边上有墨爬出去。零是干笔，也是此前每一笔的值。
    bleed = max(0.0, float(record.get('bleed') or 0.0))
    bristle_pitch = max(0.5, float(record.get('bristle_pitch') or 2.5))
    seed = float(record.get('seed', 0) or 0.0)
    # **The page comes from the record, and the canvas deliberately does not overrule it.** A brush's width is a share
    # of the page it was fixed on, but the canvas is not that page: a thumbnail, a crop and a test all fill a canvas far
    # smaller than the drawing, and reading the page off one would thin every brush to a hair -- measured, six tests
    # that draw a stroke on a 500-pixel canvas broke the moment the renderer started believing its own size. So a
    # caller that knows the page says so on the record, and a record that says nothing is read against the table's own
    # page. Every reader of that number -- this path, the vector paths, the auditor -- reads the same one.
    # **剖面按位置铺开，不循环重复。** 上一版是 `np.resize`，而 `np.resize` 短了就把原数组循环填满 —— 三个值的
    # 剖面落在一支笔上会变成 6,24,6,6,24,6,… 于是宽度沿路径来回跳，画面上就是一串分开的珠子（`AESTHETIC-LIBRARY`
    # 4.74 记的就是它）。一条从宽到窄的曲线要的是插值，不是重复。`colour_profile` 下面用的是同一个写法，这里
    # 照抄它。
    widths = _np.asarray(stroke_widths(record), dtype=_np.float64) * scale
    if widths.size != points.shape[0]:
        widths = _np.interp(_np.linspace(0.0, 1.0, points.shape[0]),
                            _np.linspace(0.0, 1.0, widths.size), widths)
    opacity = float(brush['opacity'])
    profile = record.get('alpha_profile') or []
    alpha = _np.full(points.shape[0], opacity, dtype=_np.float64)
    if profile:
        stretched = _np.asarray(profile, dtype=_np.float64)
        if stretched.size != points.shape[0]:
            stretched = _np.interp(_np.linspace(0.0, 1.0, points.shape[0]),
                                   _np.linspace(0.0, 1.0, stretched.size), stretched)
        alpha = opacity * stretched

    # **The path is resampled along its length before anything is drawn.** A record's centre line arrives expanded to about
    # one point per pixel, and a distance field per point costs the same for a segment one pixel long as for one two pixels
    # long -- so the twelve thousand points of a nine-hundred-pixel stroke were twelve thousand small array operations,
    # which measured at 1228 ms against the stamp model's 50. Two pixels per segment is still four times finer than the
    # narrowest brush, and the field is a distance functio, so a straight segment carries its share exactly.
    step = 2.0
    gaps = _np.hypot(_np.diff(points[:, 0]), _np.diff(points[:, 1]))
    walked = _np.concatenate([[0.0], _np.cumsum(gaps)])
    total = float(walked[-1])
    if total <= 0.0:
        return layer
    count = max(2, int(total / step) + 1)
    along = _np.linspace(0.0, total, count)
    points = _np.stack([_np.interp(along, walked, points[:, 0]),
                        _np.interp(along, walked, points[:, 1])], axis=1)
    widths = _np.interp(along, walked, widths)
    alpha = _np.interp(along, walked, alpha)
    # **The tint is resampled on the same `along` as the geometry**, so a colour that varies inside one mark varies
    # with it rather than with some other parameterisation. `None` means the mark is one colour, which is the case the
    # writing loop below has always handled and still short-circuits to.
    tint = record.get('colour_profile') or []
    if tint:
        tint = _np.asarray(tint, dtype=_np.float64)
        if tint.ndim != 2 or tint.shape[0] < 2:
            tint = None
        else:
            if tint.shape[0] != walked.shape[0]:
                tint = _np.stack([_np.interp(_np.linspace(0.0, 1.0, walked.shape[0]),
                                             _np.linspace(0.0, 1.0, tint.shape[0]), tint[:, c])
                                  for c in range(3)], axis=1)
            tint = _np.stack([_np.interp(along, walked, tint[:, c]) for c in range(3)], axis=1)
    else:
        # An empty profile is not a profile; the writing loop below branches on `None`, and a bare `[]` would take
        # the colour path and then find nothing to index.
        tint = None

    ink = _np.zeros((height, width), dtype=_np.float64)
    # **颜料不止有颜色，还有多厚。** 厚度为零时这里什么都不建，所以每一张此前画出来的图的行为与像素都不变；
    # 一旦某一笔记下了 `height`，这一笔就同时写进一层高度图，而 `light` 能把那层高度变成侧光下的起伏。
    thickness = max(0.0, float(record.get('height') or 0.0))
    relief = _np.zeros((height, width), dtype=_np.float64) if thickness > 0.0 else None
    red = _np.zeros((height, width), dtype=_np.float64) if tint is not None else None
    green = _np.zeros((height, width), dtype=_np.float64) if tint is not None else None
    blue = _np.zeros((height, width), dtype=_np.float64) if tint is not None else None
    # **One segment at a time, inside that segment's own box.** The distance field is written over the pixels the segment
    # can reach and nowhere else, so the cost follows the ink rather than the page.
    for i in range(points.shape[0] - 1):
        ax, ay = points[i]
        bx, by = points[i + 1]
        # **湿笔的外圈要算进这个框里。** 第一版只按 `half` 加一像素取框，于是那一圈晕在框外被切掉 —— 画面上
        # 湿笔和干笔一模一样，而测试量到的正是这个。**一个按笔画取框的渲染器，每加一种「超出笔画」的效果，都要
        # 同时把框放大**；否则效果被裁掉，而代码看起来是对的。
        radius = 0.5 * max(widths[i], widths[i + 1]) + 1.0 + (bleed * 3.2 if bleed > 0.0 else 0.0)
        x0 = max(0, int(_np.floor(min(ax, bx) - radius)))
        x1 = min(width, int(_np.ceil(max(ax, bx) + radius)) + 1)
        y0 = max(0, int(_np.floor(min(ay, by) - radius)))
        y1 = min(height, int(_np.ceil(max(ay, by) + radius)) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        xs = _np.arange(x0, x1, dtype=_np.float64) + 0.5
        ys = _np.arange(y0, y1, dtype=_np.float64) + 0.5
        gx, gy = _np.meshgrid(xs, ys)
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 <= 1e-12:
            distance = _np.hypot(gx - ax, gy - ay)
        else:
            t = _np.clip(((gx - ax) * dx + (gy - ay) * dy) / length2, 0.0, 1.0)
            distance = _np.hypot(gx - (ax + t * dx), gy - (ay + t * dy))
        # **Half a width either side, with `edge` pixels of anti-aliasing at the boundary** -- the same statement the
        # dab's own coverage makes, so a two-pixel line looks the same under either model. **`edge = 1` is the shipped
        # behaviour and the algebra is identical to it**; a wider value softens the transition without moving where the
        # line's boundary sits, because the half-coverage point stays at `distance == half`.
        #
        # **The reason it is a parameter is measured, not stylistic.** Walking across a line on eleven artist drawings,
        # the grey takes 2.70 to 4.43 pixels to fall from the field to the ink at the median, while a copy drawn with
        # this renderer crosses in 1.75 to 2.00 -- which is exactly what `edge_scale` reports as "the copy is harder".
        half = 0.5 * (widths[i] + (widths[i + 1] - widths[i]) * _np.clip(
            (((gx - ax) * dx + (gy - ay) * dy) / length2) if length2 > 1e-12 else 0.0, 0.0, 1.0))
        ramp = _np.clip((half + 0.5 * edge - distance) / max(edge, 1e-6), 0.0, 1.0)
        coverage = ramp if soft <= 0.0 else ramp ** (1.0 + soft)
        # **湿的那一圈。** 在笔的有效半径之外，覆盖按指数衰减，峰值是笔心的一半以下 —— 它比任何一笔都淡，而它
        # 铺开的宽度可以比笔本身大好几倍。那正是墨在纸里走的样子：**浓的部分留在笔走过的地方，淡的部分走到笔没
        # 到过的地方。**
        if bleed > 0.0:
            outside = _np.clip(distance - half, 0.0, None)
            halo = _np.exp(-outside / bleed) * 0.28
            coverage = _np.maximum(coverage, halo)
        share = (((gx - ax) * dx + (gy - ay) * dy) / length2) if length2 > 1e-12 else 0.0
        here = coverage * (alpha[i] + (alpha[i + 1] - alpha[i]) * share)
        # **一支笔是几十根毛，不是一条带。** `grain` 给的是均匀噪声，它能做「粗糙」，做不了「毛」—— 因为毛有
        # 方向：每一根沿着笔画走，相邻两根留下的量不同，而同一根在整笔里保持一致。所以这里按**横向的栅格**取编号，
        # 由编号与种子算一个固定的伪随机，再把那个数乘到覆盖上。`pitch` 是两根毛的间距（像素）。
        #
        # 横向要有符号：到中心线的距离本身是对称的，两侧会用同一根毛的花纹，看起来像一条织带。
        if bristle > 0.0:
            seg_len = float(_np.hypot(dx, dy)) or 1.0
            across = ((gx - ax) * (-dy) + (gy - ay) * dx) / seg_len
            strand = _np.floor(across / bristle_pitch)
            hashed = _np.sin(strand * 12.9898 + seed * 78.233) * 43758.5453
            hashed -= _np.floor(hashed)
            here = here * (1.0 - bristle * 0.42 + bristle * 0.62 * hashed)
        if tint is None:
            ink[y0:y1, x0:x1] = _np.maximum(ink[y0:y1, x0:x1], here)
        else:
            # **The newest mark wins the pixel, colour and all.** The alpha channel keeps the maximum, as it always
            # has, so a pixel belongs to the segment that covered it most; its colour has to come from that same
            # segment or the two would describe different strokes.
            better = here > ink[y0:y1, x0:x1]
            ink[y0:y1, x0:x1] = _np.where(better, here, ink[y0:y1, x0:x1])
            weight = _np.clip(share, 0.0, 1.0) if not isinstance(share, float) else share
            for channel, plane in ((0, red), (1, green), (2, blue)):
                mixed = tint[i][channel] + (tint[i + 1][channel] - tint[i][channel]) * weight
                plane[y0:y1, x0:x1] = _np.where(better, mixed, plane[y0:y1, x0:x1])
        if relief is not None:
            # 厚度与覆盖同步取最大：像素的突起由盖得最深的那一段决定，与它的颜色出自同一段是同一个道理。
            relief[y0:y1, x0:x1] = _np.maximum(relief[y0:y1, x0:x1], here * thickness)

    # **Grain multiplies the coverage, as it did on the dabs**, so a chalk stroke still reads as chalk rather than as a
    # smooth band that happens to be pale.
    grain = float(brush.get('grain', 0.0))
    if grain > 0.0:
        rng = _np.random.default_rng(int(record.get('seed', 0)) + 7919)
        ink *= 1.0 - grain * rng.random(ink.shape)

    # **One array operation writes the whole layer**, and the loop that did it a pixel at a time is `_flatten_ink`.
    # The two produce the same bytes -- `tests/test_flat_ink.py` compares them across every rounding boundary rather
    # than trusting the argument in the docstrings -- and the loop stays in the file as the statement of what "the same
    # bytes" means, which is a thing a vectorised rewrite can drift from silently.
    _flatten_ink_numpy(ink, red, green, blue, colour, width, height, layer.data)
    if relief is not None:
        layer.relief = relief
    return layer


def smudge(layer: 'Layer', points, radius: float = 16.0, strength: float = 0.55, reach: float = 0.9) -> 'Layer':
    """把颜色沿着一条路径拖过去 —— 湿画法在程序里的样子。

    **油画的相邻笔触不是硬边，因为底下那笔还是湿的。** 第二笔压上去时，两笔的颜料在笔毛的带动下拉到一起，
    边界因此是脏的、软的、有方向的。`blend` 做的是 source-over，边界由不透明度决定，所以它永远给出一条干净的接触线。

    这里做的不是「更软的边」，是一个动作：沿路径的每一点，把它**身后** `radius * reach` 处的颜色按一个柔和的权重
    混进当前这一圈。方向性是这个函数与高斯模糊的全部区别 —— 模糊把两边都拖开，抹开只把颜料往笔走的方向带。

    只混颜色，不动 alpha。颜料的透明度是它铺得多厚，而拖的动作不会改变已经铺下的量。
    """
    if _np is None:
        raise RuntimeError('smudge needs numpy')
    h, w = layer.height, layer.width
    pixels = _np.frombuffer(layer.data, dtype=_np.uint8).reshape(h, w, 4).astype(_np.float32)
    span = int(radius) + 2
    for i in range(1, len(points)):
        x0, y0 = float(points[i - 1][0]), float(points[i - 1][1])
        x1, y1 = float(points[i][0]), float(points[i][1])
        dx, dy = x1 - x0, y1 - y0
        length = float(_np.hypot(dx, dy))
        if length < 1e-6:
            continue
        ux, uy = dx / length, dy / length
        cx, cy = int(round(x1)), int(round(y1))
        ys = _np.arange(max(0, cy - span), min(h, cy + span + 1))
        xs = _np.arange(max(0, cx - span), min(w, cx + span + 1))
        if not xs.size or not ys.size:
            continue
        gx, gy = _np.meshgrid(xs.astype(_np.float64), ys.astype(_np.float64))
        distance = _np.hypot(gx - x1, gy - y1)
        weight = _np.clip(1.0 - distance / max(radius, 1e-6), 0.0, 1.0) ** 1.5 * strength
        if not weight.any():
            continue
        sx = _np.clip((gx - ux * radius * reach).astype(_np.int32), 0, w - 1)
        sy = _np.clip((gy - uy * radius * reach).astype(_np.int32), 0, h - 1)
        source = pixels[sy, sx]
        block = pixels[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1]
        block[:, :, :3] = (block[:, :, :3] * (1.0 - weight[:, :, None])
                           + source[:, :, :3] * weight[:, :, None])
    layer.data = bytearray(_np.clip(pixels, 0.0, 255.0).astype(_np.uint8).tobytes())
    return layer


def light(layer: 'Layer', direction=(-0.55, -0.62, 0.95), strength=0.9, tilt=2.2) -> 'Layer':
    """把颜料的高度读成侧光下的明暗。

    **厚度只有被光照过才存在。** 一层平的颜料叠多少遍都还是一层平的颜料；一堆有高低的颜料，光斜着来，
    突起朝光的一侧亮、背光的一侧暗，笔触的边缘因此自己显出轮廓 —— 这就是厚涂能被看见的全部机制。

    做法是把高度图的梯度当成分面法线（`tilt` 放大这个梯度，因为颜料的坡度比图像的比例尺陡得多），
    算一次朗伯项，再把结果乘到颜色上。乘而不是加，所以纯黑仍然是黑的，不会因为被照亮就变灰。

    没有高度图的层原样返回。线稿不需要这一层，而它在此之前也没有 —— 每一条既有渲染路径都走这个分支。
    """
    if getattr(layer, 'relief', None) is None:
        return layer
    gy, gx = _np.gradient(layer.relief)
    nx = -gx * tilt
    ny = -gy * tilt
    norm = _np.sqrt(nx * nx + ny * ny + 1.0)
    lx, ly, lz = direction
    length = float(_np.sqrt(lx * lx + ly * ly + lz * lz))
    lambert = (nx * lx + ny * ly + lz) / (norm * length)
    shade = 1.0 + strength * (lambert - lz / length)
    out = Layer(layer.width, layer.height)
    pixels = _np.frombuffer(bytes(layer.data), dtype=_np.uint8).reshape(layer.height, layer.width, 4)
    tinted = pixels.astype(_np.float64)
    tinted[:, :, :3] *= shade[:, :, None]
    out.data = bytearray(_np.clip(tinted, 0.0, 255.0).astype(_np.uint8).tobytes())
    out.relief = layer.relief
    return out


def save_png(layer: Layer, path: str, background: tuple[int, int, int] = (244, 241, 233)) -> None:
    """Writes the buffer out. Pillow is optional: without it the compositor still runs, it just cannot show you."""
    from PIL import Image
    image = Image.new('RGB', (layer.width, layer.height), background)
    pixels = image.load()
    for y in range(layer.height):
        row = y * layer.width * 4
        for x in range(layer.width):
            index = row + x * 4
            a = layer.data[index + 3] / 255.0
            if a <= 0:
                continue
            pixels[x, y] = (
                int(layer.data[index] * a + background[0] * (1 - a)),
                int(layer.data[index + 1] * a + background[1] * (1 - a)),
                int(layer.data[index + 2] * a + background[2] * (1 - a)),
            )
    # **Pillow writes the file, so it is handed the temporary name.** This is what a person looks at, and a
    # half-written PNG is what a viewer shows as a broken image rather than as an incomplete drawing.
    from .atomic import atomic_path
    temporary = atomic_path(path)
    # **`format` is given explicitly, because Pillow infers it from the extension and the temporary ends in
    # `.tmp`** -- left to infer it raises `unknown file extension: .tmp`, and the atomic write never happens. This
    # was found by running the test suite rather than by reading the code.
    image.save(temporary, format='PNG')
    os.replace(temporary, os.path.abspath(path))
