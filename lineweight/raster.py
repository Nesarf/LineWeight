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

from .core import BRUSHES, mark_ink
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
                 density: bool = False, width_scale: float = 1.0) -> Layer:
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
    brush = BRUSHES[record['brush']]
    colour = record.get('colour_int') or (26, 22, 32)
    layer = Layer(width, height, paper=paper)
    if density:
        layer.density = [0.0] * (width * height)
        # **The same sum without the alpha**, so the ratio is an average rather than a magnitude that depends on how
        # finely the path happened to be sampled.
        layer.density_ref = [0.0] * (width * height)
        layer.density_colour = colour
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
    widths = record.get('width_profile') or []
    alphas = record.get('alpha_profile') or []
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
            if widths:
                base = float(widths[min(i, len(widths) - 1)])
                radius = max(0.5, base * (p / median_pressure) * scale * 0.5 * width_scale)
            else:
                radius = max(0.5, brush['width'] * (p ** gamma) * scale * 0.5 * width_scale)
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


def blend(base: Layer, top: Layer, mode: str = 'normal', opacity: float = 1.0) -> Layer:
    """Combines two layers. Four modes, because four is what a drawing needs.

    `normal` paints over, `multiply` darkens (shadow, pencil), `screen` lightens (highlights, glow), and `overlay`
    does both according to what is underneath, which is the one that makes colour feel like paint rather than plastic.
    """
    if (base.width, base.height) != (top.width, top.height):
        raise ValueError('layers must be the same size: %sx%s vs %sx%s'
                         % (base.width, base.height, top.width, top.height))
    out = Layer(base.width, base.height)
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
    """
    if (layer.width, layer.height) != (mask.width, mask.height):
        raise ValueError('layer and mask must be the same size: %sx%s vs %sx%s'
                         % (layer.width, layer.height, mask.width, mask.height))
    out = Layer(layer.width, layer.height)
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
                 scale: float = 1.0, fill_rule: str = 'nonzero') -> None:
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
    if fill_rule not in ('nonzero', 'even-odd'):
        raise ValueError('unknown fill rule %r' % (fill_rule,))
    xs = [p[0] * scale for p in points]
    ys = [p[1] * scale for p in points]
    y0 = max(0, int(min(ys)))
    y1 = min(layer.height - 1, int(max(ys)) + 1)
    r, g, b = colour
    for py in range(y0, y1 + 1):
        yc = py + 0.5
        crossings: list[tuple[float, int]] = []
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
                index = row + px * 4
                old_a = layer.data[index + 3] / 255.0
                new_a = a + old_a * (1 - a)
                if new_a <= 0:
                    continue
                layer.data[index] = int((r * a + layer.data[index] * old_a * (1 - a)) / new_a)
                layer.data[index + 1] = int((g * a + layer.data[index + 1] * old_a * (1 - a)) / new_a)
                layer.data[index + 2] = int((b * a + layer.data[index + 2] * old_a * (1 - a)) / new_a)
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
    fill_polygon(layer, points, parse_hex(appearance.get('fill', '#808080')),
                 float(appearance.get('opacity', 1.0)), scale)
    return layer


#: **How far apart the dabs of an integrated stroke sit, as a fraction of the tip's diameter.** The maximum path
#: keeps each brush's own `spacing` because for it the spacing is a *texture* -- overlapping dabs simply do not
#: deepen, so their distance changes how the edge reads and nothing else. The density path has no such freedom: it
#: saturates wherever a dab covers, so the stroke's outline is the union of the tips and the spacing is the
#: scalloping of its edge. **2.5 percent is the figure Compositor publishes for soft tips**, which is where the
#: number comes from rather than from a sweep here -- and it is twenty times finer than the brush table's 56.
DENSITY_STEP = 0.025

#: **The width above which the deposition method is a question worth asking.** The ripple along a stroke is the same
#: fraction of its mean at every size -- 0.37 on the ink brush at four pixels and at eighty -- so what changes with
#: width is only whether it can be seen. Below this a stroke is a line and the two methods are the same picture; above
#: it a stroke is a shape and the maximum visibly beads. **It does not choose the method**: switching on it alone made
#: the pencil five times fainter, so the caller decides and this says where deciding matters.
WIDE_STROKE = 8.0


def render_marks(marks: list[dict], width: int, height: int, scale: float = 1.0,
                 paper: Paper | None = None, outlined: set | None = None,
                 outline_tint: float | None = None, outline_width: float | None = None) -> 'Layer':
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
                      'colour_int': parse_hex(mark_ink(mark))}
            # **Above `WIDE_STROKE` the deposition is integrated, below it the maximum is used.** The ripple along
            # a stroke is the same fraction of its mean at every width -- 0.37 on the ink brush at four pixels and at
            # eighty -- so what the width decides is only whether it can be seen. Measured after the normalisation
            # became a ratio of two sums, the peak agrees between the two methods on all four brushes (229/232,
            # 169/176, 243/245, 85/86) and the residual ripple on pencil and wash is their own paper grain.
            profile = record.get('width_profile') or []
            widest = max(profile) if profile else BRUSHES[record['brush']]['width']
            layer = stroke_layer(record, width, height, scale, paper=paper,
                                 density=widest >= WIDE_STROKE)
            if outlined and mark.get('layer') in outlined:
                # **The growth is stated in width units, and a stroke's width is its brush's**, so the scale is
                # relative to that rather than absolute -- a fine line and a wash both get the same line around them,
                # which is what the art does: the outline's width does not follow the fill's.
                brush_width = max(0.5, BRUSHES[record['brush']]['width'])
                grown = dict(record)
                grown['colour_int'] = outline_colour(record['colour_int'], tint)
                # **The outline takes the same deposition rule as the fill, and leaving it out is what kept the
                # beads after everything else was fixed.** It is drawn wider than the shape it surrounds, so it is
                # the outermost edge of the mark -- and on the maximum path, whose dabs do not deepen each other, a
                # wider tip means a wider spacing and therefore a scalloped rim standing proud of a smooth fill.
                # Measured on a bone: with the rule the left edge reverses direction 0 times over 66 rows, without
                # it 6 times, and the picture shows a wavy rim that survives every fix applied to the fill.
                behind = stroke_layer(grown, width, height, scale, paper=paper,
                                      density=widest >= WIDE_STROKE,
                                      width_scale=1.0 + 2.0 * line / brush_width)
                out = blend(out, behind, 'normal', 1.0)
        elif kind == 'fill':
            layer = fill_layer(mark, width, height, scale)
        else:
            raise ValueError('cannot render a mark of kind %r' % (kind,))
        out = blend(out, layer, 'normal', 1.0)
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
