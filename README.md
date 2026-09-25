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
  the path to both sides by half the local width and fill the result. This is the same operation a drawing
  application performs when a variable-width stroke is expanded, done here so the output stays plain SVG.
* **Whole-document inking.** `inked_svg()` walks an existing SVG and gives every shape large enough to be part of a
  silhouette a weighted contour, leaving small details alone. Extent decides, not a list of names, so a shape added
  later is inked without anybody remembering to.
* **Calibration.** `--fit` measures a real drawing's linework — the distribution of ink across rows and columns —
  which is the appearance a brush's curves have to reproduce.

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

## Calibrating to your own hand

1. Draw a sheet of strokes with **one** brush: a long line pressed from light through heavy and back, the same line
   drawn fast and then slow, a right-angle turn, a hairpin, and a tapered flick.
2. `python -m lineweight --fit sheet.png` prints the ink distribution.
3. Adjust `BRUSHES` until the model's distribution matches. The four effects in `pressures()` are the dials.

## Licence

MIT — see `LICENSE`.
