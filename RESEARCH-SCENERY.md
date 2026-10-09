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
