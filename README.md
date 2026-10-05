# lineweight

Vector linework with weight, for the case where there is no tablet.

A stroke in SVG has one width from end to end, which is why vector drawings read as diagrams next to drawings made
by hand. `lineweight` models the thing a tablet measures — pressure — and expands each stroke into a **filled
outline** whose width varies along it, so plain SVG can carry line weight without any dependency on a drawing
application.

It exists because a language model asked to draw has no hand. Pressure cannot be felt, so it is computed from what is
observable about a line, and the numbers can be calibrated against real artwork rather than guessed.

## What it does

**What it does**

* **Four brushes** (`fine`, `ink`, `pencil`, `wash`), each the same set of numbers a paint program exposes: width,
  opacity, dab spacing, and jitter, plus two taper curves.
* **A pressure model.** Pressure follows four effects that a real stroke shows: it is lighter when the stroke is
  moving fast, lighter through a sharp turn, tapered at both ends of an open stroke, and drifting slowly underneath.
  Closed contours are walked once and never tapered, because a loop has no ends to taper.
* **Stroke to outline.** SVG cannot vary a stroke's width, so the width profile is expanded into an outline — offset
  the path to both sides by half the local width and fill the result. This is the same operation a drawing
  application performs when a variable-width stroke is expanded, done here so the output stays plain SVG.
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

**It is not an automation bridge into a paint application.** Most of them expose no scripting interface at all, and
those that do expose a different one each; a tool that claims otherwise is a tool that will break. What is portable
is the *model* of pressure and the *measurement* of a real drawing — so the workflow is: draw a test sheet in
whatever program you have, at whatever pressures you can control, and fit the brushes here to it.

**It is not a renderer and not a drawing program.** It produces path data. What you fill it with is your business.

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

**What is measured, and what is not.** Illustrator 28.5 runs a generated script from a command line and returns the
drawing with its layers, fills and opacities intact, verified by reading back the SVG Illustrator itself exported --
including that `ExportType.SVG` is the working constant and `ExportType.SVGFORMAT` does not exist in that build. The
PSD writer's output is verified by walking its own bytes back out: layer names, dimensions, channel layout and the
merged image. **Whether SAI accepts the PSD is not verified** -- SAI has no scripting interface and no reliable
signal here that it has loaded a file, so the claim stops at the format. Animate opens a hand-written XFL as a
document, which is verified, but **the content does not import**, and that is unresolved; see `lineweight/xfl.py`.

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

What the measurement says about the current model, on 26 line drawings from a 75-image library. The numbers are
**ratios of one length to another inside a single drawing**, which is the only kind of comparison that survives two
pictures being different sizes:

| | reference, inside one drawing | the model | verdict |
|---|---|---|---|
| `p90/median` -- a few heavy lines among many light ones | 2.75 | 2.67 | close: the model does produce a drawing's spread |
| `max/median` -- how far the heavy end reaches | 5.33 | 5.33 | equal |
| `taper_ratio` | 0.41 | 0.50 | unresolved -- the whole-stroke statistic cannot see an end; see below |

**Two of these three numbers were wrong before they were right, and both times the fault was in the experiment.**

* The first comparison divided a four-stroke demo sheet by a finished illustration, at a render scale that inflated a
  6.5-unit brush to 26 pixels -- past the width at which a run stops counting as a line. It reported "ink ratio 7x too
  sparse" and "strokes too thick", and both numbers were describing the setup.
* The second measured the model over four stroke *shapes* of one length, while the pressure model's speed effect is
  defined against each stroke's own length. Over a spread of lengths from 24 to 600 pixels -- what a drawing actually
  contains -- the spread the library shows appears, and the "model cannot produce a drawing's hierarchy" finding
  dissolved.

`taper_ratio` is reported as unresolved rather than as a discrepancy, and the reason is worth stating because it
changed twice while being investigated. Lowering the taper **floor** (how thin the very tip gets) from 0.25 to 0.06
moved the measured ratio by nothing at any render scale, which first looked like a broken metric. It is not: the floor
touches only the first sample, and a run of pixels cannot resolve that. What does move the profile is the taper
**length** -- a longer taper keeps more of the stroke below full width -- and that does move the statistic. So the
instrument works, and the honest position on the 0.41-versus-0.50 gap is that the tapers need to be measured over the
end regions specifically before anyone tunes against it; a whole-stroke statistic is dominated by the difference
between strokes, not by the shape of an end.

1. Draw a sheet of strokes with **one** brush: a long line pressed from light through heavy and back, the same line
   drawn fast and then slow, a right-angle turn, a hairpin, and a tapered flick.
2. `python -m lineweight --fit sheet.png` prints the ink distribution.
3. Adjust `BRUSHES` until the model's distribution matches. The four effects in `pressures()` are the dials, and
   `lineweight.ref.check` is how you know when to stop -- but only for the metrics that actually respond to a change.

## Licence

MIT — see `LICENSE`.
