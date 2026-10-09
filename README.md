# lineweight

Vector linework with weight, for the case where there is no tablet.

A stroke in SVG has one width from end to end, which is why vector drawings read as diagrams next to drawings made
by hand. `lineweight` models the thing a tablet measures — pressure — and expands each stroke into a **filled
outline** whose width varies along it, so plain SVG can carry line weight without any dependency on a drawing
application.

It exists because a language model asked to draw has no hand. Pressure cannot be felt, so it is computed from what is
observable about a line, and the numbers can be calibrated against real artwork rather than guessed.

## What it does

* **Four brushes** (`fine`, `ink`, `pencil`, `wash`), each the same set of numbers a paint program exposes: width,
  opacity, dab spacing, and jitter, plus two taper curves.
* **A pressure model.** Pressure follows four effects that a real stroke shows: it is lighter when the stroke is
  moving fast, lighter through a sharp turn, tapered at both ends of an open stroke, and drifting slowly underneath.
  Closed contours are walked once and never tapered, because a loop has no ends to taper.
* **Stroke to outline.** SVG cannot vary a stroke's width, so the width profile is expanded into an outline — offset
  the path to both sides by half the local width and fill the result. This is what a drawing application does when it
  expands a variable-width stroke, so the output stays plain SVG — but this implementation is the cheap version of it,
  and "What it is not" below has the measurements that shows where it differs.
* **Whole-document inking.** `inked_svg()` walks an existing SVG and gives every shape large enough to be part of a
  silhouette a weighted contour, leaving small details alone. Extent decides, not a list of names, so a shape added
  later is inked without anybody remembering to. The whole SVG command set is parsed — curves, arcs, relative
  commands — and ancestor `transform` attributes are applied, because a contour drawn in local coordinates inside a
  transformed group lands in the wrong place.
* **A document, and one writer per application.** The drawing is built once as layers of paths and handed to each
  destination in the form it opens: a script Illustrator runs, a layered PSD for SAI, and XFL for Animate.
* **Calibration against real artwork.** `--fit` measures a drawing's linework, and `lineweight.ref` measures a whole
  library of it — the distribution of ink across rows and columns, which is the appearance a brush's curves have to
  reproduce. `check()` compares a generated sheet against the library and reports the ratio, so "close enough" is a
  number rather than a judgement.

## What it is not

**It is not a renderer and not a drawing program.** It produces path data, and now also the files three drawing
applications open; what those applications then do with a path is their business and not this library's.

**The outline expansion is an approximation, and its failure mode is measured.** A stroke becomes a filled polygon by
offsetting the centreline along its normals, which is cheap and produces the correct *appearance* -- but the offset
curves cross each other where the stroke curves tightly, because that is what offset curves do. Counted on six shapes:

| centreline | self-intersections in the outline |
|---|---|
| straight line | 0 |
| right angle | 0 |
| sharp V | 0 |
| hairpin (out and back) | 9 |
| overlapping zigzag | 14 |
| **a smooth wave** | **354** |

SVG's default `fill-rule` is `nonzero`, so an overlapping lobe fills as a union and the crossings are invisible when the
shape is filled -- which is why this has not shown up as a visible defect, and why the numbers above are worth stating
rather than discovering later. They are still wrong geometry: any boolean operation, stroke-to-path conversion, or
geometry comparison downstream sees them. A real stroke expansion engine resamples by arc length, offsets with a variable
radius, solves the joins (miter, round, bevel) and removes the self-intersections. This is not that, and the calibration
numbers in this file are about *appearance*, which is the thing it does produce.

**It is not a general SVG processor.** `inked_svg()` walks a document with regular expressions; the table under "Use"
lists exactly what that reaches and what it does not.

## Install

    pip install -e .          # add [fit] to measure images instead of only drawing
    python -m lineweight --out strokes.svg
    python -m lineweight --fit reference.png

## Use

