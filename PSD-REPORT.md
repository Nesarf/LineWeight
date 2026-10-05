# How `lineweight` writes a PSD, and every fault found on the way

This is the whole account: the pipeline, each defect, how it was found, and what is still broken. Every number here was
measured against a file on disk. Reference files used are named, because a claim traced to a file can be re-checked and
a claim traced to reasoning cannot.

## Why PSD, and what "working" means

`lineweight` produces vector strokes with no hand involved: a pressure model, then stroke-to-outline expansion. Three
applications are targets because they are what the work has to move through. For SAI the only door is a layered PSD,
because SAI has no scripting interface at all. So the requirement is exact: **write a PSD that SAI opens, with the
drawing visible and the layers separate.**

Three grades of "works", and they are not the same thing:

1. the file parses
2. **this project's own reader** reads it back
3. an application shows the drawing

Grade 2 is worth almost nothing on its own, and most of the time lost in this work came from treating it as if it were
grade 3.

## The container, section by section

```
8BPS, version 1
reserved (6 bytes, zero)
channels (2)  height (4)  width (4)  depth (2)  colour mode (2)
── colour mode data        length (4) + data
── image resources         length (4) + data
── layer and mask section  length (4)
     └ layer info          length (4)
          layer count (2, signed)
          layer records
          layer channel data
── global layer mask info  length (4), zero here
── merged image data       3 channels, PackBits
```

The nesting is the first trap: **the layer-and-mask section has a length, and the layer-info block inside it has its
own length, and the global mask follows both.** Counting the global mask inside the layer info gives a section that
announces four bytes more than it holds.

## Layer record, field by field

```
rectangle        top, left, bottom, right  (4 x int32)   <- this order, not top/bottom/left/right
number of channels (2)
per channel:  id (2, signed)  length (4)
blend signature  "8BIM"
blend mode       "norm"
opacity          1 byte, 0-255
clipping         1 byte
flags            1 byte
filler           1 byte
extra data       length (4) + data:
                     layer mask data       4 bytes (zero)
                     blending ranges       4 bytes (zero)
                     name as a Pascal string, padded to a multiple of 4
                     "8BIM" + "luni" + length + the name as UTF-16BE
then, after every record:
    the channel data, in record order, each blob beginning with a 2-byte compression tag
```

## The channel data, which is where it kept going wrong

A channel is a compression tag, then the rows. For PackBits (tag 1) the layout is:

```
tag               2 bytes, 1 = PackBits
row counts        height x 2 bytes, big-endian, ALL OF THEM FIRST
row data          the rows, in order, each exactly as long as its count
```

`row_size = (width * depth + 7) // 8` — the uncompressed size of one row.

## Every fault found, and how

### 1. No 8BIM signature on the layer record

Wrote the 4-byte blend mode alone. The bytes on disk began `8BPSnorm` — the **file-header** signature where the
**resource** signature belongs. To SAI the document then has no layer records at all, so it opens the file, shows the
canvas, reports no error, and presents an empty layer panel.

Found by diffing against a PSD SAI had saved itself. **`read_psd_header`, this project's own reader, skipped the
signature field as well**, so the round trip passed for several rounds while certifying a file no application could read.

### 2. The layer count written negative

Written negative on the strength of an experiment where a positive count appeared to produce an empty layer panel — but
that file also carried fault 1, so the observation was contaminated and the conclusion drawn from it was wrong. SAI's
own file writes a positive count. The reader reports the sign as a flag; the writer matches the application.

### 3. Global layer mask counted inside the layer info length

Announced four bytes more than the block held. `psd-tools` refused the whole file with `Invalid data section size`.

### 4. The resolution resource declared 12 bytes and its block was 16

Its six fields are `horizontal, horizontal_unit, width_unit, vertical, vertical_unit, height_unit` — `I 2H I 2H`, sixteen
bytes. Only the four obvious ones were written. Found in `psd-tools`' `ResoulutionInfo.read`, which reads `"I2HI2H"`.

