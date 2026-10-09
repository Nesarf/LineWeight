# What is already out there for stroke-to-outline, collected

Written while working on the outline expansion's self-intersections. **Nothing here is endorsed or integrated** -- this
is a survey, kept because the search itself was the useful part and would otherwise be repeated.

The problem being solved: a centreline with a width at every point becomes a filled polygon by offsetting to both sides,
and where the stroke curls tightly the offsets cross. The crossings that matter are the ones that wind *against* their
neighbours, because under SVG's `nonzero` fill rule those cancel instead of filling and leave a pinhole in the stroke.
This project's numbers: **0 holes at ordinary curvature, 6 and 5 on tight and tighter waves** (see the tests in
`tests/test_lineweight.py`).

## The finding that matters most

**A well-known implementation of this exact thing has the same self-crossings and accepts them.**

[`perfect-freehand`](https://github.com/steveruizok/perfect-freehand) (Steve Ruiz; the drawing engine behind tldraw)
turns points-plus-pressure into a filled outline -- the same transformation this library performs -- and its
documentation says plainly:

> By default, the polygon's paths include self-crossings. You may wish to remove these crossings and render a stroke as a
> "flattened" polygon.

It renders with `fill-rule="nonzero"`, which is what this library does. So the crossings are a property of the approach
and not a defect in this implementation; what this library does *not* know is whether `perfect-freehand` has the same
pinholes at tight curvature, and that is the experiment worth running before writing any more geometry.

There is a Python port: [`perfect-freehand-python`](https://bigbluebutton.github.io/perfect-freehand-python/)
(`pip install perfect-freehand-python`, by Calvin Walton, porting Ruiz's algorithm).

## The canonical fix, as the reference implementation states it

```python
from shapely.geometry import Polygon

polygon = Polygon(stroke)
polygon = polygon.buffer(0)          # resolves self-crossings into a valid polygon
```

`buffer(0)` is a **polygon self-union**: it returns the region the polygon encloses under the nonzero rule, as one
exterior ring plus interior rings for any holes. Two consequences the same page names and this project had not worked
out:

* after a self-union the result is **several rings**, so the path must use **`fill-rule="evenodd"`** for the holes to
  read as holes rather than as more fill;
* the operation is the whole of Clipper's value, which is why Clipper exists.

Implementations: [Clipper2](https://github.com/AngusJohnson/Clipper2) (C++, with bindings),
[`pyclipper`](https://github.com/fonttools/pyclipper) (Python), and `shapely` (GEOS) above. All are dependencies, and
this library is deliberately pure-stdlib, so using any of them is a design decision rather than a fix.

## The algorithm, and why two attempts here failed

The problem has a name in the literature: an **invalid loop**. Definition 3 of
[*Offsetting obstacles of any shape for robot motion planning*](https://www.cambridge.org/core/journals/robotica/article/offsetting-obstacles-of-any-shape-for-robot-motion-planning/)
is exactly this object.

The cost structure is the part that explains the failures. From a survey of the method
([METU thesis](https://open.metu.edu.tr/bitstream/handle/11511/115421/Parviz_Thesis_Final.pdf)): constructing the raw
offset curve is **O(n)**, and **removing invalid loops is the expensive step**. Both attempts this project made were
cheap O(n) filters over the offset points, which is not the same class of operation as the step they were trying to
replace:

| attempt | result |
|---|---|
| current: one polygon, `left + reversed(right)` | 11 holes (0 at ordinary curvature) |
| drop offset points covered by any disc of the sweep | **175 holes** -- worse |
| the same, with gaps filled by the disc's arc | **168 holes** -- still worse |
| each segment emitted as its own consistently-wound subpath | 11 holes -- no change |

The middle two failed for a reason worth keeping: a coverage test **also fires on the inside of an ordinary curve**,
where the offset point is legitimately on the boundary, so the change damaged the easy cases while failing to fix the
hard ones. All four were measured by the same winding-number criterion, which is now a test.

Worth calibrating against: **Inkscape replaced its offset and boolean engine outright** --
[Killing Livarot](https://wiki.inkscape.org/wiki/index.php/Killing_Livarot). That is a useful reminder that this step is
hard enough that major projects have bought their way out of it rather than written it.

## Same problem, adjacent projects

| project | what it is | why it may be worth reading |
|---|---|---|
| [`perfect-freehand`](https://github.com/steveruizok/perfect-freehand) | points + pressure -> outline | the closest thing to a reference implementation of this library's core |
| [`libmypaint`](https://github.com/mypaint/libmypaint) | the brush engine behind MyPaint | the reference for pressure-driven brushes; `lib/strokemap.py` is its stroke representation -- tiles rather than one polygon, which sidesteps the problem differently |
| [`SVGPathProfile`](https://github.com/saurabhgayali/SVGPathProfile) | "separating SVG path geometry from reusable stroke-width behaviour" | the same decomposition this library arrived at with `stroke_record` -- geometry, pressure and brush response kept apart |
| [`@hanakla/svg-variable-width-line`](https://www.npmjs.com/package/@hanakla/svg-variable-width-line) | variable-width lines as SVG | same output, different input model |
| [`wobble-strokes`](https://blu-octopus.github.io/wobble-strokes/) | variable-width hand-drawn SVG paths | the wobble/hand-quality half of the problem |
| [`strokify`](http://osp.kitchen/tools/strokify/) | expands strokes for fonts | a different domain, and it delegates the expansion to FontForge rather than doing it |
| [`lineartization`](https://pypi.org/project/lineartization/) | PyPI, line-art oriented | unexplored |
| [`TJ_ComfyUI_Lineart2Vector`](https://comfy.icu/extension/TJ16th__TJ_ComfyUI_Lineart2Vector) | line art to vector, in ComfyUI | unexplored; same pipeline position as this library |

## Geometry libraries to weigh against the pure-stdlib constraint

* [`compmec/shapepy`](https://github.com/compmec/shapepy) -- 2D boolean operations with NURBS curves
* [`gon`](https://pypi.org/project/gon/) -- 2D geometry
* [`congma/polygon-inclusion`](https://github.com/congma/polygon-inclusion) -- winding number, which is the primitive the
  acceptance test here is built on

## On the wider goal, which is line quality rather than geometry

This library exists to make programmatic linework read as drawn, for Japanese-style character work. Two papers are
directly about measuring whether that worked, which is the question the corpus calibration in this repository answers
only statistically:

* [*Quantitative Evaluation of Line Thickness in AI-Generated Anime Line Art Using Image Processing*](https://zenodo.org/records/18251029)
* [*Automatic Line Art Extraction and Line Correction System from Original Images Based on Image Processing Algorithms
  for Animation Production*](https://zenodo.org/records/18493610)

Both are unexplored. The first is the more interesting, because "the linework looks wrong" is the complaint that started
this project and this project's answer so far has been a width distribution rather than a perceptible-quality measure.

## SVG itself

Variable stroke width is a long-requested SVG feature that did not arrive;
[SVG2 Requirements Input](https://www.w3.org/Graphics/SVG/WG/wiki/index.php?title=SVG2_Requirements_Input) has the
requests. This is why the expansion has to be done by hand at all, and it is the standing reason the approach will not
become unnecessary.

## The algorithm itself, read from the source

The complete implementation is small enough to read in one sitting: `perfect-freehand`'s ESM bundle is **3.77 kB**, whole.
Fetched from `https://unpkg.com/perfect-freehand@1.2.2/dist/esm/index.mjs`. `getStrokeOutlinePoints` is the function that
matters, and it does something this project never thought of.

**It builds one polygon the same way this library does** -- a left chain, an end cap, the right chain reversed, a start
cap -- so the construction is not where the difference lies. The difference is a **direction-reversal test**:

```js
Y  = dot(currentVector, nextVector)          // consecutive samples agree?
be = dot(currentVector, previousVector) < 0  // the stroke just turned around
ne = Y < 0                                   // the stroke is about to turn around

if (be || ne) {
    let v = perpendicular(previousVector) * radius
    for (let w = 0; w <= 1; w += 1/13) {
        left.push (rotate(offsetLeft  - v, aroundPoint, (PI + 1e-4) *  w))
        right.push(rotate(offsetRight + v, aroundPoint, (PI + 1e-4) * -w))
    }
    continue          // and the normal points are NOT pushed
}
```

**Where the offsets would cross, it stops marching and sweeps a half-circle instead.** That is the whole trick. A tight
curl, a hairpin, a cusp -- any place where the direction of travel reverses -- is handled by drawing the arc that the
turn actually makes, rather than by letting the left and right chains pass through each other and hoping the fill rule
sorts it out. Nothing is unioned, nothing is clipped, and no invalid loops are ever created, because the polygon never
gets the chance to cross itself there.

The rest of the function, for completeness:

* **The normal is interpolated between consecutive samples**, not taken from one of them: `e + (next - e) * dot`, so the
  offset direction turns smoothly through a corner instead of stepping.
* **Points closer than `(size * smoothing)²` to the last pushed point are dropped**, which keeps the polygon small on
  dense input -- the same job this library does by choosing a resampling resolution up front.
* **Both caps are arcs**, sampled at `PI/13` and `PI/29` steps, so a round cap falls out of the same mechanism.
* **Pressure is smoothed** over the first ten samples and by an exponential follow on the running length, which is the
  same idea as the low-frequency noise term here.

### What this means for this project

The fix is not a polygon self-union. A self-union is what you do when you already have an invalid polygon; this avoids
producing one. It is a **local test and a local arc**, roughly:

```
for each sample i:
    if dot(v[i], v[i-1]) < 0 or dot(v[i], v[i+1]) < 0:
        emit the turning arc on both sides; do not emit the normal offsets
    else:
        emit the offsets with an interpolated normal
```

That is a few dozen lines, it is in the same O(n) class as the existing loop, and it produces no invalid loops by
construction. **It is the next thing to try, and it should be tried before anything heavier** -- the earlier attempts
here failed because they were filters applied *after* the polygon had already crossed itself, and this prevents the
crossing.