```python
from lineweight import stroke, inked_svg

# one stroke: a path in, a filled outline plus an opacity out
d, opacity = stroke([(40, 40), (140, 30), (240, 60)], 'ink')
svg = f'<path d="{d}" fill="#1A1620" opacity="{opacity:.2f}"/>'

# or ink a whole document that something else drew
inked = inked_svg(open('figure.svg').read(), min_extent=46, brush='ink', colour='#2A1E26')
```

**What `inked_svg` is, and what it is not.** It walks a document with regular expressions rather than parsing XML, which
is a real limitation and not a detail. It works well on the vector artwork it was written against -- generated SVG, hand-
built icons, illustration exports -- and it is not a general SVG processor. What it does is measured:

| document | what happens |
|---|---|
| `<path d="..."/>` and `<path d="..."></path>` | inked |
| any path command, absolute or relative, including arcs | inked |
| `transform` on the path, and on any `<g>` above it | accumulated correctly |
| a `<path>` inside `<!-- -->` | **left alone** -- a commented-out shape is not part of the drawing |
| a `<path>` inside `<defs>` or `<clipPath>` | **inked**, though it is a definition rather than visible artwork |
| `<use href="#id">` | the definition is inked where it is written, not where it is used |
| `style="transform: ..."` (a CSS transform) | ignored, so the outline is placed as though it were not there |
| `<svg:path>`, or any namespaced element name | not matched at all |
| `<rect>`, `<circle>`, `<ellipse>`, `<polygon>`, `<polyline>` | not inked: only `<path>` is, whatever its size |

Everything the patterns do not match is preserved verbatim -- the pass is a substitution, never a rebuild -- so an
unsupported element is left as it was rather than deleted. The first version of this function did rebuild, and it took a
figure's eyes with it.

## Getting the drawing into a drawing application

SVG is the right output when the destination is a browser or a repository. It is the wrong output when the
destination is an application, because a format cannot carry what it does not have: which layer a shape belongs to,
whether it is a filled outline or a stroked centre line. So the drawing is built once as a **document** and each
application is handed the form it actually opens.

```python
from lineweight import Document, Path, Appearance, jsx_document, write_xfl

doc = Document(width=800, height=600)
doc.layer('LINE').add(Path(points=outline_points, appearance=Appearance(fill='#19151F')))
doc.layer('DETAIL').add(Path(points=[(40, 380), (360, 380)], closed=False,
                              appearance=Appearance(filled=False, stroke='#6E1E2E', stroke_width=2.5)))

jsx_document(doc, export_svg='out.svg')   # a script Illustrator runs, rebuilding real layers and paths
write_xfl(doc, 'drawing.xfl')             # Animate's own uncompressed project format
```

On the command line:

    python -m lineweight --bridge draw.jsx --run     # Illustrator: write the script and run it
    python -m lineweight --psd draw.psd              # SAI: a layered PSD
    python -m lineweight --xfl draw.xfl --run        # Animate: write the XFL and open it

**What is measured, and what is not.** Illustrator 28.5 runs a generated script from a command line in about twenty
seconds and returns the drawing with its layers, fills and opacities intact, verified by reading back the SVG Illustrator
itself exported -- including that `ExportType.SVG` is the working constant and `ExportType.SVGFORMAT` does not exist in
that build.

**It needs Illustrator's own first run to have been completed once.** A fresh installation, or one whose settings
directory has been moved aside, will start, draw its menu bar, leave the workspace blank, ignore the script argument and
report nothing -- from the outside that is indistinguishable from the script being rejected, and it is what a documented
"restart to fix it" does not cure. Launching Illustrator by hand once, until its home screen appears, is what settles it;
after that the command-line path works every time. Written down because an afternoon went into diagnosing the script
generator for a fault that was in the application's first-run state.

**SAI works, and it is the destination that took the longest to reach.** A generated PSD opens in SAI 1.2.6 with its
canvas, its layer, its layer name, and its pixels -- verified by looking at the screen, because SAI has no scripting
interface and no other kind of evidence exists for it. Two independent parsers agree with that reading: `psd-tools` and
this project's own reader both return the exact colours written.

