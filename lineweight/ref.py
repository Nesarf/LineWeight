"""Measuring real linework, so the pressure model is fitted to art instead of to taste.

**Why a library of images and not a curve editor.** The four effects in `pressures()` have numbers attached to them --
how much a fast stroke lightens, how long a taper is, how much a corner thins -- and picking those by eye produces
linework that pleases whoever picked them and matches nobody. A real drawing contains the answer: the width
distribution of its lines, how much ink sits on the page, how long its thin ends are. That is what `--fit` was always
supposed to compare against, and this module is the part that turns a folder of artwork into those numbers.

**Why PNG is decoded here rather than with a library.** The rest of this project draws with the standard library so it
can be installed wherever Python is, and the same reasoning applies to reading: a PNG is a zlib stream of filtered
scanlines, which is arithmetic, not an imaging engine. JPEG genuinely is a codec and is not implemented -- if Pillow
is present it is used for those, and if it is not, the file is skipped and counted rather than silently dropped.

**What the numbers are for.** `widths` is the distribution a brush's curves have to reproduce; `taper` is how much of
a stroke's length is spent thinning at its ends, which is the direct measurement of `taper_in`/`taper_out`; `ink` is
the overall weight, which is what opacity has to average out to. A drawing measured here can be compared with a
generated sheet measured the same way, and the gap between them is the calibration error -- a number, not an opinion.
"""
from __future__ import annotations

import json
import math
import os
import struct
import zlib
from dataclasses import asdict, dataclass, field

# A pixel darker than this counts as ink. 128 is the midpoint of 8-bit grey and is what `fit_report` already used, so
# measurements from the two paths are comparable -- changing it here would silently make old numbers mean something
# else.
INK_THRESHOLD = 128

# The widest run still counted as a line. Above this a run of ink is a filled region -- hair, clothing, a shadow --
# and mixing those into the width distribution produces a mean that describes no line in the drawing.
MAX_LINE_WIDTH = 16

# Below this many line-like runs a picture cannot be fitted against, however dark it is. Kept explicit so a library
# entry that contributes nothing is excluded by a rule rather than by somebody noticing it looked odd.
MIN_LINE_RUNS = 200

# A width that repeats at least this many times is a filled region rather than a stroke. A 40-pixel-wide block yields
# one run per scanline it spans, so its width shows up dozens of times, while a drawn line gives a handful.
REPEAT_FLOOR = 12


class ImageError(Exception):
    """Raised for an image this module cannot read, naming the file so a skip is never silent."""


@dataclass
class Rgb:
    """A decoded image as three bytes per pixel, rows top-down.

    **Kept as a second model rather than replacing `Greyscale`, because every measurement in this file is about
    geometry** -- run widths, taper, coverage -- and geometry is a property of luminance. The colour model exists for
    one question the rest of the file cannot ask, which is what ink a drawing is actually made of.
    """
    width: int
    height: int
    pixels: bytearray

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        i = (y * self.width + x) * 3
        return self.pixels[i], self.pixels[i + 1], self.pixels[i + 2]


