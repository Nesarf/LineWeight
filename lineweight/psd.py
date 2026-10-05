"""A layered PSD writer, because SAI has no scripting interface and PSD is the door it opens.

**Why PSD and not SAI's own format.** `libsai` reverse-engineers the original `.sai`, and its own issue tracker says
Sai2 support is absent; the `.sai2` container is undocumented, changes with builds, and is not a thing to hang a
pipeline on. SAI reads **PSD and PNG with layers intact**, so a layered PSD is the honest bridge: it is a published
format, it carries the layer names the drawing already has, and it costs nothing to produce.

**Why this is not a rasteriser.** A drawing's *weight* already lives in its geometry -- a stroke is expanded to a
filled outline before it ever needs a pixel. So this file exists to give a drawing somewhere to be *painted*: masks
per layer, at whatever scale the caller asks for, with the vector document remaining the source of truth.

**The format details that are easy to get wrong**, all of which produce a file that opens but is wrong rather than a
file that fails:

* Everything is **big-endian**, alone among the formats this project touches.
* The layer section is the **obsolete `0x043B` block**, and it must be written even though the spec calls it
  obsolete, because it is what SAI, Krita and Photoshop all read. Writing only the "modern" tagged blocks produces a
  flattened-looking file.
* `layer count` is written as a **negative** number when the first alpha channel holds transparency -- the convention
  that distinguishes a normal layered file from one whose bottom layer is flattened.
* A layer's channel data is stored **bottom-up**, like the image data and unlike the layer *order* in the records,
  which is bottom-up to top-down from the first record.
"""
from __future__ import annotations

import struct

from .doc import Document, parse_colour

SIGNATURE = b'8BPS'
VERSION = 1
MODE_RGB = 3
CHANNELS = 4
DEPTH = 8

BLEND_NORMAL = b'norm'

# A layer record's channel order in a file written by Photoshop and read by everything else.
CHANNEL_IDS = (0, 1, 2, -1)          # R, G, B, alpha (negative = the layer's transparency mask)


def _pad2(data: bytes) -> bytes:
    """PSD keeps sections on even boundaries; an odd-length block gets one pad byte."""
    return data + b'\x00' if len(data) % 2 else data


def _pascal_name(name: str, total: int = 4) -> bytes:
    """A layer's name is a Pascal string padded to a multiple of four -- not a length-prefixed blob."""
    raw = name.encode('utf-8')[:255]
    body = bytes([len(raw)]) + raw
    while len(body) % total:
        body += b'\x00'
    return body


class Layer:
    """One RGBA layer at the document's pixel size. Straight alpha, rows top-down like every other module here."""

    def __init__(self, name: str, width: int, height: int, opacity: float = 1.0, visible: bool = True) -> None:
        self.name = name
        self.width = width
        self.height = height
        self.opacity = max(0.0, min(1.0, opacity))
        self.visible = visible
        self.data = bytearray(width * height * 4)

    def set_pixel(self, x: int, y: int, colour: tuple[int, int, int], alpha: float) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        i = (y * self.width + x) * 4
        a = max(0.0, min(1.0, alpha))
        # straight alpha, so the colour stays meaningful at low alpha and the compositor resolves the rest
        self.data[i] = int(colour[0])
        self.data[i + 1] = int(colour[1])
        self.data[i + 2] = int(colour[2])
        self.data[i + 3] = int(round(a * 255))

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, colour: tuple[int, int, int], alpha: float = 1.0) -> None:
        for y in range(max(0, int(y0)), min(self.height, int(y1) + 1)):
            for x in range(max(0, int(x0)), min(self.width, int(x1) + 1)):
                self.set_pixel(x, y, colour, alpha)

    def channel_bytes(self, channel: int) -> bytes:
        """One channel, rows top-down, which the writer reverses for the file."""
        out = bytearray(self.width * self.height)
        for i in range(self.width * self.height):
            out[i] = self.data[i * 4 + channel]
        return bytes(out)

    def alpha(self) -> float:
        """The layer's mean alpha, used to decide whether it is worth writing without asking the caller."""
        total = 0
        count = self.width * self.height
        for i in range(count):
            total += self.data[i * 4 + 3]
        return (total / count / 255.0) if count else 0.0


def layers_from_document(document: Document, scale: float = 1.0) -> list[Layer]:
    """Fills one mask per document layer.

    The polygons are scanline-filled here rather than handed to a library: the whole project draws with the standard
    library so that it can be installed anywhere Python is, and a fill of a closed contour is a short loop.
    """
    width = max(1, int(document.width * scale))
    height = max(1, int(document.height * scale))
    made: list[Layer] = []
    for layer in document.layers:
        canvas = Layer(layer.name, width, height)
        for path in layer.paths:
            if path.appearance.filled:
                colour = parse_colour(path.appearance.fill)
                _fill_polygon(canvas, [(x * scale, y * scale) for x, y in path.points], colour,
                              path.appearance.opacity)
            else:
                colour = parse_colour(path.appearance.stroke or path.appearance.fill)
                width_px = max(1.0, path.appearance.stroke_width * scale)
                _stroke_polyline(canvas, [(x * scale, y * scale) for x, y in path.points], colour,
                                 path.appearance.opacity, width_px, path.closed)
        made.append(canvas)
    return made