Getting there took several rounds, and `PSD-REPORT.md` has the full account. The short version is that **four separate
faults each produced a file that opened, parsed, and showed nothing**, and every one of them survived this project's own
round-trip tests because the reader made the same mistake as the writer:

* a layer record with no `8BIM` signature -- the file-header signature written where the resource signature belongs, so
  no reader could find any layer at all;
* row lengths written as one byte, and interleaved with the data, where the format has a table of two-byte lengths
  before all the rows;
* rows reversed, on a belief that layer channels are stored bottom-up, "confirmed" by an experiment that read the file
  back with the same assumption the writer used;
* the alpha channel inverted, which turns every opaque pixel into zero.

And one more that no amount of comparing bytes against a reference file found, because every comparison was of the wrong
question: **`layer.channel_bytes(-1)` was called for every channel id**, so channels 0, 1 and 2 each received the alpha
plane. The blobs were present, the PackBits coding was byte-identical to `psd-tools`', the record parsed, the offsets
lined up -- all of it verifying that the wrong data had been written faithfully. A unit test on `channel_bytes()` passed
throughout, because that function was correct; its caller had stopped passing the argument.

**The last piece was a channel this writer did not need.** A `-2` channel declares a user layer mask, and SAI reads one
as a real mask and switches the layer into mask-editing mode -- so the canvas shows the mask, which is empty, while the
layer content is perfectly correct. SAI's own saved file has four channels and no `-2`. It was added here to match
`psd-tools`' output, which was the wrong writer to imitate.

Animate works, and getting there was mostly about finding out what the format actually is. Nine hand-written skeletons
opened as documents while importing nothing, because an XFL is a **directory** holding `DOMDocument.xml` beside a
marker file named after the project and containing `PROXY-CS5`, and Animate has to be pointed at **the marker**, not
the folder -- the folder opens the home screen. A document Animate saved itself supplied the rest: `xflVersion="23.0"`,
`creatorInfo="Adobe Animate"`, `<scripts/>`/`<PrinterSettings/>`/`<publishHistory/>` on the root,
`layerDepthEnabled` on the timeline, and a frame with no `duration`.

Two more things were settled by measurement rather than by reading. A shape's geometry is written **twice**, in a
compact `edges` attribute and a verbose `cubics` form, and only the second is not a shape. And a drawing unit is not a
scene unit: a contour spanning its canvas renders about a **fortieth** of the stage, so the coordinates are scaled
before they are written. A generated XFL now opens with its own scene name and canvas and the drawing's variable-width
strokes visible on the stage.

Animate has no scriptable entry point on this machine at all, which is why the bridge is a file: JSFL passed on the
command line opens as a document, `FlashFactory` refuses out-of-process creation, a JSFL in `Configuration/Commands`
does not run when a document opens, its UI Automation tree is empty, a background process cannot take its focus, and
`Animate.exe drawing.svg` opens the home screen. After Effects 2024 ships no XFL exporter and Illustrator has no XFL
in its scripting dictionary.

## Calibrating to your own hand

The model's numbers should not be a matter of taste, so they are fitted to real drawings rather than chosen. A
reference library is a folder of artwork, measured by the same code that can measure a generated sheet, which makes
the gap between them a number instead of an opinion.

```python
from lineweight import scan, summarise, check

measurements = scan(r'D:\art\linework')          # decodes PNG by hand; JPEG needs Pillow
reference = summarise([m for m in measurements if m.ink_ratio < 0.30])
print(check(generated, reference))
#  {'verdicts': {'taper_ratio': 'ok', 'ink_ratio': 'off by 0.1x'}, ...}
```

**A run of ink is not necessarily a line.** A full-colour illustration's dark regions read as strokes tens of pixels
wide, so runs are split into lines (2-16 px) and areas, and a width that repeats on many scanlines is treated as a
region rather than a stroke. A library of paintings measured naively returns a mean width that describes no line in
any of them; the counts are printed so that is visible rather than plausible.