### 5. The image resource block's name field

An image resource is `8BIM`, a 2-byte id, then the name as a Pascal string **padded so the name field is an even number
of bytes**. An empty name is therefore two bytes: a zero length and its pad. Getting this wrong shifts every following
section.

### 6. The merged image was RGBA

Its channel count is the **header's**, and for RGB that is three; a layer record lists its own channels separately and
carries four. `CHANNELS = 4` was doing duty for both.

### 7. The merged image had a transparent background

It started from zeroes, so untouched pixels stayed `(0,0,0,0)` — a composite whose background is transparent black.
Three RGB channels *mean* opaque, so a viewer draws that as a black canvas. It is composited onto white now.

### 8. Channel ids

`channel_bytes(-1)` wrote `self.data[i * 4 + (-1)]`, which is `i * 4 - 1` — **the previous pixel's blue byte** for every
pixel but the first. Python's negative indexing looks like it handles "channel -1 is alpha" and does the opposite.

### 9. The row counts: one byte instead of two, and interleaved instead of a table

The fault that took longest, and the one worth reading about.

The writer emitted, for each row, a **single-byte** length followed by that row. The reader read it the same way. Both
were wrong, and because they agreed, every round trip passed.

The symptom when a different decoder was used: the **first** row decoded correctly and everything after it was garbage,
surfacing as `compression 12` — a value the format does not have.

It was resolved by reading `psd_tools/compression/__init__.py`, the decoder that *does* work:

```python
row_size = (width * depth + 7) // 8
bytes_counts = read_be_array(("H", "I")[version - 1], height, fp)
return b"".join(rle_impl.decode(fp.read(count), row_size) for count in bytes_counts)
```

Two bytes per count, and all counts before all rows. Verified against SAI's own drawing: counts sum to exactly the bytes
after the table (253104 of 253104), rows expand to exactly the channel size (1662661 of 1662661, `EXACT`).

## Things I asserted that were wrong, and retracted

These are stated because each was written down as a finding and each was false.

* **"A layer count must be negative."** Wrong; it came from a contaminated experiment (fault 1).
* **"A flat drawing's three colour channels must encode to equal lengths."** Wrong. SAI's drawn file has 167983,
  170515, 174687. Generalised from an *empty* canvas where every channel is the same constant. A test asserting it was
  written and has been removed.
* **"The alpha channel is stored inverted."** Uncertain, not established either way.
* **"SAI's canvas is the largest child window."** The largest child is 692x373, and posting mouse messages to it draws
  nothing; SAI reads input from the queue, not from messages to its controls.
* **A measurement instrument that found its own region by looking for brightness** — it shrinks as the drawing fills it,
  so it reports a filled canvas as empty. Two "the shape does not draw" conclusions came from it.

## The one that is still open

**The layer channels still do not carry the drawing.**

What is known: SAI opens the file, lists the layer with its name, and sizes the canvas correctly. The canvas is blank.
`psd-tools` reads the layer's four channels as containing only the values 0 and 1. The row format is now right — that is
verified against a real SAI file — so the fault is in what those rows contain, or in which stream each channel reads.

The merged section of the same file decodes to a correct picture independently, so the difference is specifically in the
per-layer channel data.

## What actually moved this forward, and what did not

**Did not work:** inferring the format from bytes. Four separate conclusions were drawn that way and three were wrong.
Each looked like progress and cost a round.

**Did work, every time:** comparing against a file written by the application that has to read it. A reference PSD from
SAI found faults 1, 2, 9 and settled the alpha question. An independent parser (`psd-tools`, and notably *not* Pillow,
which has no PSD layer support at all) turned "my reader agrees with my writer" into a real check.

**The rule worth keeping:** a reader and a writer that share a mistake validate each other perfectly. Faults 1 and 9
both survived round-trip tests for that reason. Any check that is only the project's own code reading the project's own
output is not a check.
