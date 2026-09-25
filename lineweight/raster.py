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

from .core import BRUSHES


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


class Layer:
    """One RGBA buffer. Straight alpha: the colour of a pixel is the colour it actually is."""

    def __init__(self, width: int, height: int, seed: int = 0) -> None:
        self.width = width
        self.height = height
        self.seed = seed
        # premultiplied would be faster to blend and harder to reason about; this keeps the colour meaningful when
        # alpha is low, which matters as soon as anybody looks at an intermediate buffer
        self.data = bytearray(width * height * 4)

    def dab(self, x: float, y: float, radius: float, colour: tuple[int, int, int], alpha: float,
            grain: float = 0.0) -> None:
        """One stamp: a radial falloff, which is what a brush tip is at this level of description."""
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
                if grain > 0:
                    # the tooth of the paper, sampled where the dab lands rather than by dab count
                    # **The absolute pixel, not an offset within this dab's own bounding box.** The first version
                    # sampled relative to x0/y0, which are the corners of the dab being stamped -- so the tooth was
                    # local to each dab and travelled with the brush, which is precisely what sampling by position
                    # was supposed to prevent. The property test caught it: the same line drawn in the opposite
                    # direction had its speckle in different places.
                    a *= 1.0 - grain * (1.0 - grain_at(px, py, self.seed))
                index = row + px * 4
                old_a = self.data[index + 3] / 255.0
                new_a = a + old_a * (1 - a)
                if new_a <= 0:
                    continue
                self.data[index] = int((r * a + self.data[index] * old_a * (1 - a)) / new_a)
                self.data[index + 1] = int((g * a + self.data[index + 1] * old_a * (1 - a)) / new_a)
                self.data[index + 2] = int((b * a + self.data[index + 2] * old_a * (1 - a)) / new_a)
                self.data[index + 3] = int(new_a * 255)


    def wet_dab(self, x: float, y: float, radius: float, colour: tuple[int, int, int], alpha: float,
                pickup: float, under: Layer | None = None, grain: float = 0.0) -> None:
        """A dab that first picks up what is already on the layer, then lays down the result.

        **This is the essence of wet mixing, and it is a lerp rather than a physics simulation.** A loaded brush
        crossing a wet wash carries some of that wash with it; the colour it deposits is part way between the paint it
        holds and the paint it found. Sampling the footprint's average and mixing by `pickup` reproduces the thing
        that makes watercolour read as watercolour -- the trail of colour a brush drags out of a shape it passes over
        -- without any of the neighbourhood iteration the tier was expected to need.

        Zero pickup is the dry dab exactly, so one code path covers both.
        """
        if pickup <= 0:
            self.dab(x, y, radius, colour, alpha, grain)
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
        self.dab(x, y, radius, mixed, alpha, grain)

def stroke_layer(record: dict, width: int, height: int, scale: float = 1.0,
                 wet: float = 0.0, under: Layer | None = None) -> Layer:
    """Rasterises a stroke record: dabs along the centre line, spaced by the brush, sized by the pressure.

    **This is the same data the vector expander uses**, which is the point of keeping a record rather than an
    outline: one stroke goes to SVG or to a buffer without being redrawn, and the two outputs cannot disagree about
    what was drawn.
    """
    brush = BRUSHES[record['brush']]
    colour = record.get('colour_int') or (26, 22, 32)
    layer = Layer(width, height)
    gamma = float(brush.get('curve', 1.0))
    centre = record['centre']
    pressure = record['pressure']
    # **Spacing is measured against the radius, not against the width times a factor.** The first version
    # multiplied the brush width by its spacing factor, which for a 22-pixel wash with a factor of 1.4 drew a
    # dab every 15 pixels -- a string of separate beads. A brush's spacing is how far apart its dabs sit
    # *relative to how big they are*: a tenth of the diameter is smooth, half the diameter is a texture.
    spacing = max(1.0, brush['width'] * brush.get('spacing', 0.7) * 0.5)
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
            radius = max(0.5, brush['width'] * (p ** gamma) * scale * 0.5)
            layer.wet_dab(x, y, radius, colour, min(1.0, brush['opacity'] * (p ** gamma)), wet, under,
                          float(brush.get('grain', 0.0)))
            travelled += max(1.0, radius * 2 * brush.get('spacing', 0.7)) * scale
        carry = travelled - segment
    return layer


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
    image.save(path)
