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

## The difference between 萌え and 美人 is not beauty

The tutorials above say *how*. This says *what the target actually is*, and it is the only research-grade source found.

**[「萌える」キャラクタの顔と声のデザインのための科学的設計指針の構築](https://kaken.nii.ac.jp/en/grant/KAKENHI-PROJECT-25560011/)**
-- KAKENHI 25560011, Grant-in-Aid for Challenging Exploratory Research, Kanazawa Institute of Technology, PI 山田真司,
FY2013-2016. The project's premise is the one sentence worth keeping:

> 従来、制作者達の**センスや経験、勘**に基づいて制作されていた「萌えキャラクタ」の顔…のデザインとその知覚印象との関係について、
> 心理学的・工学的手法による実験研究で明らかにする
> -- what has until now been made from **taste, experience and intuition** is to be settled by experiment.

Method, and this is why it beats every tutorial: professional designers produced a 「萌える」 face and a 「美人だが萌えない」
face; face parameters were then varied **interpolatively and extrapolatively** between the two; **83 stimuli** were rated by
semantic differential and factor-analysed.

The result:

| | |
|---|---|
| four factors explain the impression | **美しさ** (beauty), **派手さ** (flashiness), **力強さ** (strength), **大人っぽさ** (adultness) |
| a face read as **美人** | 美しくて・地味で・大人っぽい -- beautiful, plain, adult |
| a face read as **萌え** | 美しくて・派手で・子供っぽい -- beautiful, flashy, childish |

**Both are 美しい.** Moe is not "more beautiful" than a beautiful woman -- the two differ on 派手さ and 大人っぽさ, and
beauty is common to both. That is a design constraint stated as a direction in a four-dimensional space, and it is the
first thing found that says what to vary rather than how to hold the pen. The parameters actually manipulated were
**両目の間の距離 / 目の大きさ / 口の位置 / 顔輪郭の縦横比** -- inter-eye distance, eye size, mouth position, face-contour
aspect ratio. All four are numbers.

Reference: Wada, Yoneda, Kanamori, Yamada, *A perceptual study of face design for "MOE" characters*, IWIMQA 2013.

### The result that lands directly on this library

The same laboratory published, in the same year, the study that this library's output variable deserves:

**[Changes of Impression in the Animation Characters with the Different Color and Thickness in
Outlines](https://ep.liu.se/ecp/100/077/ecp14100077.pdf)** -- Haruna Izumi, Masato Sakurai, Ryo Yoneda, Masashi Yamada,
Kanazawa Institute of Technology. KEER2014 (International Conference on Kansei Engineering and Emotion Research),
Linköping, pp. 921-926. Free full text.

Setup, which is unusually clean for this question: four characters drawn so that they **do not** impress similarly;
white background; and -- the detail that makes the whole experiment work --

> The outlines of each character are drawn using the pen tool **without the effect of pen pressure**.

Removing pressure isolates width as a controlled variable. Ten outline conditions per character (none, four black
thicknesses at constant colour, five chromatic colours at constant thickness), **40 stimuli**, 18 bipolar adjective pairs,
7 ranks, 16 subjects, factor analysis. **Cumulative contribution ratio 81% on three factors**: naturalness, potency,
activity.

And then the two sentences that matter:

> the impressions to naturalness and potency are affected by the colors and thickness of the outlines **rather than the
> design of animation characters**
>
> the impression to activity is related to the design of the animation characters **without the effects of outlines**

**Naturalness and potency are properties of the line. Activity is a property of the design. They are separable.** That is
a diagnostic this project has never had: if a drawing reads wrong and the complaint is that it looks unnatural or weak,
the fault is in the linework, and no amount of character-design work will move it. It also means the linework can be
evaluated on its own terms, which is what `corpus_summary.json` has been trying to do without knowing what it was
measuring.

The measured effects, stated as directions:

| change | naturalness | potency |
|---|---|---|
| **thicker outline** | falls | **rises** |
| **brown / reddish-brown outline** (vs black at equal thickness) | **rises** | falls |
| black, reddish brown, pale brown | positive | -- |
| green, blue, red | negative | -- |

Two things follow.

**There is a trade-off, not an optimum.** Thickness buys potency and costs naturalness; brown buys naturalness and costs
potency. The paper explains the industry's move to brown outlines as exactly this purchase -- *"it gives animation
characters more natural and usual impressions"* -- and states the cost in the same breath: *"Although it decreases usual
and natural impression for them, the impression to potency increases with the thickness."* So "make the outline thicker"
is not an improvement, it is a **trade**, and a line-hierarchy model that only ever thickens the contour is spending
naturalness to buy potency without saying so.

**Colour near skin tone reads as natural, and so does black.** The colours that scored positive on naturalness are black
and the two browns; the ones that scored negative are green, blue and red. The paper's reading: *"the use of color close
to human skin color in the outline gives animation characters natural impression, as well as the use of black."*
lineweight currently has **no colour model at all** for outlines -- one brush, one ink. This is the evidence that colour is
not decoration but a second axis with a measured effect, and that the axis is legible: warm-and-desaturated versus
everything else.

**The limit of the finding, which has to be stated**: the study used **constant-width** outlines, because pressure was
deliberately removed. lineweight's pressure model produces **tapered** width. So the monotone "thicker → more potent"
result is measured on uniform outlines, and nobody has measured the tapered case. The honest position is that the
direction is likely to carry over and the magnitude is unknown -- and that this is exactly the kind of gap that the
`--fit-dir` corpus numbers were supposed to fill and could not, because they were computed over a mixed corpus.

Two more references from its bibliography, both on quantifying moe, neither yet obtained:

* Kawatani, Kashiwazaki, Takai & Takai (2010), *Feature Evaluation by **Moe-Factor** of ANIME Characters Images and its
  Application*, IEICE Technical Report 109(415), 113-118.
* Kawatani, Kashiwazaki, Takai & Takai (2008), *ANIME Degree Evaluation by Feature Extraction of Animation Characters*,
  IPSJ SIG Technical Report 2008-CG-132, 35-38.

"Moe-factor" is a numeric moe score computed from character images -- the earliest attempt found at turning the thing
this project is aiming at into a number.

## Frontal-face construction, and why its numbers cannot be trusted

[CLIP STUDIO TIPS, 正面顔イラストの描き方](https://tips.clip-studio.com/ja-jp/articles/16685) (もえかき編集部) gives the
standard construction, and the useful part is that it is explicit about *why* the frontal view is the hard one:
**正面顔は左右差が目立ちやすい** -- a three-quarter view hides imbalance in foreshortening, a frontal view does not.

The stated rules, worth recording because they are what a construction layer would encode:

* **ear** spans from the eye-height line down to about the nose
* **hair is drawn outside the skull**, not along its contour -- 一回り外側にボリュームを持たせて
* **hair is masses, not strands** -- 一本一本の髪の毛ではなく…大きな「かたまり」として考える
* **nose and mouth get few lines**; over-rendering them makes the whole face read heavy
* **左右反転** to check -- the same trick as looking at a drawing in a mirror, and the same one a renderer gets for free

And the rule that does not survive contact with itself:

> 目の大きさは顔の横幅のおよそ**2分の1**を目安に -- eye width ≈ **1/2** the face width
> 左右の目の間隔は「**目1個分**」程度空ける -- the gap between the eyes is about **one eye width**

Two eyes plus one gap is **three eye-widths** across the face, which forces eye width ≈ 1/3 of the face, not 1/2. The two
sentences on the same page cannot both be true. This is not a criticism of the article -- it is the ordinary condition of
prose rules about proportion, and it is exactly why **measuring a corpus beats reading rules**: a tutorial can state two
incompatible numbers in adjacent paragraphs and still be useful, whereas an extractor that returns 1/2 where the drawing
says 1/3 is simply wrong. It is the same reason the width numbers in `RESEARCH-SCENERY.md` had to be traced back to a
mixed corpus before they meant anything.

## Why line drawings work at all, and why nobody can say how

From **Line Drawings and Perception** -- Doug DeCarlo, Part III of the SIGGRAPH 2005 course *Line Drawings from 3D
Models* ([course7-6-lineinterp.pdf](https://gfx.cs.princeton.edu/proj/sg05lines/course7-6-lineinterp.pdf)).

**The puzzle, stated plainly**: *"It's actually a bit surprising that line drawings are effective at all. Upon first
inspection, line drawings seem to be too ambiguous. **An infinity of curves in 3D project to the same line in the
image.**"* Same non-injectivity that makes vectorization hard, seen from the perception side rather than the
representation side.

**And then the sentence that describes this entire project's reason to exist** -- about Dürer and Flaxman:

> While artists can produce drawings like this, **they don't have access to the nature of the processes behind what
> they're doing.** They rely on their training, and **use their own perception to judge the effects of their
> decisions**.

That is the whole situation. The knowledge is real, it is not written down anywhere as a process, it is transmitted as
training, and the only feedback loop is the artist's own eye. It is also why this project keeps finding that the
authoritative sources are **procedures** (*"draw the body under the clothes"*) rather than principles -- the principles
are unknown even to the people who execute them flawlessly. Every tutorial table in this file is a practitioner's
compression of a process they cannot fully state, which is exactly why those tables contain contradictions like the
eye-width one above.

**Coherence is local, not global.** The Penrose triangle and Vasarely's impossible figures show that the perceptual
integration of lines *"is not global"* -- inconsistencies survive and produce a non-convergent series of inferences. And:
*"Interpretation of line drawings depends on context."* Consequence for any automatic line work: **there is no global
consistency check that can be run on a line drawing**, because the human visual system does not run one either. A
renderer that enforces global geometric consistency is enforcing something the viewer never applies.

**The two-channel model of line patterns**, which is compact enough to be implemented:

> These patterns of lines convey **shading through their local density** and convey **geometry through their direction**.

Density carries tone; direction carries form. Two independent signals in one field of strokes. `lineweight` currently
models neither explicitly -- it has strokes with width and pressure, and no notion of a stroke *field*. Hatching,
cross-hatching and 陰影線 are all instances of the density channel, and the line-weight table's "solid fill (ベタ) for
deep cast shadows" is what that channel does when density saturates.

Dürer's print uses *"contour, crease, hatching, cross-hatching"*; Flaxman's uses *"contours and creases, and perhaps
other lines such as suggestive contours, ridges and valleys"* -- the same vocabulary as the formal taxonomy in
`RESEARCH-VECTORIZATION.md`, named from a 1505 woodcut and an 1805 etching.

## The pressure model's tapers were measured in the wrong unit

**This is the first change to `lineweight`'s model that came from an outside measurement rather than from this
repository's own judgement**, so the reasoning is worth keeping in full.

### What was wrong

`taper_in` and `taper_out` were **fractions of the stroke's arc length**. That is the one thing a taper cannot be. A
nib's entry is a **distance it travels while pressure builds**, and it is the same distance whether the stroke is long
or short. Measured on `ink` before the change:

| stroke length | entry + exit, in px | as a multiple of the 6.5 px width |
|---|---|---|
| 40 px | 6.4 | 1.0x |
| 400 px | 64.0 | 9.8x |
| 4000 px | 640.0 | 98.5x |

**One unchanged brush, a hundredfold spread in taper length.** Nothing caught it because every stroke in every test
was a similar length -- the defect only exists *between* lengths, and a single-length test cannot see it.

### The calibration

One measured anchor, from 漫画の教科書シリーズ No.02, 萌えキャラの上手な描き方: a **丸ペン of 0.35 mm with 入り and 抜き
set to 5.0 mm**, i.e. a taper **14.3x the nib width**. The unit became the brush's own width, because the anchor is a
**ratio** and a ratio is scale-free -- `lineweight` does not know a document's px-per-mm and should not pretend to.

**All four brushes take that single measured total and differ only in how it splits between entry and exit.** An
earlier attempt scaled each brush's old *fraction* by a common factor instead; that gave the 22 px `wash` a **590 px**
entry, longer than most strokes, so every wash became nothing but taper. Blindly rescaling numbers whose unit had just
changed is the same error as hand-computing an offset, and the existing tests caught it rather than a reading of the
code.

### What the verification actually showed, including where it misled

Measured with `ref.measure` on a rendered sheet of **60 strokes of lengths 40-1400 px** -- a stand-in for a page:

| model | `taper_ratio` |
|---|---|
| fraction-based (before) | **0.4595** |
| length-based (after) | **0.4372** |
| corpus target, moe / BA artbook | **0.3923** |
| corpus target, line-drawing library | **0.4213** |

**The change moves the metric toward the corpus**, which is the outcome wanted. But two things must be recorded against
that, because the first measurement taken said something different:

* **A single stroke measured in isolation gave 0.72-0.76** -- far *above* the corpus, which reads as "the tapers are far
  too shallow" and is the opposite of the truth. `taper_ratio` is the mean of the thinnest fifth of all runs against
  the mean of all runs, so on one long stroke the taper is a small absolute number of runs and the thinnest fifth is
  mostly **full-width** runs. **The metric is confounded by the distribution of stroke lengths, which is the same
  variable the defect concerns.** It is only meaningful over a drawing, not over a line.
* **The remaining gap (0.437 against 0.421) is not closable by this metric alone.** Lengthening the taper would lower
  the ratio further, but 14.3x is a *measured* value and tuning it to fit a confounded statistic would be fitting the
  measurement to the metric rather than the other way round. The gap is recorded, not closed.

The earlier test comment claimed that lowering the taper's floor from 0.25 to 0.06 *"changed the measured ratio by
nothing at all, at any render scale"*, and that stands: the floor sets the value at the first sample only. **A taper is
calibrated by its length, and the floor is not a calibration knob** -- which is what made the length the thing to fix.

### What this cost, and what it says about the tests

Three tests failed on the change and all three for the right reason: one used the old unit and had to be rewritten,
one had to have its sampling window moved off the tapers it was accidentally measuring, and one was a real threshold
that the longer taper pushed against. A fourth test was added that the old code cannot pass -- it draws a 200 px and a
2000 px stroke with the same brush and requires the same absolute taper -- because **the defect was invisible to a test
suite that only ever drew one stroke length**.
