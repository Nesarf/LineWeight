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


class Layer:
    """One RGBA buffer. Straight alpha: the colour of a pixel is the colour it actually is."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        # premultiplied would be faster to blend and harder to reason about; this keeps the colour meaningful when
        # alpha is low, which matters as soon as anybody looks at an intermediate buffer
        self.data = bytearray(width * height * 4)

    def dab(self, x: float, y: float, radius: float, colour: tuple[int, int, int], alpha: float) -> None:
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
                index = row + px * 4
                old_a = self.data[index + 3] / 255.0
                new_a = a + old_a * (1 - a)
                if new_a <= 0:
                    continue
                self.data[index] = int((r * a + self.data[index] * old_a * (1 - a)) / new_a)
                self.data[index + 1] = int((g * a + self.data[index + 1] * old_a * (1 - a)) / new_a)
                self.data[index + 2] = int((b * a + self.data[index + 2] * old_a * (1 - a)) / new_a)
                self.data[index + 3] = int(new_a * 255)


def stroke_layer(record: dict, width: int, height: int, scale: float = 1.0) -> Layer:
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
            layer.dab(x, y, radius, colour, min(1.0, brush['opacity'] * (p ** gamma)))
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
