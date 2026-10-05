# Writing a layered PSD that PaintTool SAI 1 will open

A status report for outside help. Everything below is measured against files on disk, and the exact tooling is named so
each claim can be re-checked. Nothing here is inferred from a specification.

## The goal

A pure-stdlib Python library (`lineweight`) writes a layered PSD from programmatic vector strokes. The merged image is
verified correct. **SAI 1.2.6-Beta.3 opens the file, reports no error, shows its canvas, lists the layer names in the
layer panel — and draws nothing on the canvas.**

The file opens. The layers are named. The pixels do not appear.

## What SAI is

`PaintTool SAI Ver.1.2.6-Beta.3`, 2025-01-27, English build, at `E:\Apps\SAI-en\sai.exe`. It runs as `sai.exe`, window
class `sfl_window_class`, and its dialogs are custom-drawn (no Win32 `#32770`), which matters for the automation notes
at the end.

## Reference files SAI 1 wrote itself

Two files were saved by hand from SAI and are the ground truth. Both are available.

**A blank new canvas** (15876 bytes):

```
banner         512x512, 3 channels, depth 8, mode 3
colour mode    0 bytes
resources      360 bytes
layer+mask     116 bytes
layer info     112 bytes
layer count    +1
record         rect top=0 left=0 bottom=0 right=0   (empty: nothing drawn)
               channels [(-1,2), (0,2), (1,2), (2,2)]
               sig 8BIM, blend norm, opacity 255, clip 0, flags 0x00, filler 0
               extra 0x2C bytes = mask(4) + blending(4) + pascal "Layer1" + 8BIM luni block
channel data   8 bytes total (four near-empty channels)
global mask    0
```

**A canvas with one hand-drawn stroke** (278053 bytes):

```
banner         512x512, 3 channels, depth 8, mode 3
colour mode    0 bytes
resources      360 bytes
layer+mask     129099 bytes
layer info     129095 bytes
layer count    +1
record         rect bytes 00 00 00 19 | 00 00 00 00 | 00 00 01 f0 | 00 00 01 fe
                    read as top=25 left=0 bottom=496 right=510
               channels [(-1,49503), (0,26496), (1,26496), (2,26496)]
               sig 8BIM, blend norm, opacity 255, clip 0, flags 0x00
               extra 0x2C bytes, same shape as above
channel data   49503+26496*3 = 128991 bytes, which is exactly layer_info minus the records
global mask    0
```

Channel data layout is confirmed: **blobs consecutive in record order, each beginning with a 2-byte compression tag
(1 = PackBits), and the declared channel length includes that tag.** Walking it consumes a real file exactly
(`consumed 128991 of 128991`).

## What `psd-tools` says

`psd-tools` reads SAI's stroke file successfully:

```
PSDImage: size (512, 512), mode 3, channels 3, depth 8
  layer name='Layer1'  bbox=(0, 25, 510, 496)  opacity=255  visible=True  blend=NORMAL
  layer.numpy() -> shape (471, 510, 4), min=0 max=1, mean=0.6
```

It refuses the file produced by `lineweight`:

```
OSError: Invalid data section size: 16
```

(Pillow is not an option for this check — Pillow 12 has no PSD layer support at all, so its failure says nothing.)

## Difference between SAI's file and the generated one

| | SAI 1 | lineweight | note |
|---|---|---|---|
| banner channels | 3 | 3 | matched |
| layer count | +1 / +2 | +2 | positive in both |
| layer channel order | `(-1, 0, 1, 2)` | `(-1, 0, 1, 2)` | matched |
| layer flags | `0x00` | `0x00` | matched |
| record signature | `8BIM` + `norm` | `8BIM` + `norm` | matched |
| `luni` block | present | present | matched |
| resource 1005 (resolution) | present, 16 bytes of data | present | matched |
| **layer info length** | **excludes the global mask** | **excluded after a fix** | was including it |
| **global mask placement** | **own field, 0 bytes** | **own field, 0 bytes** | was inside layer info |
| **image resources** | **360 bytes, 4 blocks** | **24 bytes, 1 block** | see below |

### The current blocker

`psd-tools` fails while reading the **image resources**. Traced directly:

```python
from psd_tools.psd.bin_utils import read_length_block
fp = io.BytesIO(open('lineweight-demo.psd','rb').read()); fp.seek(26)
block = read_length_block(fp)     # -> b'' (length 0), tell = 30
```

