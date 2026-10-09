# Line quality for Japanese-style linework, collected

A survey of what the drawing side actually requires, kept separate from `RESEARCH-OUTLINE.md` (which is about geometry).
The reason this file exists: the geometry work was blocking, but the geometry is not what makes linework read as drawn.
The rules below are the ones this library does not implement at all, stated by people who teach the subject.

## The line-weight table

From [パルミー, 線画の描き方｜線の強弱・太さ](https://www.palmie.jp/lessons/263) -- a lesson by the illustrator
羽々倉ごし, and the clearest statement of the convention found so far.

| line | where | purpose |
|---|---|---|
| **thicker** | the outer contour; the **shadow side**; the **base of hair strands and cloth folds**; deep inside an overlap | silhouette, depth, shadow |
| **thinner** | the **lit side**; the inside of skin and cloth; fine hair tips; auxiliary lines that must not obstruct | brightness, softness, detail |
| **solid fill** (ベタ) | deep cast shadows; cloth linings; narrow places where parts overlap | tightens the picture, marks a strong shadow |

And the quantitative part, which is the sentence to build on:

> **線幅は固定値ではなく、同じ絵の中での相対差として決めます。**
> Line width is not decided as an absolute value but as a **relative difference within the same drawing** -- check that
> thick and thin are still distinguishable at reduced scale.

Concretely, from the same lesson: collarbones, knee bumps and the elastic band of thigh-highs are *inner* lines and go
thin; the outer contour, and the boundary between thigh and thigh-high, go thick. Making only the contour thick reads as
**deformed** -- which is the chibi/ sticker look, useful and deliberate, not an accident.

**This library has one brush per stroke and no notion of a line's role.** Every line is drawn by whatever brush the
caller passed. That is a large part of why the output reads flat, and it is not a geometry problem.

## The five-item checklist

The same lesson ends with a checklist for a finished line drawing. Four of the five are measurable, and two of those are
measurable with code this library already has:

```
[ ] is there a difference between outer and inner line width?
[ ] is the shadow side stronger than the lit side?
[ ] is the overlap of hair and clothing readable?
[ ] are there no gaps that would leak when the drawing is filled?
[ ] at reduced scale, are the focal points (the face) not buried under line?
```

* **outer vs inner width** -- split the strokes by role and compare the two width distributions. Needs the role model.
* **leaking gaps** -- `weld_endpoints()` and `region_fill()` in this library already address exactly this, for a
  different purpose.
* **reduced scale** -- render the outline at 25% and measure whether the width differences survive.
* **shadow side vs lit side** -- needs light direction as an input, which the document model does not have.

## Two construction rules that are directly encodable

**Eyelashes are drawn by overlapping lines, not by filling black.**

> まつ毛は、線を重ねるようにして描くと、毛が密集しているような感じが出せます。
> Draw lashes as *overlapping strokes* and you get the sense of dense hair; filling them solid black does not look right.

That is a stroke-generation rule: not one heavy line, but several coincident lighter ones. Cheap to implement on top of
`stroke_record`, and it is the kind of detail that separates drawn-looking from plotted-looking.

**Draw the body under the clothes.**

> 服で隠れる部分も、体の線を描いておく -- draw the hidden parts of the body too, because it makes the clothing easier
> to fit and makes errors in the underlying drawing visible.

This is the structural answer to the complaint that started this project: **2.5D construction works outside-in, and 2D
moe construction works inside-out.** A silhouette traced from a projected model has no interior structure to hang
clothing on, which is why the result reads wrong in a way that is hard to name. The fix is a construction order, not a
rendering technique.

## Outside confirmation of this library's design

CLIP STUDIO PAINT's vector layer is described as holding

> 線の中心線と制御点、ブラシサイズなどのストローク情報
> the stroke's centreline, its control points, and brush size

which is what `stroke_record` already stores (`centre`, `control`, `pressure`, `brush`, `resolution`, `seed`). The
decomposition this library arrived at independently matches what a production drawing application keeps, which is the
strongest evidence so far that the record is the right abstraction to build the missing layers on.

## Where the construction knowledge lives

* [Sketching Manga-Style Vol. 1](https://archive.org/download/SketchingMangaStyleVol.1SketchingToPlan/Sketching%20Manga-Style%20Vol.%201%20-%20Sketching%20to%20Plan.pdf)
  -- construction method, free on the Internet Archive
* Imagine FX, *Manga: The Ultimate Guide to Mastering Digital Painting* -- workflow from skeleton to finish
* [How to Draw Anime Body Proportions](https://jerwoodvisualarts.org/blog/how-to-draw-anime-body-proportions/) -- the
  head-as-measurement-unit convention
* A thesis on anime body proportions describing the stylisation explicitly (long limbs, thinned bodies, a Japanese beauty
  model rather than anatomy) -- the useful part is that it is stated as *convention*, which is what makes it encodable

None of this is code. It is the material for a construction layer, and it is the actual ceiling on this project's output
quality.