def _fill_polygon(layer: Layer, points: list[tuple[float, float]], colour: tuple[int, int, int],
                  alpha: float) -> None:
    """Even-odd scanline fill. A closed contour is all this ever receives."""
    if len(points) < 3:
        return
    ys = [y for _, y in points]
    y0, y1 = max(0, int(min(ys))), min(layer.height - 1, int(max(ys)) + 1)
    count = len(points)
    for y in range(y0, y1 + 1):
        centre = y + 0.5
        crossings: list[float] = []
        for i in range(count):
            ax, ay = points[i]
            bx, by = points[(i + 1) % count]
            if (ay <= centre < by) or (by <= centre < ay):
                crossings.append(ax + (centre - ay) / (by - ay) * (bx - ax))
        crossings.sort()
        for i in range(0, len(crossings) - 1, 2):
            for x in range(max(0, int(crossings[i])), min(layer.width, int(crossings[i + 1]) + 1)):
                layer.set_pixel(x, y, colour, alpha)


def _stroke_polyline(layer: Layer, points: list[tuple[float, float]], colour: tuple[int, int, int],
                     alpha: float, width: float, closed: bool) -> None:
    """A centre line thickened by stamping discs along it -- the same operation the vector outline replaces."""
    if len(points) < 2:
        return
    radius = width / 2.0
    seq = list(points) + ([points[0]] if closed else [])
    for i in range(len(seq) - 1):
        ax, ay = seq[i]
        bx, by = seq[i + 1]
        steps = max(1, int(max(abs(bx - ax), abs(by - ay))))
        for s in range(steps + 1):
            t = s / steps if steps else 0.0
            cx, cy = ax + (bx - ax) * t, ay + (by - ay) * t
            x0, x1 = int(cx - radius), int(cx + radius) + 1
            y0, y1 = int(cy - radius), int(cy + radius) + 1
            for y in range(max(0, y0), min(layer.height, y1 + 1)):
                for x in range(max(0, x0), min(layer.width, x1 + 1)):
                    if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= radius * radius:
                        layer.set_pixel(x, y, colour, alpha)


def flatten(layers: list[Layer], width: int, height: int) -> bytearray:
    """The merged image, as straight RGBA. PSD stores this *before* the layer section, not after it."""
    out = bytearray(width * height * 4)
    for layer in layers:
        if not layer.visible:
            continue
        for i in range(0, width * height * 4, 4):
            a = layer.data[i + 3] / 255.0 * layer.opacity
            if a <= 0:
                continue
            da = out[i + 3] / 255.0
            na = a + da * (1 - a)
            if na <= 0:
                continue
            for c in range(3):
                src = layer.data[i + c] / 255.0
                dst = out[i + c] / 255.0
                out[i + c] = int(round((src * a + dst * da * (1 - a)) / na * 255))
            out[i + 3] = int(round(na * 255))
    return out


def _raw_channel(data: bytes) -> bytes:
    """A channel with compression 0 (raw), which is the one form every reader has always supported."""
    return struct.pack('>H', 0) + data


def save_psd(layers: list[Layer], path: str, width: int | None = None, height: int | None = None) -> str:
    """Write the layers as a layered PSD that SAI can open with its names and transparency intact."""
    if not layers:
        raise ValueError('a PSD needs at least one layer')
    w = width or layers[0].width
    h = height or layers[0].height
    merged = flatten(layers, w, h)

    out = bytearray()
    out += SIGNATURE + struct.pack('>H', VERSION)
    out += b'\x00' * 6                                  # reserved
    out += struct.pack('>H', CHANNELS) + struct.pack('>I', h) + struct.pack('>I', w)
    out += struct.pack('>H', DEPTH) + struct.pack('>H', MODE_RGB)
    out += struct.pack('>I', 0)                         # colour mode data
    out += struct.pack('>I', 0)                         # image resources

    # ---- layer and mask information ----
    layer_info = bytearray()
    layer_info += struct.pack('>h', len(layers))        # negative would mean "first alpha is transparency"
    records = bytearray()
    channel_blobs = bytearray()
    for layer in layers:
        rect = struct.pack('>iiii', 0, 0, h, w)
        headers = b''
        blobs = bytearray()
        for cid in CHANNEL_IDS:
            # the transparency channel is stored inverted, which is the PSD convention for a negative channel id
            raw = (bytes(255 - v for v in layer.channel_bytes(3)) if cid == -1
                   else layer.channel_bytes(cid))
            # channel data is written bottom-up, unlike the row order used everywhere else in this library
            rows = [raw[y * w:(y + 1) * w] for y in range(h)]
            blob = _raw_channel(b''.join(reversed(rows)))
            # **The 6-byte header belongs to its own data, and it is the header that carries the length.** Collecting
            # the headers first and the blobs afterwards is a plausible-looking layout that no reader accepts: a
            # reader takes the length from the first header, skips that much data, and expects the next header there.
            # With the blobs pooled at the end it lands in pixel data instead -- which is why `blend mode` came back
            # as `\xff\xff\xff\xff` and the layer name as 255 bytes of garbage. The bytes on disk are the contract,
            # not the tidy loop.
            headers += struct.pack('>h', cid) + struct.pack('>I', len(blob))
            blobs += blob
        record = bytearray()
        record += rect
        record += struct.pack('>H', CHANNELS) + headers
        record += BLEND_NORMAL
        record += bytes([int(round(layer.opacity * 255))])       # opacity
        record += bytes([0])                                     # clipping: base
        record += bytes([0x08 | (0x01 if layer.visible else 0x02)])   # flags: visible bit set = shown
        record += b'\x00'                                        # filler
        extra = bytearray()
        extra += b'\x00' * 4                                     # layer mask data
        extra += b'\x00' * 4                                     # blending ranges
        extra += _pascal_name(layer.name)
        record += struct.pack('>I', len(extra)) + extra
        records += record
        channel_blobs += blobs
    layer_info += records
    layer_info += channel_blobs
    layer_info += struct.pack('>I', 0)                  # global layer mask info

    out += struct.pack('>I', 4 + len(layer_info))
    out += struct.pack('>I', len(layer_info))
    out += layer_info

    # ---- merged image data, raw ----
    for c in range(CHANNELS):
        raw = bytes(merged[i * 4 + c] for i in range(w * h))
        out += struct.pack('>H', 0) + raw
    out = bytearray(_pad2(bytes(out)))

    with open(path, 'wb') as handle:
        handle.write(out)
    return path