@dataclass
class Greyscale:
    """A decoded image as one byte of grey per pixel, rows top-down."""
    width: int
    height: int
    pixels: bytearray

    def line_widths(self, threshold: int = INK_THRESHOLD, axis: str = 'x') -> list[int]:
        """Lengths of the runs of ink found along one axis.

        A run is a maximal consecutive stretch of dark pixels, which is the only width a flat drawing can offer: the
        *appearance* of the line rather than the pressure that made it. Scanning both axes matters because a drawing
        is mostly lines in one direction, and measuring only one of them measures only the lines that happen to cross
        it.

        **Written to walk indices rather than to slice.** The obvious version takes a row with
        `pixels[y*w:(y+1)*w]`, which copies every pixel of the image once per axis -- on a four-megapixel illustration
        that is sixteen megabytes of copying to count runs, and it was most of the time a full library took to
        measure. The step form is the same loop with no copy.
        """
        runs: list[int] = []
        if axis == 'x':
            for y in range(self.height):
                base = y * self.width
                length = 0
                for x in range(self.width):
                    if self.pixels[base + x] < threshold:
                        length += 1
                    elif length:
                        runs.append(length)
                        length = 0
                if length:
                    runs.append(length)
        else:
            for x in range(self.width):
                length = 0
                index = x
                for _y in range(self.height):
                    if self.pixels[index] < threshold:
                        length += 1
                    elif length:
                        runs.append(length)
                        length = 0
                    index += self.width
                if length:
                    runs.append(length)
        return runs

    def ink_stats(self, threshold: int = INK_THRESHOLD) -> tuple[float, float]:
        """Ink fraction and mean darkness in one pass, because they are read from the same pixels.

        Two separate passes over every pixel was the shape this started as, and with three such helpers the cost of a
        measurement grew with the number of questions asked rather than with the size of the image.
        """
        dark = 0
        total_darkness = 0
        count = len(self.pixels)
        for value in self.pixels:
            if value < threshold:
                dark += 1
                total_darkness += 255 - value
        return (dark / count if count else 0.0,
                (total_darkness / dark) if dark else 0.0)

    def mean_darkness(self, threshold: int = INK_THRESHOLD) -> float:
        return self.ink_stats(threshold)[1]

    def ink_ratio(self, threshold: int = INK_THRESHOLD) -> float:
        return self.ink_stats(threshold)[0]


def _runs(sequence, threshold: int) -> list[int]:
    runs: list[int] = []
    length = 0
    for value in sequence:
        if value < threshold:
            length += 1
        elif length:
            runs.append(length)
            length = 0
    if length:
        runs.append(length)
    return runs


# ---------------------------------------------------------------- decoding