That is correct so far — offset 26 holds the colour-mode length, which is 0. But after
`ImageResources.read(fp)` the stream is still at 30 rather than 58, so the layer-and-mask length is then read from
offset 30 (where the image-resources length, 24, sits) and comes out as **943868237**.

The generated resource block is 24 bytes and declares 24:

```
38 42 49 4d 03 ed 00 00 00 00 00 10 00 48 00 00 00 01 00 48 00 00 00 01
8BIM         id=1005  len=0 pad   dataLen=16
                                  72dpi<<16 + unit1, twice
```

SAI's equivalents for the same resource, from its 360-byte block:

```
id=1005  nameLen=0  dataLen=16      (resolution)
id=1024  nameLen=0  dataLen=2       (layer state)
id=1026  nameLen=0  dataLen=2       (layer group)
id=1058  nameLen=0  dataLen=292     (version info)
```

Walking SAI's block from offset 34 with the rule "pascal name padded so the name field is even, then a 4-byte length,
then data padded to even" consumes exactly 360 of 360. **The same rule applied to the generated block consumes 28 of a
declared 24** — that is where it stands and it has not been resolved.

### The specific questions

1. What exactly does an image resource block's name field pad to, and how many bytes should
   `8BIM` + `id=1005` + empty name + 4-byte length + 16 bytes of data occupy in total?
2. Is a resolution resource required at all, or would a file with **zero** image resources be read by SAI and by
   `psd-tools`? (The writer originally emitted none, and that version was never checked with `psd-tools`.)
3. Independently of the above: **does SAI read layer pixels from the layer channels or from the merged image?**
   The merged section of the generated file is verified correct (three RGB channels, PackBits, white paper, correct ink
   coverage, byte-exact length) yet nothing is drawn, which suggests the layers take precedence and the layer channel
   data is where the remaining fault is.
4. SAI's stroke layer declares `49503` bytes for the `-1` channel over a `510x471` region (240210 cells). Decoding it
   as rows of 1-byte length prefix + PackBits recovers only 87688 cells with 471 rows consumed. **What is the row
   format of a layer channel in a SAI 1 PSD?** This has not been established and is the second open item.

## Tooling that produced these numbers

```
python tests/tools/psd_records.py FILE        # raw byte dump of layer records, per field
python tests/tools/psd_pixels.py FILE         # decode layer channels and report ink coverage
python tests/tools/psd_layout.py FILE         # test candidate channel-data layouts, keep the consistent one
python tests/tools/psd_rowformat.py FILE      # search the row format against the implied cell count
python tests/tools/psd_inspect.py A B         # field-by-field diff of two files
```

`psd-tools` was installed ad hoc for the independent check:

```
python -m pip install --target <dir> psd-tools
PYTHONPATH=<dir> python -c "from psd_tools import PSDImage; print(PSDImage.open('file.psd'))"
```

## Automating SAI 1, for anyone who goes further

Recorded because several rounds were lost to it.

* **A command-line argument does open a file.** `Start-Process sai.exe -ArgumentList '"C:\path\file.psd"'` works, and
  the window title becomes `SAI - Experimental (E:) / path / file.psd`. Unquoted arguments and short waits are what made
  earlier attempts look like failures: the document can take 60-100 seconds to appear. **Wait for the title to change;
  do not sleep and assume.**
* **`AppActivate` and `SetForegroundWindow` both fail** and leave the foreground where it was, so keystrokes go to
  another application entirely. The foreground lock is not lifted by being an administrator. `AttachThreadInput` to the
  thread owning the foreground window, then `SetForegroundWindow`, **with the attachment held open while the keys are
  sent**, does work.
* **A shortcut in SAI 1 is usually the start of a sequence.** Ctrl+N opens a canvas dialog that still wants confirming;
  Ctrl+O opens a custom "Open Canvas" window whose controls are all `sfl_window_class`.
* **Those custom controls ignore `WM_SETTEXT`, `WM_CHAR` and posted click messages.** Real cursor movement plus
  `mouse_event` reaches them; message-level automation does not.

## What is already correct and should not be re-litigated

* The merged image section: three RGB channels, PackBits with a **single-byte** row-length prefix, composited onto
  white, byte-exact with no trailing data.
* Layer records: rectangle order `top, left, bottom, right`; four channels ordered `-1, 0, 1, 2`; `8BIM` before the blend
  mode; `luni` Unicode name block; flags `0x00`.
* Two earlier conclusions in the project's history were wrong and are retracted in the repository: that a positive layer
  count causes an empty layer panel, and that the layer count should be written negative.