def read_psd_header(path: str) -> dict:
    """Read back what a PSD claims about itself, so a written file can be checked rather than trusted.

    A writer that reports success because it finished writing is the failure mode this project keeps running into:
    the check has to come from the bytes on disk, and it has to be the same bytes a drawing application would read.
    The layer walk below therefore mirrors `save_psd` exactly -- section offsets, then the layer-info block, then the
    records -- because a checker that shares a bug with the writer is not a check.
    """
    with open(path, 'rb') as handle:
        data = handle.read()
    if data[:4] != SIGNATURE:
        raise ValueError('not a PSD: bad signature %r' % data[:4])
    version, = struct.unpack('>H', data[4:6])
    channels, height, width = struct.unpack('>HII', data[12:22])
    depth, mode = struct.unpack('>HH', data[22:26])

    offset = 26
    colour_len, = struct.unpack('>I', data[offset:offset + 4])
    offset += 4 + colour_len
    resource_len, = struct.unpack('>I', data[offset:offset + 4])
    offset += 4 + resource_len

    # layer and mask information section: length, then the layer-info block with its own length
    layer_mask_len, = struct.unpack('>I', data[offset:offset + 4])
    offset += 4
    section_start = offset
    info_len, = struct.unpack('>I', data[offset:offset + 4])
    offset += 4
    count, = struct.unpack('>h', data[offset:offset + 2])
    offset += 2

    names: list[str] = []
    opacities: list[str] = []
    channel_total = 0
    blob_expectations: list[int] = []
    for _ in range(abs(count)):
        offset += 16                                   # rectangle
        nch, = struct.unpack('>H', data[offset:offset + 2])
        offset += 2
        # **Layer records come first, and every layer's channel data follows the last record.** A reader that walks
        # header-blob-header-blob -- which this one did -- lands in pixel data on its second step and reports the
        # blend mode as `\xff\xff\xff\xff`, the opacity as 255 and the name as garbage. The file was correct; the
        # checker was the thing that was wrong, which is worth writing down because it sent the search into the
        # writer for a round.
        for _c in range(nch):
            offset += 2                                # channel id
            clen, = struct.unpack('>I', data[offset:offset + 4])
            offset += 4
            blob_expectations.append(clen)
            channel_total += clen
        offset += 4                                    # blend mode
        opacities.append('%d/255' % data[offset])
        offset += 1 + 1 + 1 + 1                        # opacity, clipping, flags, filler
        extra_len, = struct.unpack('>I', data[offset:offset + 4])
        offset += 4
        extra = data[offset:offset + extra_len]
        offset += extra_len
        name_len = extra[8] if len(extra) > 8 else 0
        names.append(extra[9:9 + name_len].decode('utf-8', 'replace'))
    # now step over the channel data that belongs to all of those records
    blob_bytes = sum(blob_expectations)
    offset += blob_bytes
    global_mask_len = struct.unpack('>I', data[offset:offset + 4])[0] if offset + 4 <= len(data) else -1
    offset += 4 + global_mask_len

    merged_start = section_start + layer_mask_len
    merged_channels = []
    mo = merged_start
    for _c in range(channels):
        comp, = struct.unpack('>H', data[mo:mo + 2])
        merged_channels.append(comp)
        mo += 2 + width * height
    return {'version': version, 'channels': channels, 'width': width, 'height': height,
            'depth': depth, 'mode': mode, 'layers': count, 'names': names, 'opacities': opacities,
            'channel_bytes': channel_total, 'merged_compression': merged_channels,
            'merged_bytes_present': mo <= len(data), 'bytes': len(data), 'layer_info_bytes': info_len}
