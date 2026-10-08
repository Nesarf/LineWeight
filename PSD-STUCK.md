# Stuck: `lineweight` writes a PSD whose layer channels `psd-tools` reads as white

A status report for outside help. Every number below was produced by running the code in this repository against the
files named, and each is reproducible with the commands at the end. Nothing here is inferred from the specification.

## The goal and the exact failure

`lineweight` (pure-stdlib Python) generates vector strokes and writes a layered PSD that **PaintTool SAI 1.2.6** should
open with the drawing visible and the layers separate. The merged image section is correct and independently verified.
The layer channels are not: SAI opens the file, sizes the canvas correctly, lists the layer and its name in the panel,
and draws nothing.

## The smallest case that shows it

One layer, one path, filling the whole 8x8 canvas with solid `#FF0000`.

```
writer intent (in memory, before serialisation)   pixel(0,0) = (255, 0, 0, 255)
psd-tools, reading the file back                  pixel(0,0) = (255, 255, 255, 255)
```

G and B come back as 255 where the file was written with 0. Alpha is right. Layer bbox is right: `(0, 0, 8, 8)`.

## What is verified about this same file

Each of these was measured, not assumed.

**(a) The channel values the writer intends are correct.**

```
ch -1 (alpha) row0 = [255, 255, 255, 255]     255 = opaque
ch +0 (R)     row0 = [255, 255, 255, 255]
ch +1 (G)     row0 = [0, 0, 0, 0]
ch +2 (B)     row0 = [0, 0, 0, 0]
ch -2 (mask)  row0 = [255, 255, 255, 255]     all-white user mask
```

**(b) The channel blobs are present verbatim in the file.** Searching the file for each blob `_packed_channel()`
produced finds it at the expected offset.

**(c) The PackBits coding round-trips through `psd-tools`' own decoder.** Giving `psd_tools.compression.decompress` the
bytes *after* the two-byte compression tag, for every channel:

```
ch -1: tag=1  OK
ch +0: tag=1  OK
ch +1: tag=1  OK
ch +2: tag=1  OK
ch -2: tag=1  OK
```

**(d) `psd-tools` parses the layer record correctly.** It reports 5 channels with the right ids and lengths:

```
rect=(0, 0, 8, 8)
channels=[(-1, 34), (0, 34), (1, 34), (2, 34), (-2, 34)]
```

**(e) The channel data layout is continuous blobs in record order.** Confirmed by walking a PSD that SAI wrote itself
(1600x1200, a real hand-drawn stroke): the blobs are consecutive and their declared lengths account for the section
exactly.

**(f) The row format.** Compression tag (2 bytes) = 1, then a table of **2-byte big-endian row lengths for every row**,
then the rows. Taken from `psd_tools/compression/__init__.py`:

```python
row_size = (width * depth + 7) // 8
bytes_counts = read_be_array(("H", "I")[version - 1], height, fp)
return b"".join(rle_impl.decode(fp.read(count), row_size) for count in bytes_counts)
```

Verified against SAI's own file: the counts sum to exactly the bytes after the table (253104 of 253104) and the rows
expand to exactly the channel size (1662661 of 1662661).

**(g) Rows are top-down**, established by writing the same picture with `psd-tools` (red top-left, green top-right, blue
bottom-left, yellow bottom-right) and decoding its channels back: each channel is high exactly where its colour was
placed, with no flip.

## What has been tried and did not change the outcome

| change | source | effect on the read |
|---|---|---|
| rounded rectangle field order `top, left, bottom, right` | spec + `psd-tools` | already correct |
| `8BIM` before the blend mode | SAI's own file | necessary, fixed earlier |
| layer count positive | SAI's own file | necessary, fixed earlier |
| channel order `-1, 0, 1, 2` | SAI's own file | already correct |
| alpha not inverted | SAI's own file via `psd-tools` | fixed transparent/opaque, colours still wrong |
| rows not reversed | `psd-tools` output | no change |
| added 5th channel `-2` (all-white user mask) | `psd-tools` output | no change |
| blending ranges `8 x channels` bytes with declared length | `psd-tools` output | no change |
| layer flags `0x00` vs `0x08` | `psd-tools` output | not yet tried; `0x00` is current |

## The two files, layer-info region, byte for byte

Both are the same 8x8 solid-red picture.

