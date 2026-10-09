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
