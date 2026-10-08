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
* **Every layer record begins with the `8BIM` resource signature** before its blend mode. Two signatures in this format
  look alike and mean different things: `8BPS` opens a document, `8BIM` opens a resource. Writing the file-header one in
  a record makes a file whose layers no reader can find -- it opens, shows its canvas, and lists nothing.
* **The layer count is positive**, matching the file SAI writes itself. It was written negative for several rounds on the
  strength of an experiment whose reference file also carried the signature fault above, so the observation was
  contaminated. The sign is a real convention and the reader reports it as a flag; it is not what decides whether layers
  appear.
* **Each channel is a 2-byte compression tag, then a table of 2-byte row lengths for every row, then the rows.** Not
  one-byte lengths, and not a length immediately before each row. This was wrong for several rounds and the round trip
  passed anyway because the reader made the same two mistakes.
* **Rows are top-down**, the same order as everywhere else in this library. They were reversed here on a belief that
  layer channels are stored bottom-up; a PSD written by `psd-tools` with known colours in known quadrants decodes them
  exactly where they were placed, with no flip.
* **The alpha channel is written as it is**: 255 opaque, 0 transparent. It was written inverted, which turns every
  opaque pixel into zero -- a layer that displays as nothing while being listed correctly.

**The recurring lesson, stated here because this file has cost the most time in the project.** Each of those faults
survived because the reader in this module made the same mistake as the writer, so every round trip passed. A reader and
a writer that share a mistake validate each other perfectly. What finds these is an outside artifact: a file the target
application wrote itself, or an independent parser. `PSD-REPORT.md` has the full account.
"""
from __future__ import annotations

import struct

from .doc import Document, parse_colour
from .ref import ImageError

SIGNATURE = b'8BPS'                 # the file header's
VERSION = 1
MODE_RGB = 3
CHANNELS = 3                        # the merged image's: R, G, B. Layer records list their own.
DEPTH = 8

# **Two signatures that look alike and mean different things.** `8BPS` opens a document; `8BIM` opens an image
# resource, and a layer record carries one before its blend mode. Using the first where the second belongs produces a
# file that is structurally neat, opens in SAI, shows its canvas, reports no error, and has no layer panel -- because a
# reader scanning for records finds none and concludes the document is flat. That is exactly what happened here, and it
# survived several rounds of a round-trip test whose reader shared the writer's mistake.
SIGNATURE_RESOURCE = b'8BIM'
BLEND_NORMAL = b'norm'

# A layer record's channel order in a file written by Photoshop and read by everything else.
# **The order is the order SAI 1 writes, which is not the order this used to use.** Its own layered file lists
# the transparency channel first and then the colours; writing them the other way round produced a file whose
# records parse and whose layers a reader can name, and which no channel of ink ever reached the canvas from.
# Matching the application that has to open the file is the requirement.
# **The fifth channel is a user mask, and it is written all-white.** `psd-tools`' own writer emits `-1, 0, 1, 2, -2`
# for a layer, and this wrote the first four only. The `-2` is the layer's user mask; white means "no mask", so it
# masks nothing and costs a channel. It is written because matching the encoder whose output is known to read back
# correctly is worth more than the byte it saves -- and a reader that expects the channel list to match its own
# convention is exactly the kind of reader this file has been failing.
CHANNEL_IDS = (-1, 0, 1, 2, -2)      # transparency, R, G, B, user mask


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
        # **Everything is white and nothing is opaque.** A layer starts as a sheet of white paper with the alpha channel
        # at zero, and drawing puts colour where the alpha then says there is something. Zeroing the whole buffer
        # instead -- which is what this did -- gives a transparent layer whose colour channels are *black*, and a
        # consumer that composites a layer as "colour, masked by alpha" paints the entire canvas black: the drawing is
        # then on top of that in near-black and cannot be seen at all. That is what SAI showed, with the layer names
        # correctly listed beside a blank canvas.
        #
        # SAI's own picture layer settles it: 96096 pixels of pure white at alpha zero, and the stroke in black at
        # alpha 255. White is what its transparent areas hold, and its alpha is nearly eight times its ink coverage,
        # because the shape is carried by the alpha rather than by the colour.
        self.data = bytearray(width * height * 4)
        for i in range(0, len(self.data), 4):
            self.data[i] = self.data[i + 1] = self.data[i + 2] = 255

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
        """One channel, rows top-down, which the writer reverses for the file.

        **A channel id of -1 means the alpha channel, and it is translated rather than indexed.** Writing
        `self.data[i * 4 + channel]` looked as though Python's negative indexing took care of it, and it does not:
        `i * 4 + (-1)` is `i * 4 - 1`, which for every pixel after the first is the *previous* pixel's blue byte. The
        alpha channel was therefore filled with the blue channel's values shifted by one pixel -- and at zero for the
        first pixel only. That is a layer whose transparency is derived from the wrong data entirely, which reads as a
        blank or black canvas while the layers are listed correctly beside it.
        """
        if channel == -1:
            channel = 3
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


def flatten(layers: list[Layer], width: int, height: int, background: int = 255) -> bytearray:
    """The merged image, composited onto an opaque background -- which is what a PSD's merged section is.

    **The merged section is not the layer stack, and it is not allowed to be transparent.** It is what a viewer that
    ignores layers puts on screen, and its channel count is the file header's, which for RGB is three. This function
    used to start from zeroes and leave the untouched pixels at `(0, 0, 0, 0)`: a merged image whose background is
    transparent black. On a viewer that treats it as opaque -- which is what three channels of RGB *means* -- that is a
    black canvas, and the drawing is invisible however correct the layers are.

    Compositing onto white is a choice, and the honest statement of it is that a PSD has no alpha channel in its merged
    data to be transparent with. Callers that want a different paper colour can pass one.
    """
    out = bytearray(width * height * 4)
    for i in range(0, width * height * 4, 4):
        out[i] = out[i + 1] = out[i + 2] = background
        out[i + 3] = 255
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
            if index >= len(data):
                # **A run whose value byte is missing ends the stream instead of raising.** Truncated input reaches
                # here whenever a caller's offsets are off, and an IndexError from deep inside a decoder says nothing
                # about which field was wrong; stopping says the stream ended, which is the fact that helps.
                break
            out += bytes([data[index]]) * count
            index += 1
        # header == 128 is a no-op per the specification
    return bytes(out)


def _packed_channel(data: bytes, width: int, height: int) -> bytes:
    """One channel as PackBits: a **table of two-byte row lengths**, and then all the rows.

    **Both of those were wrong here for several rounds, and reading the decoder that actually works settled it.** A
    reference file -- a SAI PSD containing a real drawing -- decodes perfectly through `psd-tools`, and its `decode_rle`
    states the layout plainly::

        row_size = (width * depth + 7) // 8
        bytes_counts = read_be_array(("H", "I")[version - 1], height, fp)   # every count, first
        return b"".join(decode(fp.read(count), row_size) for count in bytes_counts)

    * **The counts are two bytes each** for version 1, not one. A single byte shifts every row boundary, so the first
      row decodes and nothing after it does -- exactly the symptom that was being chased for several rounds.
    * **All the counts come before any row data.** Writing each row's length immediately before that row is the obvious
      layout, and it is not this format.

    Measured against the reference: the counts sum to precisely the bytes following the table (253104 of 253104) and the
    rows expand to precisely the channel size (1662661 of 1662661).
    """
    counts = bytearray()
    rows = bytearray()
    for y in range(height):
        packed = packbits(bytes(data[y * width:(y + 1) * width]))
        counts += struct.pack('>H', len(packed))
        rows += packed
    return bytes(struct.pack('>H', 1) + counts + rows)


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
    # **The resolution resource, because it is the one block SAI's own files always carry.** A PSD with no image
    # resources is legal and this wrote one for a while; SAI's own 512x512 document writes 58 bytes here, of which this
    # is the useful part -- resource 1005, the resolution, as two 32-bit fixed-point values. Whether SAI needs it is not
    # established, and it is written because matching the application that has to open the file is the whole
    # requirement, not minimality.
    # **The name field is a Pascal string padded to an even length, so an empty one is two bytes.** A zero length byte
    # on its own is odd and takes a pad byte with it; this wrote a single zero, which made the block three bytes
    # shorter than a reader walking it expected and shifted every following field by three. SAI's file carries the same
    # resource and its name field is two bytes wide.
    resolution = bytearray(SIGNATURE_RESOURCE + struct.pack('>H', 1005) + b'\x00\x00')   # id, empty name + pad
    # **Sixteen bytes of data: six fields, not four.** The resolution resource is horizontal resolution and its unit,
    # the unit the document's *width* is measured in, vertical resolution and its unit, then the unit for the height --
    # `I 2H I 2H`. This wrote only the four obvious ones, twelve bytes, and announced twelve, so the block was
    # internally consistent and four fields short of the format; `psd-tools` refused it with "read=12, expected=16".
    # SAI writes all sixteen, which is where the number in its file came from and what was mistaken for padding.
    resolution += struct.pack('>I', 16)
    resolution += struct.pack('>I', 72 << 16) + struct.pack('>H', 1)   # horizontal dpi, unit 1 = inches
    resolution += struct.pack('>H', 1)                                 # width unit
    resolution += struct.pack('>I', 72 << 16) + struct.pack('>H', 1)   # vertical dpi, unit
    resolution += struct.pack('>H', 1)                                 # height unit
    out += struct.pack('>I', len(resolution))
    out += resolution

    # ---- layer and mask information ----
    layer_info = bytearray()
    # **Written positive, matching the file SAI writes itself.** This was negative for several rounds, on the strength
    # of an experiment where a positive count appeared to produce an empty layer panel -- but that file also carried the
    # broken layer-record signature fixed below, so the observation was contaminated and the conclusion drawn from it
    # was wrong. SAI's own 512x512 document writes `+2`. The sign is a real convention and the reader still reports it;
    # what it is not is the thing that decides whether layers appear.
    layer_info += struct.pack('>h', len(layers))
    records = bytearray()
    channel_blobs = bytearray()
    for layer in layers:
        rect = struct.pack('>iiii', 0, 0, h, w)
        headers = b''
        blobs = bytearray()
        for cid in CHANNEL_IDS:
            # **The alpha channel is written as it is: 255 for opaque, 0 for transparent.** This wrote
            # `255 - alpha`, which turns every opaque pixel into zero and every transparent one into 255 -- the layer
            # comes out entirely inverted, so a consumer displays nothing while the layer is listed correctly beside
            # the blank canvas. The evidence is SAI's own layer, read by `psd-tools`: `min 0.000 max 1.000 mean
            # 0.20592`, with ink *high* where the stroke is. Zero is transparent and 255 is drawn, which is also what
            # the in-memory buffer holds.
            #
            # The inversion had been justified by a comment claiming the format stores it inverted. That is not
            # established, and the measurement says the opposite. `PSD-REPORT.md` had already recorded it as unproven
            # while the code treated it as settled -- the divergence was the signal.
            raw = (bytes([255]) * (w * h) if cid == -2        # an all-white user mask masks nothing
                   else layer.channel_bytes(-1))
            # **Rows are written top-down, the same order as everywhere else in this library.**
            #
            # This reversed them, on the belief that layer channel data is stored bottom-up. It is not, and the
            # evidence is a PSD written by `psd-tools` -- an encoder that is known to work -- with red, green, blue and
            # yellow placed in four known quadrants. Decoding its channels back gives channel 0 high at top-left and
            # bottom-right, channel 1 high at top-right and bottom-right, channel 2 high at bottom-left: the colours
            # where they were put, with no flip.
            #
            # The earlier evidence for reversing was an experiment that drew a bar near the top and found it near the
            # bottom of the file -- but the file was read back with the same decoding assumption the writer used, so
            # the two agreed and neither was checked against anything. The same trap as the row count and the record
            # signature, met a third time.
            rows = [raw[y * w:(y + 1) * w] for y in range(h)]
            blob = _packed_channel(b''.join(rows), w, h)
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
        record += struct.pack('>H', len(CHANNEL_IDS)) + headers
        # **The signature is not decoration -- it is how a reader finds the record.** A layer record carries an
        # eight-byte block: the `8BIM` signature and then the blend mode. This wrote the four-byte blend mode alone,
        # and the consequence was not a wrong blend mode but *no layers at all*: SAI opens such a file, shows its
        # canvas, reports nothing, and presents an empty layer panel, because a reader that scans for `8BIM` finds no
        # records and concludes the document is flat.
        #
        # Nothing here caught it for several rounds, and the reason is worth keeping: `read_psd_header` is this
        # module's own reader, and it skipped the signature field too. A reader and a writer that agree on the same
        # mistake validate each other perfectly. What found it was diffing against a file SAI wrote itself.
        record += SIGNATURE_RESOURCE + BLEND_NORMAL
        record += bytes([int(round(layer.opacity * 255))])       # opacity
        record += bytes([0])                                     # clipping: base
        # SAI writes zero here for a normal, visible layer. 0x09 was this project's own guess at "visible", and a
        # guess in a field a reader interprets is a risk taken for no benefit.
        record += bytes([0x00])                                  # flags, as SAI writes them
        record += b'\x00'                                        # filler
        extra = bytearray()
        extra += b'\x00' * 4                                     # layer mask data: length 0, "no mask"
        # **Eight bytes of blending ranges per channel, not zero.** A zero-length block is legal and means "no
        # restricted ranges", and this wrote one. `psd-tools` -- whose output is the one known to read back correctly
        # -- writes `8 x channels` zero bytes and declares that length. The whole approach here is to match the encoder
        # that works rather than to argue from the specification, so that is what this writes now.
        extra += struct.pack('>I', 8 * len(CHANNEL_IDS)) + b'\x00' * (8 * len(CHANNEL_IDS))
        extra += _pascal_name(layer.name)
        # **The Unicode name too.** SAI writes a `luni` block holding the name as UTF-16, and so does every file this
        # project has compared against; the Pascal string above is the legacy form that predates it. A reader that
        # wants a name for a layer whose name is not Latin-1 has only the `luni` block to read it from.
        unicode_name = layer.name.encode('utf-16-be')
        extra += SIGNATURE_RESOURCE + b'luni' + struct.pack('>I', 4 + len(unicode_name))
        extra += struct.pack('>I', len(layer.name)) + unicode_name
        if (4 + len(unicode_name)) % 2:
            extra += b'\x00'                                     # resource blocks are padded to even
        record += struct.pack('>I', len(extra)) + extra
        records += record
        channel_blobs += blobs
    layer_info += records
    layer_info += channel_blobs

    # **The global mask is its own field, not part of the layer info.** It sat inside `layer_info`, so its four bytes
    # were counted in the layer info length -- a section that announced four bytes more than it held. A reader that
    # trusts the length walks past the end of the data it was promised, and `psd-tools` refused the whole file with
    # "Invalid data section size" because of it.
    out += struct.pack('>I', 4 + len(layer_info) + 4)   # the layer and mask section
    out += struct.pack('>I', len(layer_info))           # the layer info block within it
    out += layer_info
    out += struct.pack('>I', 0)                         # global layer mask info: empty

    # ---- merged image data, PackBits per scanline like every PSD a drawing application has ever seen ----
    for c in range(3):                              # RGB; an alpha channel here is read as data and rejected
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
        # header-blob-header-blob lands in pixel data on its second step and reports the blend mode as
        # `\xff\xff\xff\xff`. That misread sent the search into the writer for a round, and the writer turned out to
        # have a real defect as well -- see the signature check below.
        for _c in range(nch):
            offset += 2                                # channel id
            clen, = struct.unpack('>I', data[offset:offset + 4])
            offset += 4
            blob_expectations.append(clen)
            channel_total += clen
        # **Eight bytes: the signature and then the blend mode.** Skipping four was this reader agreeing with a writer
        # that wrote four, which is why neither noticed. The result was a file whose layer records began with the bare
        # string `norm` where a reader looks for `8BIM` -- SAI opened it with an empty layer panel. The signature is
        # read rather than skipped now, so the two cannot drift apart again without a test failing.
        if data[offset:offset + 4] != SIGNATURE_RESOURCE:
            raise ImageError('layer record %d has no 8BIM signature: %r'
                             % (len(opacities), data[offset:offset + 4]))
        offset += 4                                    # 8BIM
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
            # **A table of two-byte row lengths, then every row.** Both halves were wrong here and in the writer, and
            # they agreed with each other, which is why the round trip passed while the file was unreadable elsewhere.
            # The layout is not a guess: `psd-tools` decodes a real SAI drawing with exactly this shape, and reading
            # that decoder is what ended several rounds of inferring the format from bytes.
            counts = []
            for _y in range(height):
                counts.append(struct.unpack('>H', data[mo:mo + 2])[0])
                mo += 2
            rows = []
            for row_len in counts:
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