What the measurement says about the current model. The numbers are **ratios of one length to another inside a single
drawing**, which is the only kind of comparison that survives two pictures being different sizes. The targets come
from 276 line drawings pooled out of 929 measured images across three private collections -- character art, design
sheets and illustration files -- and the pooled summary is checked in as `tests/data/corpus_summary.json` so the targets
can be re-derived rather than taken on trust:

| | reference, inside one drawing | the model | verdict |
|---|---|---|---|
| `p90/median` -- a few heavy lines among many light ones | 2.75 | 2.67 | close: the model does produce a drawing's spread |
| `max/median` -- how far the heavy end reaches | 5.33 | 5.33 | equal |
| `taper_ratio` | 0.42 | 0.44 | closer after recalibration, but the instrument is confounded -- see below |

**Three independent collections agree, and that is the whole argument.** The 26-image library used first gave
`p90/median` 2.750 and `taper_ratio` 0.410; the 262-image pool gave 2.750 and 0.423; adding seventeen character-art
sheets moved the pool to 276 and returned 2.750 and 0.421. A number that survives being computed from three separate
sets of artwork is worth more than any one of them, and this is the only kind of check available here -- the model
cannot be its own referee. That cost this project five separate faults on the way to a working PSD, four of which
survived its own round-trip tests for the same reason: **a reader and a writer that share a mistake validate each other
perfectly**, and a check that is only this library reading this library's output is not a check. `PSD-REPORT.md` has the
list.

**Two of these three numbers were wrong before they were right, and both times the fault was in the experiment.**

* The first comparison divided a four-stroke demo sheet by a finished illustration, at a render scale that inflated a
  6.5-unit brush to 26 pixels -- past the width at which a run stops counting as a line. It reported "ink ratio 7x too
  sparse" and "strokes too thick", and both numbers were describing the setup.
* The second measured the model over four stroke *shapes* of one length, while the pressure model's speed effect is
  defined against each stroke's own length. Over a spread of lengths from 24 to 600 pixels -- what a drawing actually
  contains -- the spread the library shows appears, and the "model cannot produce a drawing's hierarchy" finding
  dissolved.

`taper_ratio` was reported as unresolved, and the investigation of it changed the model rather than the metric. Lowering
the taper **floor** (how thin the very tip gets) from 0.25 to 0.06 moved the measured ratio by nothing at any render
scale, which first looked like a broken metric. It is not: the floor touches only the first sample, and a run of pixels
cannot resolve that. What moves the profile is the taper **length**, and the length turned out to be wrong in its unit --
it was a fraction of the stroke's arc length, so one unchanged brush spent 6 px building pressure on a 40 px stroke and
640 px on a 4000 px one. Tapers are distances now, calibrated against a measured 丸ペン setting (see
`RESEARCH-LINE-QUALITY.md`), and the ratio moved from **0.4595 to 0.4372** over a rendered sheet of 60 strokes.

**The paragraph that used to sit here predicted this correctly**, and the prediction is worth keeping because the
measurement then confirmed it: *a whole-stroke statistic is dominated by the difference between strokes, not by the
shape of an end.* Measured on **one stroke in isolation** the same model reports **0.72-0.76** -- far above the corpus,
readable as "the tapers are far too shallow", and the exact opposite of the truth, because on a single long stroke the
thinnest fifth of the runs is mostly **full-width** runs. `taper_ratio` is only meaningful over a drawing. The remaining
0.437-against-0.421 gap is recorded rather than closed: lengthening the taper would close it, but the taper length is a
*measured* value and tuning a measurement to fit a confounded statistic is fitting the wrong way round.

1. Draw a sheet of strokes with **one** brush: a long line pressed from light through heavy and back, the same line
   drawn fast and then slow, a right-angle turn, a hairpin, and a tapered flick.
2. `python -m lineweight --fit sheet.png` prints the ink distribution.
3. Adjust `BRUSHES` until the model's distribution matches. The four effects in `pressures()` are the dials, and
   `lineweight.ref.check` is how you know when to stop -- but only for the metrics that actually respond to a change.