```
MINE   layer info at 70, length 278
  @70   (rel 0  ) 00 01 | 00 00 00 00 | 00 00 00 00 | 00 08 | 00 00 00 08
        count=1        rect top=0,left=0            bottom=8   right=8
  @86   (rel 16 ) 00 05 | ff ff 00 00 00 22 | 00 00 00 00 00 22 | 00 01 ...
        nch=5            ch -1 len 34          ch 0  len 34       ch 1
  @118  (rel 48 ) ... 38 42 49 4d 6e 6f 72 6d | ff | 00 | 00 | 00
                       "8BIM" "norm"            op   clip flags filler
  @134  (rel 64 ) 00 2a | 00 00 00 00 | 00 00 00 00 | 05 53 4f 4c 49 44 ...
        extra_len=42     mask len 0     blend len 0    "SOLID"

THEIRS layer info at 136, length 312
  @136  (rel 0  ) 00 01 | 00 00 00 00 | 00 00 00 00 | 00 08 | 00 00 00 08
  @152  (rel 16 ) 00 05 | ff ff 00 00 00 22 | 00 00 00 00 00 22 | ...
  @184  (rel 48 ) ... 38 42 49 4d 6e 6f 72 6d | ff | 00 | 08 | 00
                       "8BIM" "norm"            op   clip flags=0x08 filler
  @200  (rel 64 ) 00 4c | 00 00 00 14 | <20 bytes of mask rect> | 00 00 00 28 | <40 zero bytes> | 05 53 4f 4c 49 44
        extra_len=76     mask len=20                             blend len=40          "SOLID"
```

The remaining structural differences are the mask block (theirs declares 20 bytes of a real mask rectangle, mine
declares 0 for "no mask") and the flags byte. Both are legal in the specification.

## The four questions

1. **What else is in the layer-info section that differs between these two files?** The comparison above is by field; a
   byte-by-byte walk of the whole region has not been done, and the fault could be in a part not being looked at.

2. **Does the layer mask block matter?** `psd-tools` declares 20 bytes of mask data (a rectangle plus default colour
   plus flags) where this writer declares zero. Zero is documented as "no mask". Could a reader be using the presence of
   that block, or its length, to compute where something else begins?

3. **Is there anything about the `-2` channel's position?** `psd-tools` writes the order `-1, 0, 1, 2, -2`. SAI's own
   file has only four channels, `-1, 0, 1, 2`, with no `-2` at all -- and SAI renders it correctly. That suggests `-2`
   is not the issue, but it also means SAI's file and `psd-tools`' file differ in a way neither this writer nor the
   questions above account for.

4. **Given that the PackBits coding, the channel values, the record, and the file offsets all check out, what is left
   that could make a reader produce white where `(255, 0, 0, 255)` was written?** The pattern -- G and B reading as 255
   when they were written as 0 -- looks like a reader substituting a fill rather than misreading a value, which would
   point at a channel being rejected and replaced. `psd-tools` documents exactly that behaviour:

   > Issued when channel data cannot be fully decompressed. The affected channel is replaced with black pixels.

   That would give black, not white, so it does not explain this either -- but it does suggest looking at whether a
   warning is being emitted.

## Reproducing

```bash
python -m pip install --target <dir> psd-tools
PYTHONPATH=<dir> python -c "
from psd_tools import PSDImage
import numpy as np
psd = PSDImage.open('probe.psd')
a = (psd[0].numpy()*255).round().astype(int)
print(tuple(int(v) for v in a[0,0]))     # (255, 255, 255, 255) where (255, 0, 0, 255) was written
"

python tests/tools/psd_records.py FILE      # layer records, field by field
python tests/tools/psd_layout.py FILE       # test candidate channel-data layouts against a real file
python tests/tools/psd_pixels.py FILE       # decode layer channels and report ink coverage
python tests/tools/psd_show.py FILE         # render a channel as text so its shape is visible
python tests/tools/psd_inspect.py A B       # field-by-field diff of two files
```

Files: `tests/tools/` in this repository. The writer is `lineweight/psd.py`; `save_psd()` and `_packed_channel()` are
the two functions that matter.

## What is NOT claimed

* That the writer is correct and `psd-tools` is wrong. Both are candidates.
* That SAI's behaviour is explained. SAI's own saved PSD renders correctly through `psd-tools`; this writer's does not;
  that is the whole of what is known about SAI's side.
* Any of the four claims this project previously made and retracted: that the layer count must be negative, that a flat
  drawing's three colour channels must encode to equal lengths, that rows are stored bottom-up, that the alpha is
  inverted. All four were wrong, three of them because a check consisted of this project's own reader agreeing with this
  project's own writer.
