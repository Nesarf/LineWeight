# Prior art: raster → vector line art

`lineweight` is a raster-to-vector line art tool whether or not it says so: it takes a stroke, expands it into a shape,
and emits a path. This file records what else exists at that job, what the field has and has not managed, and which
parts of it this project is accidentally duplicating.

It did not exist before because the geometry work was absorbing all the attention. That is the wrong order -- the
question "has someone already solved this" should be asked before implementing, not after.

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

Every method surveyed -- learned and heuristic -- outputs curves with a **fixed stroke width**. Width is not a
parameter anywhere in the prior art reviewed here.

**`lineweight`'s entire output is variable width.** Pressure → width is the model, `stroke_record` carries `pressure` and
`brush`, and the line-hierarchy work in `RESEARCH-LINE-QUALITY.md` is about making width vary *by role*. The one
measured, published, perceptually-validated property of this material -- outline thickness controls the impression of
**potency** -- is the property no vectorizer models.

That is a genuine, unoccupied position, and it also explains why a raster trace was never going to be enough: a trace
recovers *where* the boundary is and throws away *how heavily it was drawn*, which is the part a viewer reads.

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