## Checking it, rather than believing it

**The library marks its own homework; `--judge` does not.** A project can be drawn a second time by **cairo**, which has
never heard of this library, and the two compared:

    python -m lineweight --judge draw.json          # both referees, with the numbers and their caveats

    A. filler    -- the same polygon points, two unrelated rasterisers
    B. offsetter -- outline() against cairo's stroker, per stroke, with the sharpest turn on that path

Referee B reports the sharpest direction change alongside every stroke **because the number is unreadable without it**:
agreement is expected while the path is smooth, and a disagreement at a reversal is the known invalid-loop problem
rather than a regression. A 90-degree corner *in the control points* is not a sharp turn -- the curve is smoothed
through it and the sampled turn is about 25 degrees.

`--audit` draws the same project through cairo with **each mark in its own colour**, after Metzger 2024 (CESCG)
Figure 5:

    python -m lineweight --audit draw.json --out audit.png
    python -m lineweight --audit draw.json --stage line --out lines.png
    python -m lineweight --audit draw.json --out detail.png --zoom 250,120,44 --pixels 760

**Why the colours are the point.** Visual similarity hides structure. A stroke that has merged into its neighbour, or
crossed itself into a pinhole, is two or three slightly-off pixels in an honest render and nobody would ever see it.
Painted its own colour it becomes **a hole in a solid field**, and a hole in a solid field is the one kind of defect
that cannot be mistaken for antialiasing. Hue steps by the golden angle so that any two strokes adjacent in draw order --
the only two that can touch -- are always furthest apart.

Output is byte-identical for the same input, including across processes, because "I looked at the render" is only
evidence if the render is the same thing next time.

`audit.py` needs `pycairo`. **The library does not**: cairo is imported at the point of use, and `import lineweight`
pulls in nothing but the standard library.

The measurement code has tests; the bridges cannot, because they need an application to be installed and driven. So the
checks live in `tests/tools/` and are run deliberately:

    python tests/tools/stress_inked.py     # inked_svg over real vector artwork: nothing lost, XML still valid
    python tests/tools/where.py            # do the weighted outlines land on the shape, or somewhere the transform left them
    python tests/tools/verify_all.py       # one end-to-end run per destination
    LW_CORPUS=... python tests/tools/run_corpus.py       # measure a corpus into a resumable library
    python tests/tools/add_corpus.py LIB.jsonl TAG DIR   # add a collection without re-measuring the rest

Each is a script rather than a test because each needs something this repository cannot supply: an Illustrator
installation, an Animate installation, a directory of artwork. Two of them are worth more than the library's own tests,
because what they check is the thing this project has got wrong most often -- **output that is well formed and wrong**.
`where.py` compares the box the outlines occupy against the box of the input geometry with its transforms applied;
`stress_inked.py` counts the elements that survived, because a pass that rebuilds a document deletes what it does not
understand and did exactly that once, taking a figure's eyes with it.

`--fit` and `--fit-dir` measure a drawing or a folder on the same scale as the reference library, so a sheet drawn by
hand can be read against `tests/data/corpus_summary.json` directly.

**The corpora are private and are not here.** They are collections of artwork, so what is shared is the distribution --
lengths and ratios -- and the code that produced it. The per-image measurements stay on the machine that made them, the
corpus directories are named by environment variable rather than in the source, and `.gitignore` refuses images,
archives and `.jsonl` outright, because a rule that depends on remembering is not a rule.

**A UI kit is not linework.** Several thousand PNGs from two game UI packs were offered to this library and are not in
it. A line-width distribution describes strokes, and a UI kit is filled rectangles, gradients and sprite-sheet slices;
measuring those describes the widths of nothing, and pooling them would move the targets in a direction that has nothing
to do with drawing. What that material would need is a different measurement -- corner radii, border weights, a palette
-- which is a different question from this one.

## Licence

MIT — see `LICENSE`.