def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(path: str, rgb: bool = False):
    """A PNG as greyscale, by undoing the filters and reducing to luminance.

    `rgb=True` keeps the three colour channels instead. **One filter loop, two reductions**, rather than a second
    decoder: the filters are the part that is fiddly and the part that is worth having exactly one of, and a copy of
    them kept for colour would be a copy that could disagree with this one about what the file says.

    The filter step is the part that is easy to skip and wrong to skip: every scanline declares which of five
    predictors was applied to it, and reading the bytes without undoing that produces an image that is not merely
    off by a little -- it accumulates across the row, so the right-hand side of the picture is noise.
    """
    with open(path, 'rb') as handle:
        data = handle.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ImageError('not a PNG: %s' % path)

    pos = 8
    width = height = depth = colour = interlace = 0
    palette: list[tuple[int, int, int]] = []
    idat = bytearray()
    while pos + 8 <= len(data):
        length, = struct.unpack('>I', data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b'IHDR':
            width, height, depth, colour, _comp, _filt, interlace = struct.unpack('>IIBBBBB', body[:13])
        elif kind == b'PLTE':
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body) - 2, 3)]
        elif kind == b'IDAT':
            idat += body
        elif kind == b'IEND':
            break
    if not width or not height:
        raise ImageError('PNG has no header: %s' % path)
    if interlace:
        raise ImageError('interlaced PNG is not supported: %s' % path)
    if depth not in (8,):
        raise ImageError('PNG bit depth %d is not supported: %s' % (depth, path))

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    if channels is None:
        raise ImageError('PNG colour type %d is not supported: %s' % (colour, path))

    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    step = 3 if rgb else 1
    out = bytearray(width * height * step)
    prior = bytearray(stride)
    offset = 0
    for y in range(height):
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        if filter_type == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + prior[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prior[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            # **The predictor is inlined.** `_paeth` is three subtractions and three comparisons, and calling it once
            # per byte of a four-megapixel image costs more than the arithmetic inside it -- the decoder was most of
            # the time a full library took to measure, while the measuring itself ran in under half a second.
            for i in range(stride):
                if i >= channels:
                    a = line[i - channels]
                    b = prior[i]
                    c = prior[i - channels]
                else:
                    a = 0
                    b = prior[i]
                    c = 0
                p = a + b - c
                pa = p - a
                if pa < 0:
                    pa = -pa
                pb = p - b
                if pb < 0:
                    pb = -pb
                pc = p - c
                if pc < 0:
                    pc = -pc
                if pa <= pb and pa <= pc:
                    pred = a
                elif pb <= pc:
                    pred = b
                else:
                    pred = c
                line[i] = (line[i] + pred) & 0xFF
        elif filter_type != 0:
            raise ImageError('unknown PNG filter %d in %s' % (filter_type, path))
        prior = line
        base = y * width * step
        if rgb:
            _row_rgb(out, base, line, width, colour, palette)
        elif colour == 0:                                # grey, one byte a pixel
            out[base:base + width] = line[:width]
        elif colour == 4:                                # grey plus alpha
            out[base:base + width] = line[0::2]
        elif colour == 2:                                # RGB, the recursion kept out of the inner loop
            for x in range(width):
                i = x * 3
                out[base + x] = (line[i] * 299 + line[i + 1] * 587 + line[i + 2] * 114) // 1000
        elif colour == 6:                                # RGBA
            for x in range(width):
                i = x * 4
                out[base + x] = (line[i] * 299 + line[i + 1] * 587 + line[i + 2] * 114) // 1000
        else:                                            # palette: resolved once, not per pixel
            table = bytearray(256)
            for index in range(256):
                if index < len(palette):
                    r, g, b = palette[index]
                    table[index] = (r * 299 + g * 587 + b * 114) // 1000
                else:
                    table[index] = 255
            for x in range(width):
                out[base + x] = table[line[x]]
    if rgb:
        return Rgb(width=width, height=height, pixels=out)
    return Greyscale(width=width, height=height, pixels=out)


def _row_rgb(out: bytearray, base: int, line: bytearray, width: int, colour: int, palette) -> None:
    """Writes one unfiltered scanline as RGB. The reduction the greyscale path does not do.

    `colour == 2` is a straight copy because the row is already RGB, which is the case every camera and every
    screenshot produces and therefore the case worth having fast.
    """
    if colour == 2:
        out[base:base + width * 3] = line[:width * 3]
        return
    for x in range(width):
        j = base + x * 3
        if colour == 6:
            i = x * 4
            out[j], out[j + 1], out[j + 2] = line[i], line[i + 1], line[i + 2]
        elif colour == 0:
            value = line[x]
            out[j], out[j + 1], out[j + 2] = value, value, value
        elif colour == 4:
            value = line[x * 2]
            out[j], out[j + 1], out[j + 2] = value, value, value
        else:
            index = line[x]
            r, g, b = palette[index] if index < len(palette) else (255, 255, 255)
            out[j], out[j + 1], out[j + 2] = r, g, b


def load_greyscale(path: str) -> Greyscale:
    """Whatever the file is, as greyscale: PNG by hand, anything else through Pillow when it is available."""
    extension = os.path.splitext(path)[1].lower()
    if extension == '.png':
        return decode_png(path)
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageError('no decoder for %s without Pillow' % extension) from exc
    with Image.open(path) as image:
        grey = image.convert('L')
        return Greyscale(width=grey.width, height=grey.height, pixels=bytearray(grey.tobytes()))


def load_rgb(path: str) -> Rgb:
    """Whatever the file is, in colour: PNG by hand, anything else through Pillow when it is available.

    The counterpart of `load_greyscale`, and it exists because **the rest of this file throws colour away**. Every
    measurement in it is about geometry, and geometry is a property of luminance, so reducing to grey was right for
    all of them -- and it left the library unable to answer the one question about ink that the drawing convention
    turns out to have a measured answer for.
    """
    extension = os.path.splitext(path)[1].lower()
    if extension == '.png':
        return decode_png(path, rgb=True)
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageError('no decoder for %s without Pillow' % extension) from exc
    with Image.open(path) as image:
        rgb = image.convert('RGB')
        return Rgb(width=rgb.width, height=rgb.height, pixels=bytearray(rgb.tobytes()))


# How far below its own paper a pixel has to sit to count as ink. **Relative to the paper, not absolute.** The first
# version of this used the module's `INK_THRESHOLD` of 128 and reported a 20-second frame of clean line art as
# `median 119,108,113` -- a mixture of the line art, a grey watermark and the frame border, because that line art is a
# *light* dusty rose whose core sits well above 128. A threshold calibrated for dark ink is the wrong instrument for
# light ink, and the drawing convention has plenty of both.
PAPER_MARGIN = 12
# Above this, a pixel has a hue that can be measured. Below it, the pixel is grey and its colour is an artefact of
# whatever it was mixed with.
CHROMA_FLOOR = 0.10
# Each edge ignored, as a fraction of that dimension: screen recordings carry frame borders and watermarks, and a
# border is not ink.
BORDER_CROP = 0.02


@dataclass
class InkColour:
    """The colour of a drawing's ink, **and how much of the ink had a colour at all.**

    **The second number is not a detail.** A drawing whose lines are black has no ink colour to report, and the honest
    answer is to say so rather than to return the median of a pile of grey pixels -- which is what the first version
    did, and it is how "the ink is warm, R-B +10" came to be recorded for a frame whose lines are a red-brown at
    R-B +39 alongside a grey watermark and a grey border that shared its median.
    """
    paper: int
    ink: int
    coloured: int
    median: tuple[int, int, int]          # over the pixels that have a hue

    @property
    def hue_fraction(self) -> float:
        return self.coloured / float(self.ink) if self.ink else 0.0

    @property
    def warmth(self) -> int:
        return self.median[0] - self.median[2]

    @property
    def chroma(self) -> float:
        return (max(self.median) - min(self.median)) / 255.0

    def verdict(self) -> str:
        """**What the measurement is entitled to say.** Stated as a sentence so it cannot be quoted as a number
        without its condition."""
        if self.coloured < 200 or self.hue_fraction < 0.05:
            return ('the ink is hueless: only %d of %d ink pixels have a measurable hue, so there is no ink colour '
                    'here to report' % (self.coloured, self.ink))
        return ('ink has a hue: %d of %d ink pixels (%.0f%%) are coloured, median %d,%d,%d, R-B %+d, chroma %.3f'
                % (self.coloured, self.ink, 100.0 * self.hue_fraction, self.median[0], self.median[1],
                   self.median[2], self.warmth, self.chroma))

    def line(self) -> str:
        return ('paper %3d | ink %7d px | coloured %7d (%4.1f%%) | median %3d,%3d,%3d | R-B %+3d | chroma %.3f'
                % (self.paper, self.ink, self.coloured, 100.0 * self.hue_fraction, self.median[0], self.median[1],
                   self.median[2], self.warmth, self.chroma))


def measure_ink_colour(image: Rgb, margin: int = PAPER_MARGIN, border: float = BORDER_CROP) -> InkColour:
    """The colour of a drawing's ink, relative to that drawing's own paper and over **every** pixel rather than a
    sample of them.

    No subsampling: ink is a small fraction of a drawing's pixels, the interesting case is a colour only slightly off
    neutral, and a sample is the wrong instrument for a small effect on a small subset. One pass in Python, about a
    second on a 1.6-megapixel frame.
    """
    pixels = image.pixels
    width, height = image.width, image.height
    x0, x1 = int(width * border), width - int(width * border)
    y0, y1 = int(height * border), height - int(height * border)

    # The paper is the bright end of the image, taken as a high percentile rather than the maximum so that a white
    # watermark or a blown highlight does not drag it up.
    histogram = [0] * 256
    for y in range(y0, y1):
        base = y * width * 3
        for x in range(x0, x1):
            i = base + x * 3
            histogram[(pixels[i] * 299 + pixels[i + 1] * 587 + pixels[i + 2] * 114) // 1000] += 1
    seen = total = 0
    for level in range(255, -1, -1):
        seen += histogram[level]
        total += histogram[level]
    target = sum(histogram) * 0.75
    seen = 0
    paper = 255
    for level in range(255, -1, -1):
        seen += histogram[level]
        if seen >= target:
            paper = level
            break

    below = paper - margin
    reds: list[int] = []
    greens: list[int] = []
    blues: list[int] = []
    ink = 0
    for y in range(y0, y1):
        base = y * width * 3
        for x in range(x0, x1):
            i = base + x * 3
            r, g, b = pixels[i], pixels[i + 1], pixels[i + 2]
            if (r * 299 + g * 587 + b * 114) // 1000 >= below:
                continue
            ink += 1
            if (max(r, g, b) - min(r, g, b)) / 255.0 >= CHROMA_FLOOR:
                reds.append(r)
                greens.append(g)
                blues.append(b)
    if not ink:
        raise ImageError('no ink at all below paper %d: this is a blank image' % paper)
    if reds:
        middle = lambda values: sorted(values)[len(values) // 2]
        median = (middle(reds), middle(greens), middle(blues))
    else:
        median = (0, 0, 0)
    return InkColour(paper=paper, ink=ink, coloured=len(reds), median=median)


# ---------------------------------------------------------------- measuring

@dataclass
class Measurement:
    """What one drawing contributes: the distributions a brush is fitted to, and the counts that say how much to
    trust them. A percentile from forty pixels is not a measurement, and `runs` is kept so that is visible."""
    path: str
    width: int
    height: int
    runs: int
    line_runs: int
    area_runs: int
    ink_ratio: float
    darkness: float
    width_mean: float
    width_median: float
    width_p90: float
    width_max: int
    taper_ratio: float
    histogram: dict = field(default_factory=dict)
    note: str = ''


def measure(path: str, axis: str = 'both') -> Measurement:
    """Measure one drawing's linework.

    **A run of ink is not always a line.** A full-colour illustration has large dark regions -- hair, clothing, shadow
    -- and a naive scan reads them as strokes tens of pixels wide, which drags the mean width to a number that
    describes neither the lines nor the shapes. So runs are split: `line_runs` are 2..`MAX_LINE_WIDTH` px and are what
    the brush is fitted to, `area_runs` are wider and are reported as evidence that a picture is a painting rather
    than linework. The first illustration measured here came back at 81% ink with a mean width of 13 px, which is what
    that looks like before the split -- and the split is what told us the image was not a line drawing at all.
    """
    image = load_greyscale(path)
    if axis == 'both':
        runs = image.line_widths(axis='x') + image.line_widths(axis='y')
    else:
        runs = image.line_widths(axis=axis)
    lines = sorted(r for r in runs if 2 <= r <= MAX_LINE_WIDTH)
    areas = [r for r in runs if r > MAX_LINE_WIDTH]
    # **A width threshold alone cannot tell a line from a blob.** A 40-pixel-wide filled block produces a 8-pixel run
    # on every row it spans, so each of those runs looks like a line by width and there are forty of them -- the block
    # enters the width distribution and moves the mean toward its own thickness. What distinguishes them is not width
    # but *how many times a width repeats*: a line contributes a handful of runs, a filled region contributes one per
    # scanline it covers. Runs whose width occurs suspiciously often are therefore counted as area.
    if lines:
        counts = {}
        for value in lines:
            counts[value] = counts.get(value, 0) + 1
        repeat_cutoff = max(REPEAT_FLOOR, int(0.25 * len(lines)))
        repeated = {value for value, count in counts.items() if count >= repeat_cutoff and value >= 4}
        if repeated:
            kept = [value for value in lines if value not in repeated]
            areas.extend(value for value in lines if value in repeated)
            lines = kept

    def percentile(fraction: float) -> float:
        if not lines:
            return 0.0
        index = min(len(lines) - 1, int(fraction * len(lines)))
        return float(lines[index])

    histogram: dict[str, int] = {}
    for value in lines:
        bucket = '%d-%d' % (value // 2 * 2, value // 2 * 2 + 1)
        histogram[bucket] = histogram.get(bucket, 0) + 1

    # **Taper is measured, not assumed.** The thinnest fifth of the lines against the overall mean is the ratio a
    # brush's end curves have to reproduce; a model whose tapers are too short shows up here as a ratio near 1.
    thin = lines[:max(1, len(lines) // 5)] if lines else []
    taper = (sum(thin) / len(thin)) / (sum(lines) / len(lines)) if thin and lines else 0.0
    note = ''
    if not lines:
        note = 'no line-like runs found (2-%d px)' % MAX_LINE_WIDTH
    elif len(lines) < MIN_LINE_RUNS:
        note = 'only %d line-like runs, too few to fit against' % len(lines)
    return Measurement(
        path=path, width=image.width, height=image.height, runs=len(runs),
        line_runs=len(lines), area_runs=len(areas),
        ink_ratio=round(image.ink_ratio(), 5), darkness=round(image.mean_darkness(), 2),
        width_mean=round(sum(lines) / len(lines), 3) if lines else 0.0,
        width_median=percentile(0.5), width_p90=percentile(0.9),
        width_max=lines[-1] if lines else 0, taper_ratio=round(taper, 4),
        histogram=histogram, note=note,
    )


def _width_profiles(image: Greyscale, ceiling: int = 16) -> list[list[int]]:
    """Width-along-the-stroke profiles, for strokes that run roughly vertically.

    **The width of a stroke is the length of its run on a scanline**, and the sequence of those lengths down the
    scanlines is its width profile -- the thing a taper shows up in. Getting this the wrong way round is easy and
    silent: reading runs *along* a column measures how long the stroke is, not how wide, and a filter meant to reject
    filled regions then rejects every stroke in the picture. That version reported zero strokes for a plain uniform
    bar, which is at least a loud way to be wrong.

    Runs in successive scanlines are chained into one stroke when they overlap or nearly touch, which is what turns a
    column of numbers into a line.
    """
    profiles: list[list[int]] = []
    open_strokes: list[tuple[int, int, list[int]]] = []      # (first x, last x, widths so far)
    for y in range(image.height):
        row = image.pixels[y * image.width:(y + 1) * image.width]
        runs: list[tuple[int, int]] = []
        start = 0
        length = 0
        for index, value in enumerate(list(row) + [255]):
            if value < INK_THRESHOLD:
                if length == 0:
                    start = index
                length += 1
                continue
            if length:
                runs.append((start, length))
                length = 0
        still_open: list[tuple[int, int, list[int]]] = []
        continued: set[int] = set()
        for first_x, width in runs:
            last_x = first_x + width - 1
            centre = first_x + width / 2.0
            matched = None
            for index_candidate, candidate in enumerate(open_strokes):
                c_first, c_last, _widths = candidate
                c_centre = (c_first + c_last) / 2.0
                # **Match on the centre, not on whether the ends touch.** A taper changes a stroke's width quickly,
                # so consecutive runs can belong to the same stroke while their extents barely overlap: a 2-pixel run
                # and a 6-pixel run of one stroke share only their middle. An overlap test breaks the chain there and
                # the stroke is read as several -- the profile came out as [6,5,4,3,2] then [6,...] then [2,3,4,5,6],
                # which inverted its ends and made a tapered line measure as having *wider* ends than its body.
                if -1.5 <= centre - c_centre <= 1.5:
                    matched = index_candidate
                    break
            if matched is None:
                # a run seen for the first time: open a stroke for it, and do NOT close it this row
                still_open.append((first_x, last_x, [width]))
            else:
                c_first, c_last, widths = open_strokes[matched]
                still_open.append((first_x, last_x, widths + [width]))
                continued.add(matched)
        # **Only the strokes that failed to continue are finished.** Closing everything left open -- which is what
        # this did first -- closes each stroke on the same row it was opened, so no profile is ever longer than one
        # row and every measurement silently describes a single scanline instead of a line.
        for index_candidate, (_f, _l, widths) in enumerate(open_strokes):
            if index_candidate in continued:
                continue
            if len(widths) >= 6 and all(w <= ceiling for w in widths):
                profiles.append(widths)
        open_strokes = still_open
    for _first_x, _last_x, widths in open_strokes:
        if len(widths) >= 6 and all(w <= ceiling for w in widths):
            profiles.append(widths)
    return profiles


def _ends_over_body(profile: list[int], end_fraction: float = 0.05) -> float:
    """One stroke's ends against its own body. Scale-free by construction.

    **The end window has to stay small, and this is where the first version went wrong.** At 15% of a stroke's
    length, a line whose taper occupies the last few percent reports almost no taper at all -- the window averages
    over mostly-full-width pixels -- so every long stroke reads as uniform and the metric saturates near 1.0 whatever
    the brush does. Measuring the ends where they are means a window small enough to be *inside* a taper, and for a
    drawing whose lines are hundreds of pixels long that is a few percent, not a sixth.
    """
    count = len(profile)
    if count < 6:
        return 0.0
    cut = max(1, int(count * end_fraction))
    ends = profile[:cut] + profile[-cut:]
    body = profile[cut:count - cut] or profile
    body_mean = sum(body) / len(body)
    return (sum(ends) / len(ends)) / body_mean if body_mean else 0.0


def _tip_over_peak(profile: list[int]) -> float:
    """This stroke's thinnest end against its own widest point.

    A second view of the same property, and a more robust one: it does not depend on choosing a window at all, so a
    long line and a short one are directly comparable. A uniform line gives 1.0; a line that thins to a fifth at its
    tip gives 0.2.
    """
    if len(profile) < 6:
        return 0.0
    peak = max(profile)
    if peak <= 0:
        return 0.0
    tip = min(profile[0], profile[-1])
    return tip / peak


def measure_taper(image: Greyscale, ceiling: int = 16) -> dict:
    """How thin a drawing's lines get at their ends, measured where the ends actually are.

    **Why the whole-stroke statistic cannot answer this.** `taper_ratio` compares the thinnest fifth of every run in a
    picture against the mean, and a taper occupies a few percent of a stroke's length -- so that statistic is
    dominated by differences between strokes and barely moves when the ends change. Lowering a brush's taper floor
    from 0.25 to 0.06 changed it by nothing at all in a rendered measurement, which first looked like a broken metric
    and turned out to be a metric being asked a question it does not answer.

    What does answer it is taking each line's width *along its own length* and comparing its ends with its middle.
    Both axes are scanned, because a drawing's lines mostly run one way and measuring only one axis would measure only
    the strokes that happen to cross it. The ratio is scale-free, so a sketch and a 1920-pixel illustration can be
    compared, which is the property the earlier comparisons kept losing.
    """
    profiles = _width_profiles(image, ceiling)
    transposed = Greyscale(width=image.height, height=image.width,
                           pixels=bytearray(_transpose(image)))
    profiles += _width_profiles(transposed, ceiling)
    if not profiles:
        return {'strokes': 0, 'ends_over_body': 0.0, 'tip_over_peak': 0.0}
    ends = [r for r in (_ends_over_body(p) for p in profiles) if r > 0]
    tips = [r for r in (_tip_over_peak(p) for p in profiles) if r > 0]
    ends.sort()
    tips.sort()
    return {
        'strokes': len(profiles),
        # ends_over_body uses a 5% window at each end; tip_over_peak needs no window at all
        'ends_over_body': round(sum(ends) / len(ends), 4) if ends else 0.0,
        'tip_over_peak': round(sum(tips) / len(tips), 4) if tips else 0.0,
        'tip_over_peak_median': round(tips[len(tips) // 2], 4) if tips else 0.0,
    }


def _transpose(image: Greyscale) -> bytes:
    out = bytearray(image.width * image.height)
    for y in range(image.height):
        row = image.pixels[y * image.width:(y + 1) * image.width]
        for x in range(image.width):
            out[x * image.height + y] = row[x]
    return bytes(out)


def scan(root: str, limit: int = 0, axis: str = 'both') -> list[Measurement]:
    """Measure every image under a directory, skipping what cannot be read and saying so."""
    found: list[Measurement] = []
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() not in ('.png', '.jpg', '.jpeg', '.bmp', '.webp'):
                continue
            if limit and len(found) >= limit:
                return found
            path = os.path.join(base, name)
            try:
                found.append(measure(path, axis=axis))
            except ImageError as exc:
                found.append(Measurement(path=path, width=0, height=0, runs=0, ink_ratio=0.0, darkness=0.0,
                                         width_mean=0.0, width_median=0.0, width_p90=0.0, width_max=0,
                                         taper_ratio=0.0, note='skipped: %s' % exc))
    return found


def summarise(measurements: list[Measurement]) -> dict:
    """Pool a library's measurements into the numbers a brush would be fitted against.

    Pooled by run count rather than per image, so a large drawing contributes more than a small one -- which is what
    fitting a single brush to a whole library means.
    """
    usable = [m for m in measurements if m.runs and not m.note]
    if not usable:
        return {'images': len(measurements), 'usable': 0, 'note': 'nothing measurable'}
    total_runs = sum(m.runs for m in usable)
    return {
        'images': len(measurements),
        'usable': len(usable),
        'skipped': len(measurements) - len(usable),
        'runs': total_runs,
        'ink_ratio': round(sum(m.ink_ratio for m in usable) / len(usable), 5),
        'darkness': round(sum(m.darkness for m in usable) / len(usable), 2),
        'width_mean': round(sum(m.width_mean * m.runs for m in usable) / total_runs, 3),
        'width_median': sorted(m.width_median for m in usable)[len(usable) // 2],
        'width_p90': sorted(m.width_p90 for m in usable)[int(0.9 * (len(usable) - 1))],
        'taper_ratio': round(sum(m.taper_ratio * m.runs for m in usable) / total_runs, 4),
    }


def save_report(measurements: list[Measurement], summary: dict, path: str, source: str = '') -> str:
    payload = {'source': source, 'summary': summary, 'images': [asdict(m) for m in measurements]}
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
    return path


def compare(generated: dict, reference: dict) -> dict:
    """The gap between a generated sheet and the library, as ratios rather than as adjectives.

    This is the calibration error. A model that says it is close is worth nothing; a model that reports its width mean
    is 1.8x the reference's is a model somebody can correct.

    **Only two of these ratios are honest without a scale.** `taper_ratio` and `ink_ratio` are ratios of one length to
    another within the same picture, so a small sheet and a 1920-pixel illustration are comparable. Widths are not:
    they are pixel counts, and comparing them across two canvases of different sizes produces a confident number that
    means nothing. They are returned anyway, because a caller who knows the scale can use them -- but the caller has
    to know it. The first real comparison run here reported a width mean 1.8x the library's while the canvas was only
    0.79x the size of a reference illustration, which is what "genuinely too thick" looks like as opposed to "smaller".
    """
    out: dict[str, float] = {}
    for key in ('width_mean', 'width_median', 'width_p90', 'taper_ratio', 'ink_ratio', 'darkness'):
        a, b = generated.get(key), reference.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b:
            out[key] = round(a / b, 4)
    return out


# Ratios that survive a change of canvas size. Everything else needs the scale factor to be interpreted.
SCALE_FREE = ('taper_ratio', 'ink_ratio')


def check(generated: dict, reference: dict, tolerance: float = 0.4) -> dict:
    """`compare`, plus a verdict per scale-free metric.

    The verdict is the point: a fit that is 40% out is not a fit, and saying so in a function stops "close enough"
    from being decided by whoever is reading the numbers last.
    """
    ratios = compare(generated, reference)
    verdicts = {}
    for key in SCALE_FREE:
        if key in ratios:
            verdicts[key] = 'ok' if abs(ratios[key] - 1.0) <= tolerance else 'off by %.1fx' % ratios[key]
    return {'ratios': ratios, 'verdicts': verdicts}
