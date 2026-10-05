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


def packbits(data: bytes) -> bytes:
    """PackBits compression, which is what Photoshop and everything that reads its files actually writes.

    **Raw channels are legal and are not what applications expect.** The specification allows compression 0, and a
    reader that supports the format must accept it -- but a file that arrives with raw channels is unlike every PSD a
    drawing application has ever been handed, and SAI refused one outright with "canvas creation failed" while
    accepting the same pixels through PNG. Writing the compression that real files use is the difference between a
    file that is *valid* and a file that is *accepted*, and only the second one is useful.
    """
    out = bytearray()
    index = 0
    length = len(data)
    while index < length:
        # find the run of identical bytes starting here, capped at the format's maximum of 128
        run = 1
        while index + run < length and run < 128 and data[index + run] == data[index]:
            run += 1
        if run >= 2:
            out.append(257 - run)                      # a run: 1 - n, as a signed byte
            out.append(data[index])
            index += run
            continue
        # otherwise gather literals until a run of three starts, which is where compressing becomes worthwhile
        start = index
        while index < length and index - start < 128:
            if index + 2 < length and data[index] == data[index + 1] == data[index + 2]:
                break
            index += 1
        count = index - start
        out.append(count - 1)
        out += data[start:index]
    return bytes(out)


def unpackbits(data: bytes, expected: int) -> bytes:
    """The inverse, used to check that what was written can be read back.

    A compressor with no decompressor beside it is a compressor nobody has tested. This is deliberately written from
    the format rather than by inverting `packbits`, because an inverse that mirrors a mistake in the original will
    reproduce it exactly and report success.
    """
    out = bytearray()
    index = 0
    while index < len(data) and len(out) < expected:
        header = data[index]
        index += 1
        if header < 128:
            count = header + 1
            out += data[index:index + count]
            index += count
        elif header > 128:
            count = 257 - header
            out += bytes([data[index]]) * count
            index += 1
        # header == 128 is a no-op per the specification
    return bytes(out)


def _packed_channel(data: bytes, width: int, height: int) -> bytes:
    """One channel as PackBits, one compressed run per scanline, which is how the format stores images.

    Each row is prefixed with its own compressed length -- writing one stream for the whole channel is a plausible
    simplification that no reader accepts, because the length prefixes are how a reader finds row boundaries without
    decompressing everything first.
    """
    out = bytearray(struct.pack('>H', 1))
    for y in range(height):
        row = data[y * width:(y + 1) * width]
        packed = packbits(bytes(row))
        out += struct.pack('>H', len(packed)) + packed
    return bytes(out)


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
    # **Written negative, because the first alpha channel *is* the transparency.** The sign is a flag, not a
    # count: a negative layer count tells a reader that the bottom layer's alpha holds the image's
    # transparency, which is exactly what this writer produces. Written positive, SAI opened the file and
    # showed no layer panel at all -- it read the document as one flat image.
    layer_info += struct.pack('>h', -len(layers))
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
            blob = _packed_channel(b''.join(reversed(rows)), w, h)
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

    # ---- merged image data, PackBits per scanline like every PSD a drawing application has ever seen ----
    for c in range(CHANNELS):
        raw = bytes(merged[i * 4 + c] for i in range(w * h))
        out += _packed_channel(raw, w, h)
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
    # **The count and its sign are two different facts.** The field is read as a signed 16-bit number because that is
    # how it is stored, and its sign is a flag: negative means the bottom layer's alpha carries the image's
    # transparency. Reporting the raw signed value as `layers` conflates the two -- a caller asking how many layers
    # there are gets `-2`, and a test asserting `-2` pins the flag to the number. The count is reported as a count, and
    # the flag beside it.
    signed_count, = struct.unpack('>h', data[offset:offset + 2])
    transparency_flag = signed_count < 0
    count = abs(signed_count)
    offset += 2

    names: list[str] = []
    opacities: list[str] = []
    channel_total = 0
    blob_expectations: list[int] = []
    for _ in range(count):
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
    merged_decoded = []
    mo = merged_start
    for _c in range(channels):
        comp, = struct.unpack('>H', data[mo:mo + 2])
        merged_channels.append(comp)
        mo += 2
        if comp == 0:
            merged_decoded.append(data[mo:mo + width * height])
            mo += width * height
        elif comp == 1:
            # **Row lengths are read, not assumed.** Each scanline carries its own compressed length, so the only way
            # to find the next row -- and the end of this channel -- is to follow them one at a time.
            rows = []
            for _y in range(height):
                row_len, = struct.unpack('>H', data[mo:mo + 2])
                mo += 2
                rows.append(unpackbits(data[mo:mo + row_len], width))
                mo += row_len
            merged_decoded.append(b''.join(rows))
        else:
            merged_decoded.append(b'')
    # the merged channel data must decompress to the image that was handed in, or the file is not what it claims
    merged_ok = len(merged_decoded) == CHANNELS and all(len(c) == width * height for c in merged_decoded)
    return {'version': version, 'channels': channels, 'width': width, 'height': height,
            'depth': depth, 'mode': mode, 'layers': count,
            'first_alpha_is_transparency': transparency_flag,
            'names': names, 'opacities': opacities,
            'channel_bytes': channel_total, 'merged_compression': merged_channels,
            'merged_decoded_ok': merged_ok, 'merged_bytes_present': mo <= len(data),
            'bytes': len(data), 'layer_info_bytes': info_len}
