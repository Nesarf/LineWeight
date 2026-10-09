# Scenery and isekai architecture, collected

The second direction this library is for, alongside Japanese-style character work. Kept separate from
`RESEARCH-LINE-QUALITY.md` because the requirements are genuinely different and one of them contradicts an assumption
this library was carrying.

## What the target actually is

Measured against the reference set at `F:\素材\图\固态景色\ACG建筑` (20 images, 69 MB). The first one:
an isekai city -- half-timbered houses below, gothic spires and a castle above, a dramatic cumulus sky, a girl with a
parasol in the foreground.

**It is painted, not drawn.** There is almost no line art in it. The forms are carried by value and colour masses, and
line appears only in small areas -- window frames, roof tiles, timber framing. This matters because it changes what this
library's role in scenery is:

* lineweight is **not** going to produce a finished background by itself, and aiming at that would be aiming at the wrong
  thing;
* what it can produce is the **underdrawing**: perspective construction and detail linework, which is a real stage that
  painters do use;
* the calibration in `corpus_summary.json` was fitted to **line drawings**, so it says nothing yet about scenery. That
  reference set is a separate corpus and has not been measured.

## A warning that applies directly to this library

From the perspective course handouts at [janica.jp](https://www.janica.jp/course/perspective/history02_handout.pdf):

> 先にパースの線だけ描いて、それに無理矢理合わせてキャラや背景を描こうとすると失敗しがち
> Draw only the perspective lines first and then force the character and background to fit them, and you tend to fail.

This is the obvious thing to build -- generate a grid, draw to the grid -- and it is the thing that does not work. The
grid is a checking device, not a construction method. Worth writing down before a `perspective_grid()` helper makes the
wrong workflow easy to reach for.

## The perspective grid is cheap to generate, and the math is short

An Inkscape extension, [`cds4/inkscape-grids`](https://github.com/cds4/inkscape-grids)
(`grid_perspect2.py`, GPL, Carl Sorensen), draws a two-point grid. **It does not need Inkscape for the geometry** -- the
whole of the interesting part is trigonometry, and it reimplements in about fifteen lines with no dependency:

```python
# two vanishing points on a horizon; every vertical is where a left ray meets a right ray
def perspective_intersection(left_theta, right_theta, left_x, right_x, horizon):
    r = (right_x - left_x) / (sin(right_theta) / tan(left_theta) - cos(right_theta))
    return right_x + r * cos(right_theta)
```

The rest of the extension is ray-vs-bounding-box trimming and grouping, both of which this library already has in another
form (`path_extents`, layer groups). So a `perspective_grid(horizon, left_x, right_x, divisions)` producing SVG groups --
one per family of lines, which is what the extension does with `LeftPointGridlines` / `RightPointGridlines` /
`VerticalGridlines` -- is a small addition rather than a project.

Two other generators found, unexplored:
[`nattyboyme3/five-point-perspective`](https://github.com/nattyboyme3/five-point-perspective), and the perspective
posts at [artcoded.fr](https://artcoded.fr/posts/20260222-cubes_perspective/).

## Construction references

| source | what it is |
|---|---|
| [世界觀與場景美術的建構技法](https://www.tenlong.com.tw/products/9786263384842) | a Japanese book on constructing world-view and scene art, in Chinese translation -- concept-to-design method rather than technique |
| [Proko, Designing Large Scale Environments](https://www.proko.com/course-lesson/designing-large-scale-environments/) | large-scale environment design |
| [SAI x Photoshop 背景レッスン](https://www.shokokusha.co.jp/pdf/4-395-00478-4.pdf) | background work specifically in **SAI**, which is a destination this library already writes to |
| [CLIP STUDIO TIPS: manga backgrounds from 3D models](https://tips.clip-studio.com/fr-fr/articles/11245) | the 3D-proxy workflow -- and the source of the "2.5D" look that this project exists to avoid |
| 建物パース course handouts, [janica.jp](https://janica.jp/course/perspective/history06_handout.pdf) | free Japanese perspective course material |

## What this direction needs from the library

1. **Perspective construction** as data, not as a bitmap -- so a grid can be a layer, and so vanishing points can be
   moved after the fact. Cheap, see above.
2. **Detail linework at a different scale from character linework.** Windows and roof tiles are drawn at a fraction of
   the width used for a character's contour, and the line-weight table in `RESEARCH-LINE-QUALITY.md` does not cover
   architecture at all -- its rules are about bodies and cloth.
3. **A separate calibration corpus.** The existing one is line drawings of figures; the reference set here is painted
   scenery, and the two distributions are not comparable. Measuring them against each other would be the mistake of
   dividing incomparable scales that this project has already made once.

## Measuring the three reference sets, and a trap in the numbers

`lineweight --fit-dir` run over each set separately. The same measurement, three kinds of artwork:

| set | images | ink fraction | width median | width p90 | taper ratio |
|---|---|---|---|---|---|
| the line-drawing library | 276 | **0.1485** | 4.0 | 11.0 | **0.4213** |
| `F:\素材\图\16+`, illustrations only | 14 | 0.3429 | 5.0 | 13.0 | 0.3811 |
| `F:\素材\图\固态景色\ACG建筑` | 20 | **0.6290** | 5.0 | 13.0 | 0.3564 |

**Ink fraction and taper ratio move with how painted the work is** -- 0.149 to 0.629, and 0.421 down to 0.356. That is
the expected direction and it is a useful signal for telling the three kinds of artwork apart.

**Width median and p90 barely move, and that agreement is a trap.** The metric is valid -- drawn lines of 2, 4, 8 and
16 pixels measure as 2.0, 3.0, 8.0 and 16.0, checked directly with Pillow, so it responds correctly to the parameter it
is supposed to measure. But `ref.py` classifies runs wider than 16 pixels as *area* and excludes them, so on a painted
image the surviving "line-like" runs are not lines at all: they are the smaller dark features -- shadow edges, texture,
detail -- and those happen to be 4 to 16 pixels across. **Two sets agreeing on this number does not mean their linework
agrees; it means their small dark features are a similar size.**

This is the same shape of mistake as the four retracted PSD claims: a metric that produces a number, agrees across cases,
and means something different in each. The comparison that *would* be meaningful is lineart against lineart. Against
painted work the only sound use of these figures is as a classifier for which corpus a file belongs to.

Also worth recording: the `16+` folder is **mixed** -- Pixiv illustrations, phone photographs and screenshots in one
directory. Pooling photographs with drawings would corrupt any corpus they were added to, and the 25-image figure is not
25 drawings. The 14 illustrations were separated out above for that reason; the photographs were not measured.

## The moe target, and it validates the calibration

`F:\素材\图\碧蓝档案官方设定资料` -- 292 scanned pages of *Blue Archive Official Artworks*, 223 MB. Sampled every 20th page
(15 images) and measured:

| set | ink fraction | width median | width p90 | taper ratio |
|---|---|---|---|---|
| the line-drawing library (276) | 0.1485 | 4.0 | 11.0 | 0.4213 |
| **Blue Archive official artworks (15)** | **0.1901** | **4.0** | **12.0** | **0.3923** |
| `16+` illustrations (14) | 0.3429 | 5.0 | 13.0 | 0.3811 |
| `ACG建筑` (20) | 0.6290 | 5.0 | 13.0 | 0.3564 |

**This is the first comparison where agreement means something.** The artbook sits next to the line-drawing library and
far from the other two, and unlike them it genuinely contains linework -- the pages are full-colour illustrations with
visible, weight-varying lines over cel shading, not painted masses. Ink fraction 0.19 against 0.15 is the colour content a
finished illustration has and a line drawing does not; width median is identical, p90 is within one pixel, taper within
seven per cent.

**So the existing calibration -- 276 line drawings, `p90/median` 2.750 -- is suited to this target**, which was an
assumption until now rather than a measurement. And these are the numbers to aim at for moe character work:

```
width median 4 px · width p90 12 px · taper ratio 0.392 · ink fraction 0.190
```

Two things this does not say. It does not say the output *looks* like Blue Archive -- every measure here is a
distribution over ink runs, and nothing in this file measures rhythm, curvature, line confidence or overlap hierarchy. And
the sample is 15 pages of 292, chosen by stride rather than at random, so the page mix is whatever the book's ordering
happens to put at those positions.

A structural note for whoever keeps this: the reference library now contains **three corpora that must never be pooled** --
clean line drawings, full-colour illustrations, and painted scenery. `--fit-dir` currently treats them identically, so the
next thing worth building is not more geometry but a **classifier that decides which corpus a file belongs to** before any
statistic is computed on it. Without that, the trap described above recurs by default.

## Correction: the calibration corpus is this artbook, and "linework" does not mean line art

Two things established by looking rather than by assuming, and the second one weakens a claim made earlier in this file.

**The corpus source is identified.** `F:\素材\图\碧蓝档案官方设定资料` holds three subdirectories -- `1` (292), `2` (321),
`3` (316) -- for **929 files in total**, which is exactly `/totals/records` in `tests/data/corpus_summary.json`. The
summary's own note says the images and their paths are deliberately not in the repository, which is why this was not
obvious from the file alone. So the "line-drawing library" of 276 is **276 pages of this set**, and the comparison
recorded above between it and a 15-page stride sample of volume 1 is **not target-versus-calibration -- it is two subsets
of one book.** That comparison still says something real (within a single artbook, the full-colour pages and the sparse
ones measure differently) but it says much less than "the calibration is suited to the target", which is how it was first
written.

**And the split was made by a threshold, not by looking:**

```python
linework = [r for r in good if r['note'] == '' and r['line_runs'] >= 200 and r['ink_ratio'] < 0.30]
paintings = [r for r in good if r['note'] == '' and r['ink_ratio'] >= 0.30]
```

**Full-colour illustration pages pass that test.** The 15-page sample measured `ink_ratio` 0.1901 and was drawn from the
full-colour section of volume 1 -- comfortably inside the "linework" band. So **the 276 are not line drawings; they are
pages that happen not to be ink-heavy**, and that set will contain finished colour illustrations alongside actual line art.
Every figure in `corpus_summary.json` is a distribution over that mixed set.

This does not make the calibration wrong. It makes it **a measurement of a different thing than its name says**, and that
matters for the three comparisons in this file, all of which treated "the line-drawing library" as a clean reference. It
is the same failure mode the retracted PSD claims had: a number computed correctly, named confidently, and describing
something other than what the name implies.

**What a real classifier would need to test**, now that the material is known: monochrome-ness (the Blue Archive artbook
separates cleanly -- line pages are greyscale scans, illustrations are saturated), which is a different signal from ink
ratio and would not admit a finished colour illustration into a linework corpus.

## Instead of classifying the pages, extract the line art from them

The previous section ends with a problem: the calibration corpus is 276 artbook pages selected by `ink_ratio < 0.30`,
which admits finished colour illustrations, and a better test (monochrome-ness) would only separate them -- it would not
give more line art. Searching for how this is done elsewhere found a better answer than a classifier: **the line art can
be extracted from the illustrations, which removes the need to decide which pages are "linework" at all.**

Tools that do this, in descending order of how directly they apply:

* **`control_net_lineart_anime`** -- the anime line-art annotator, in the diffusers tooling
  ([source](https://huggingface.co/diffusers/tools/blame/5f12b415568572b0746b1e3ee96dc5f5ebceefaf/control_net_lineart_anime.py)).
  Purpose-built for exactly this material, and the standard tool for it in the ControlNet ecosystem
  ([annotator overview](https://deepwiki.com/lllyasviel/ControlNet-v1-1-nightly/2.4-line-art-annotators)).
* [`lineartization`](https://pypi.org/project/lineartization/) -- a packaged line-art extractor.
* [`bloc97/SYNLA-Dataset`](https://github.com/bloc97/SYNLA-Dataset) and
  [`SYNLA-Plus`](https://github.com/bloc97/SYNLA-Plus) -- synthetic line art generated from photographs, i.e. a ready-made
  large corpus with known-good line art rather than an extraction problem at all.

**Why this is worth more than a classifier for the immediate problem.** All 929 pages become usable rather than 276 being
guessed at, the result is line art *by construction* rather than by threshold, and the extraction is repeatable so the
corpus can be rebuilt when the method improves. The cost is honest and should be stated before anyone starts: these are
**neural models with heavyweight dependencies**, so they belong in the corpus-building step and never in `lineweight`
itself, which is deliberately stdlib-only and must stay that way. A corpus is data; the library that consumes it should
not inherit a deep-learning stack.

**What this still does not settle**: extracted lines are the extractor's opinion of where the lines are, and a thinner or
thicker extraction shifts every width statistic built on top of it. So the extraction has to be validated before the
numbers mean anything -- which is the same discipline the outline work needed, and the reason a cairo-rendered reference
was proposed there.

Also found, not yet read: [TuringSketchLine](https://ieee-dataport.org/documents/turingsketchline-real-manga-draft-line-benchmark),
a benchmark of **real production manga draft lines** -- the closest thing found so far to a clean line-art corpus that did
not have to be extracted -- and [Region-Wise Correspondence Prediction between Manga Line Art
Images](https://openaccess.thecvf.com/content/CVPR2026/supplemental/Li_Region-Wise_Correspondence_Prediction_CVPR_2026_supplemental.pdf)
(CVPR 2026), which is about comparing line art to line art.
