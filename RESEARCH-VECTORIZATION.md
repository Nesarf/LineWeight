# Prior art: raster → vector line art

`lineweight` is a raster-to-vector line art tool whether or not it says so: it takes a stroke, expands it into a shape,
and emits a path. This file records what else exists at that job, what the field has and has not managed, and which
parts of it this project is accidentally duplicating.

It did not exist before because the geometry work was absorbing all the attention. That is the wrong order -- the
question "has someone already solved this" should be asked before implementing, not after.

---

## Why the output has to be a filled outline

Before the prior art on *how* to vectorize, the reason vectorizing is necessary at all -- and it is not a preference.

**SVG cannot express a variable-width stroke.** There is a W3C proposal,
[Variable_width_stroke](https://www.w3.org/Graphics/SVG/WG/wiki/Proposals/Variable_width_stroke), whose simplest form
would be "allowing a 'start' and 'end' width and smoothly adjusting along the path". Its status, as answered by its own
author **Brian Birtles** when asked in September 2024
([thread](https://lists.w3.org/Archives/Public/public-svg-issues/2024Sep/0000.html),
[reply](https://lists.w3.org/Archives/Public/public-svg-issues/2024Sep/0001.html),
[w3c/svgwg#953](https://github.com/w3c/svgwg/issues/953), since closed):

> It looks like that was my proposal and … it was discussed at the 2013 Tokyo F2F. I then updated the proposal in
> September. **I don't know if it was ever discussed after that.** (I notice the polyfill is broken too because we
> deprecated several SVG path APIs.)
>
> I think since that point **browsers have been investing less in new SVG features** for various reasons. I believe I
> might also have received feedback offline that **adding primitives not natively supported by underlying graphics
> libraries would be a significant hurdle for many implementations.**

**Last action: 2013. Reason it died: the layer underneath cannot do it either.** cairo, Skia, CoreGraphics and Direct2D
all stroke at a constant width. A variable-width stroke in SVG would therefore not be a new attribute on an existing
primitive -- every implementer would have to build a new primitive from nothing.

So the stack is closed at the bottom:

```
cairo / Skia / CoreGraphics / Direct2D   →  constant-width stroke only
        ↓  therefore
SVG                                      →  no variable-width stroke (proposal dead since 2013)
        ↓  therefore
the only expressible form is            →  expand the centreline into a filled outline
```

**That is what `lineweight` does, and it is not a workaround.** There is no other form the output could take. It also
explains the incident that started this section: the developer who filed the issue was *"trying to 'fake' variable width
lines using `fill`"* -- the same operation, arrived at independently, by someone who had no reason to care about line
quality at all and only wanted the file to be correct.

**Two consequences worth carrying.**

The claim in the section below -- that no vectorizer in the literature models width -- is **not an oversight by that
field**. It is downstream of the format. There is nowhere to put the width, so the width is dropped, and the entire
research programme inherited a fixed-width output because the container has no field for anything else. `lineweight` is
not competing with those methods on their axis; it is producing a different kind of object -- a *shape* that carries the
width inside it, which is legal SVG and therefore works everywhere, including in Illustrator, Animate and SAI.

And it sets a constraint on the verification plan: **the underlying rasterisers stroke at constant width too**, so
cairo cannot stroke a reference for a tapered line. That is the same limitation noted in `TODO.md` under P0 -- cairo is
usable as a referee for a *uniform* stroke, and for a tapered one the comparison has to be against
`cairo_fill` of an independently produced outline, not against `cairo_stroke`.

## The formal line taxonomy, and the drawing convention it matches

From **Line Drawings from 3D Models**, SIGGRAPH 2005 Course 7 -- Szymon Rusinkiewicz (Princeton), Doug DeCarlo
(Rutgers), Adam Finkelstein (Princeton)
([course intro](https://gfx.cs.princeton.edu/proj/sg05lines/course7-1-intro.pdf)):

> We will mathematically **define** lines such as **silhouettes, contours, suggestive contours, and ridges and
> valleys**. We describe algorithms for finding them efficiently, discuss methods of stylization…

This is the computational counterpart of the drawing convention in `RESEARCH-LINE-QUALITY.md`, and the two line up:

| 2D drawing convention | formal term | what it is |
|---|---|---|
| 輪郭線 (outer contour) | **silhouette** | where the surface turns away from the viewer |
| 内部線 (interior line) | **contour** | a depth or orientation discontinuity -- an occlusion edge |
| 陰影線 (shadow / form line) | **suggestive contour** | where the surface is about to turn away; the line an artist draws to imply form that the silhouette does not show |
| -- | **ridge / valley** | extremal curvature |
| -- | **apparent ridge** | view-dependent ridge, defined to match where artists actually put lines |

**Why this matters for the line-hierarchy model in `TODO.md`.** The drawing convention says which lines get thicker
(*"the outer contour; the shadow side; the base of hair strands"*) but gives no way to *compute* which line is which.
The NPR taxonomy says exactly that, and it is defined on a surface -- which means it is computable from a mesh and, more
importantly here, **checkable against a drawing**. A proposed 輪郭線 can be tested for whether it actually lies on a
silhouette.

**The bridge between the two is the thing this project is missing**, and it is the same bridge the original complaint
was about: 2.5D modelling produces silhouettes and nothing else, which is why it *"looks unintentional"* -- a mesh has
no 内部線 and no 陰影線 unless something computes them, and the moe convention's most characteristic lines (eyelashes,
hair masses, cloth folds) are largely **suggestive** rather than silhouette.

Also relevant, not yet read: **Apparent Ridges for Line Drawing** (Judd, Durand, Adelson, MIT),
[PDF](http://www-bcs.mit.edu/pub_pdfs/ApparentLines.pdf) -- and a study titled *The relative effectiveness of line
drawing algorithms at depicting 3D shape*, which is an **empirical** comparison of which line types actually convey
form. That is the question "which lines should exist" asked as an experiment rather than a convention, which is the same
move KEER2014 made for thickness.

---

## The paper that states this project's problem as a research question

**Semantically Meaningful Vectorization of Line Art in Drawn Animation** -- Calvin Metzger, supervised by Michael Wimmer,
TU Wien, Faculty of Informatics. CESCG 2024 (28th Central European Seminar on Computer Graphics), non-peer-reviewed.
[PDF](https://cescg.org/wp-content/uploads/2024/04/Metzger-Semantically-Meaningful-Vectorization-of-Line-Art-in-Drawn-Animation.pdf)

### The problem statement

> the resulting line-art vector image needs to be **semantically meaningful**, i.e., the arrangement, topology and
> parameterization of graphical primitives (i.e., Bézier curves) need to make sense and be **close to how artists would
> draw**

That is the criterion this project has been reaching for without naming. It is **not** visual similarity -- a raster
trace can be pixel-accurate and still be useless, because the curves do not correspond to strokes. It is whether the
vector structure is the structure an artist would have produced.

### The reason the problem is hard, stated precisely

> Since there is a **non-injective relation** between vector images and raster images, converting a raster image into a
> vector image is a non-trivial task.

Many different vector images rasterise to the same pixels. Nothing in the raster says which one it was. Every method
below is a different guess at resolving that ambiguity, and the ambiguity is exactly where "looks right" and "is right"
come apart.

### Where it sits in production

The hand-drawn limited-animation pipeline, four phases: storyboard → rough keyframes (line drawings for critical
moments, mostly cels) → **rough keyframes cleaned of spurious lines and obsolete text markers, then vectorized** →
in-betweens drawn, then coloured with backgrounds. Vectorization is a real, tedious, human step in the middle of that
pipeline. This is not an academic problem.

### Method

Iterative reconstruction, designed on one principle -- *"reducing the complexity of the task the model needs to solve
increases the probability that the model actually converges"*:

```
t=0   identify a curve, place a marker pixel on it
      └─ learned marked-curve reconstruction model
         input:  line-art raster + one marker pixel (image is centred on the mark,
                 so the curve's location is given, not searched for)
         output: cubic Bézier parameters (start, end, 2 controls = 8 floats)
                 with a FIXED STROKE WIDTH
      └─ draw onto canvas
t+1   the canvas is taken into account when picking the next curve
```

Dataset from **Tonari Animation**, a working studio. Baselines compared: AutoTrace [19], Egiazarian et al. [3],
Puhachov et al. [12], Mo et al. [10].

### Result

> while the proposed method outperforms prior work at the default input image resolution, ultimately **no line-art image
> vectorization method is able to satisfactorily vectorize clean animation frames**, especially failing to properly
> reconstruct details and **primitives with high curvature**. Hence, **no method studied in this work is of practical use
> in the limited-animation workflow.**

Stated advantages of their method: robustness to input resolution and binarization, resource efficiency, flexibility for
manual fixing. Stated limitations: *"a significant amount of small holes in reconstructed curve sequences, limited
semantic correctness and a **bias towards lower curvature**."*

---

## Why high curvature is the whole story

Metzger's survey says every method fails on **high curvature**. This project's outline work found, independently and in a
different formalism, that at tight curvature the offset curves cross, the resulting loops wind against their neighbours,
and under `nonzero` fill they cancel into **pinholes** -- the literature term is **invalid loop**, and loop removal is
the expensive step (a raw offset is O(n); the repair dominates). The reverted experiment that tested every outline point
for coverage took the hole count from 13 to **175**, because the coverage test also fires on the inside of ordinary
curves.

Two arrivals at the same wall from opposite directions: a learned vectorizer that is *biased towards lower curvature*,
and a geometric offsetter that produces invalid loops at high curvature. **High curvature is the shared failure mode of
this problem domain**, and it is not a bug in either implementation.

Metzger's own limitation list -- *"small holes"* -- is the same defect as this project's pinholes. That is worth knowing
before spending more time on it: the pinhole problem is not a local oversight, it is the field's open problem.

## The gap this project actually occupies

**Correction to an earlier claim in this file.** An earlier version of this section said *"width is not a parameter
anywhere in the prior art reviewed here"*. That was **too strong, and wrong** -- it generalised from the vectorization
literature, which is one community, to the whole field, which is not. The annotated bibliography from the Princeton 2005
course ([course7-3-bib.pdf](https://gfx.cs.princeton.edu/proj/sg05lines/course7-3-bib.pdf), ~50 kB, 1967-2005) shows
width modulation is an **established technique in NPR**, with at least six precedents:

| paper | width driven by |
|---|---|
| **Elber 1995b** | **depth** -- *"performing depth cuing by modulating line width and intensity, drawing thin light strokes for background lines"*, plus trimming background lines near intersections |
| **Winkenbach 1996** | **proximity to other lines** -- controlled-density hatching where width follows line spacing |
| **Hamel 1998** | **occlusion** -- transparency shown *"by modifying line width, density, or style for occluded surfaces"* |
| **Kindlmann 2003** | **estimated curvature** -- contour thickness controlled by curvature, ridges and valleys emphasised by thresholding principal curvature |
| **Sousa 2003a** | **surface curvature** -- mesh edges selected as strokes, *"drawn with width modulated by surface curvature"* |
| **Sousa 2003b** | full pipeline: extracts silhouettes, boundaries, ridges and valleys, chains lines, **fits curves to paths**, and renders paths *"sparsely with varying line width"* |

**So the honest position is narrower, and more interesting.** Width modulation in NPR is real, mature, and always driven
by a **geometric quantity** -- depth, occlusion, curvature, line density. What is not present in any of it is width
driven by **perceptual role**: the 輪郭線 / 内部線 / 陰影線 hierarchy, and the measured potency-versus-naturalness
trade-off from KEER2014. NPR asks *"what does the geometry say this line's width should be"*; the drawing convention
asks *"what should this line's width be so the picture reads right"*. Those are different questions, and only the first
one has been automated.

**And the vectorization literature is a separate community that drops width entirely** -- which is downstream of the
format (see the SVG section above: there is nowhere to put a width). So the two halves are split: NPR has width but
works from **meshes**, vectorization works from **rasters** but has no width. `lineweight` is raster-input *and*
width-carrying, which is the gap between them.

**What `Sousa 2003b` shows is that the pipeline shape is not novel.** Extract lines, chain them, fit curves to paths,
render with varying width -- that is exactly this library's shape, published in 2003 from mesh input. Worth knowing
before claiming the architecture as a contribution. The contribution available here is the **input** (raster, not mesh)
and the **width driver** (role and pressure, not curvature), not the sequence of stages.

Also of note, since `stroke_record` carries a `seed`: **Kalnins 2003** maintains frame-to-frame temporal coherency for
stylized silhouettes *"by propagating line stroke parameterizations between frames"* -- the same problem a seed solves,
solved by propagation instead. Relevant if this ever animates.

## A verification technique worth stealing

Metzger's Figure 5 compares five methods by rendering each one's output with

> each curve … represented with a **mutually exclusive color** and a **high zoom level**

so the vector structure behind the image is visible. Visual similarity is invisible at normal zoom; the structure is
only legible when every primitive is separately coloured.

**This is the cheapest independent check available for `stroke_record`.** Render each recorded stroke in its own colour
at high zoom and the topology is either right or visibly wrong -- strokes that merge, self-cross, or loop. No app, no
bridge, no human judgement call, and it is the same discipline that has been missing throughout: an artifact that can
disagree with the code.

It also belongs with the P0 cairo self-render, since both need the same rasteriser.

## Topology fact worth keeping

> clean animation frames are not noisy and the curves are more narrow and densely connected, **forming one large
> connected component** for curves.

Clean line art is **one connected component**, not a set of independent strokes. This constrains stroke grouping: a
grouping that produces many disconnected islands is wrong for this material, and it explains why
Puhachov et al. [12], which targets **scanned pencil drawings** where connectivity is broken by noise, is solving a
different problem than the one here.

---

## The prior-art map

| method | family | approach | why it is not enough |
|---|---|---|---|
| **Potrace** [15], **AutoTrace** [19] and other heuristic optimizers [11, 1, 21] | heuristic | polygon/curve fitting with optimization | primitives **rarely resemble what an artist would draw**; require **manual hyperparameter tuning per image**; assume a specific resolution, low noise, or only specific junctions |
| **Im2Vec** [13] | learned | CNN encoder + RNN decoder emitting a sequence of Béziers; trainable **without vector supervision** via a differentiable rasteriser | pixel resolution fixed at training time; does not scale to high resolution; sometimes emits degenerate and semantically useless parts |
| **Mo et al.** [10] | learned | iterative, quadratic Béziers only, differentiable canvas | trained mainly by perceptual loss on the whole image, so *"the results are not semantically meaningful"* |
| **Puhachov et al.** [12] | hybrid, current SOTA | learned ensemble detects curve **keypoints** (junctions, endpoints, corners), geometric flow finds connections and geometry | *"remarkably good"* but narrower aim: preserves **stroke connectivity in noisy scanned pencil drawings**. Clean animation frames are not noisy and form one large connected component |
| **Egiazarian et al.** [3] | learned | Transformer over image tiles; physics-inspired refinement aligned to black pixels | constrained to **10 curves per image** before tiling |
| **Metzger** (this paper) | learned, iterative | one marked curve at a time, cubic Bézier + fixed width | beats prior work at default resolution and is up to **4.5× faster** than the second-fastest learned method -- and still not usable in production |

**Reading of the map**: heuristics fail on *semantic* grounds, learned methods fail on *curvature and resolution*, and
the hybrid SOTA is aimed at a different input distribution. Nobody has the problem solved, and the paper says so
explicitly rather than rhetorically.

**What this means for expectations**: any claim that `lineweight` produces production-usable vector line art from a
raster is a claim that the field has not met. What it can honestly claim is narrower and still worthwhile --
variable-width stroke records with explicit pressure and role, which is the axis nobody else is on.

---

## References

1. Bessmeltsev & Solomon -- vectorization (foundation for [12])
2. Bhunia, Chowdhury et al.
3. Egiazarian, Voynov, Artemov et al. -- technical drawings via Transformer
6. Johnson, Alahi, Fei-Fei -- perceptual loss
8. Li, Lukáč, Gharbi, Ragan-Kelley -- differentiable vector graphics
10. Mo et al. -- iterative differentiable vectorization, quadratic Béziers
12. Puhachov, Neveu, Chien et al. -- keypoints + geometric flow
13. Reddy -- Im2Vec, vector graphics without vector supervision
15. Selinger -- **Potrace**, polygon-based
17. Wang, Lv, Yu et al. -- CogVLM (cited as future work: finetune a large VLM instead of a small encoder-decoder)
18. Wang & Lian -- DeepVecFont
19. Weber -- **AutoTrace**, 2002
21. Zhang, Liu, Li, Wu et al.
