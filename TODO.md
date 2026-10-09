# TODO

Ordered by what unblocks what. `P0` means *without this the rest is guesswork*.

---

## P0 — 独立裁判（everything else is unverifiable until this exists）

- [ ] **Deterministic self-render.** Take an SVG path string emitted by `inked_svg()`,
      rasterise it myself with `pycairo` (1.29.1, already on this machine), write a PNG,
      and read it back with `read_image`. No app, no bridge, no human.
      - This is the missing half of every verification so far: the bridges prove
        *the app accepted the file*, never *the geometry is right*.
      - Must be reproducible: fixed size, fixed background, no anti-alias surprises.
- [ ] **Use cairo `stroke()` as an independent geometry referee.** cairo can stroke a
      centreline natively. Rasterise cairo's own stroke and my expanded outline, then
      compare coverage. Two implementations, one input, no shared assumption — which is
      exactly the discipline this project has violated five times (four on PSD).
      - Known limitation to record, not to hide: cairo's stroke is *also* an offsetter,
        so agreement is evidence, not proof.
- [ ] **Render every stroke in its own colour at high zoom.** Stolen from Metzger 2024
      (CESCG), Figure 5: he compares five vectorizers by giving *"each curve … a mutually
      exclusive color and a high zoom level"*, because visual similarity hides the
      structure and structure is what is being judged. Strokes that merge, self-cross or
      loop are then visible without an app, a bridge or a judgement call.
      - Cheapest independent check available for `stroke_record`, and it needs the same
        rasteriser as the item above.

## P1 — Geometry

- [ ] **Direction-reversal detection in `outline()`.** Read out of the `perfect-freehand`
      bundle (3.77 kB ESM): when `dot(v[i], v[i-1]) < 0` or `dot(v[i], v[i+1]) < 0` it
      sweeps a half-circle arc instead of emitting offset points. It **avoids creating
      invalid loops rather than repairing them** — the repair path is the expensive one
      (raw offset is O(n); loop removal dominates).
      - Current state: 11 holes on the test corpus with consistently-wound subpaths.
      - The reverted `covered()` experiment is the negative control: it took 13 holes to
        **175**, because the coverage test also fires on the *inside of ordinary curves*.
        Do not retry it without a curvature gate.

## P2 — Model

- [ ] **Line hierarchy.** 輪郭線 / 内部線 / 陰影線 as distinct roles instead of one width.
      `stroke_record` should carry the role, not just the width.
      - **Now has empirical grounding**, not just convention: KEER2014 measured that
        outline colour and thickness control **naturalness** and **potency**, while the
        character *design* controls **activity** -- the two are separable. Thicker raises
        potency and lowers naturalness; brown raises naturalness and lowers potency.
      - **Consequence for the model: there is a trade-off, not an optimum.** A hierarchy
        that only thickens the contour is silently spending naturalness to buy potency.
        The role model has to be able to say which it is buying.
      - Open gap: the study used **constant** width (pressure deliberately removed), so
        the tapered case that `lineweight` actually generates is unmeasured.
- [ ] **An outline colour axis.** `lineweight` has one ink and no colour model. KEER2014
      found colours near skin tone (and black) read as natural while green/blue/red read
      as unnatural, and brown was adopted by the industry for exactly that reason.
      - Same file, same evidence as the role model -- they are two axes of one finding.
- [ ] **Moe construction knowledge** (see `RESEARCH-LINE-QUALITY.md`):
      - widths are **relative within one drawing**, never a fixed constant
      - thicken: outer contour, shadow side, base of hair and folds
      - thin: lit side, inside of skin and cloth, fine tips
      - eyelashes are **overlapping strokes**, not filled black
      - 2D construction is **inside-out** (draw the body under the clothes);
        2.5D is outside-in — the same target built two different ways.

## P3 — Rendering

- [ ] **Cel shading.** Only after the linework is trustworthy; shading hides line faults.

---

## Corpus

- [ ] **Fix the classifier.** `tests/tools/add_corpus.py:94-95` currently selects
      `line_runs >= 200 and ink_ratio < 0.30`. That threshold **admits full-colour
      illustrations** — a 15-page stride sample from volume 1 measured ink_ratio
      **0.1901**. "276 line drawings" really means "276 ink-light pages".
      - Replace with a **monochrome-ness / saturation** test, then recompute
        `tests/data/corpus_summary.json`.
      - This separates the sets but does **not** produce more line art. See below.
- [ ] **Extract line art instead of classifying pages.** Commit `69d33e8` recorded the
      decision: run every one of the 929 pages through a line-art extractor rather than
      guessing which pages are line art.
      - `control_net_lineart_anime`, `lineartization`, `bloc97/SYNLA-Dataset`, `SYNLA-Plus`
      - **Build-time only. Never inside `lineweight`.** The library is deliberately
        stdlib-only and must stay that way — the corpus is data, and a library that
        consumes it must not inherit a deep-learning stack.
- [ ] **Verify the extractor before trusting any number derived from it.** A thinner or
      fatter extractor moves every width statistic. Extraction is an opinion, so it has
      to be checked against something that is not extraction.

### Reference corpora — they are NOT comparable

| corpus | ink | width med | p90 | taper |
|---|---|---|---|---|
| line-drawing library (276) | 0.1485 | 4.0 | 11.0 | 0.4213 |
| BA official art (15, stride, vol 1) | 0.1901 | 4.0 | 12.0 | 0.3923 |
| `16+` illustrations (14) | 0.3429 | 5.0 | 13.0 | 0.3811 |
| `ACG建筑` (20) | 0.6290 | 5.0 | 13.0 | 0.3564 |

- Target for moe work: **median 4 px, p90 12 px, taper 0.392, ink 0.190**.
- **The trap:** the width metric is valid (Pillow lines 2/4/8/16 → 2.0/3.0/8.0/16.0),
  but `ref.py` excludes runs > 16 px as area. On painted art the surviving "line-like
  runs" are shadow and texture edges. So agreement across the four sets above does
  **not** mean the linework agrees.
- `--fit-dir` currently treats every corpus identically. It must not.
- `F:\素材\图\16+` is **mixed** — Pixiv illustrations + phone photos + screenshots.
  25 files ≠ 25 drawings.
- `F:\素材\图\固态景色\ACG建筑` is **painted (厚塗り)**, essentially no line art, so
  lineweight's role there is underdrawing only — a different job with different numbers.
- Corpus source, confirmed: `F:\素材\图\碧蓝档案官方设定资料` → `1/` 292 + `2/` 321 +
  `3/` 316 = **929**, exactly the `corpus_summary.json` record count.

---

## Prior art — read, and what it settles

Full write-up in `RESEARCH-VECTORIZATION.md`.

- [x] **Metzger, *Semantically Meaningful Vectorization of Line Art in Drawn Animation***,
      CESCG 2024, TU Wien, supervised by Michael Wimmer. Read.
      - States this project's criterion: vector structure must be *"close to how artists
        would draw"*, not merely visually similar.
      - **Settles the pinhole question**: his survey finds *no* method — heuristic or
        learned — vectorizes clean animation frames usably, failing specifically on
        **high curvature**, with *"a bias towards lower curvature"* and *"small holes"*.
        Same failure as `outline()` produces. It is the domain's open problem, not a bug
        here. Stop treating it as a local defect.
      - **Settles where the differentiator is**: every surveyed method outputs curves with
        a **fixed stroke width**. Variable width is what `lineweight` does and what nobody
        else models.
- [x] **Izumi, Sakurai, Yoneda & Yamada, *Changes of Impression in the Animation
      Characters with the Different Color and Thickness in Outlines***, KEER2014,
      pp. 921-926. Read. See the role-model item under P2 — this is its evidence.
- [x] **TuringSketchLine** — real manga production drafts paired with final line art,
      DOI `10.21227/kcvr-qf66`, 3.44 GB, panel JSON/JSONL, character boxes and identity
      labels, non-commercial, **download needs an IEEE DataPort login**. Read.
      - It is **not** a clean corpus: *"many final contours are missing or differ from the
        draft strokes"*. It is evidence that **the draft stroke is not the contour** — a
        boundary condition on `outline()`, not a dataset to calibrate against.
      - Its one genuinely useful number, not yet extracted: **how far a draft stroke sits
        from its final contour**. That would set a tolerance for the whole pipeline.
- [x] **Li, Mao, Qiu & Matsui, *Region-Wise Correspondence Prediction between Manga Line
      Art Images***, CVPR 2026, pp. 15334-15342, [arXiv 2509.09501](https://arxiv.org/abs/2509.09501).
      Read.
      - The line-art-to-line-art comparison machinery this repo lacks — the reason the four
        width tables cannot be compared to each other. Learned, so corpus-side only.

### Not yet read

- [ ] **JAniCA (日本アニメーター・演出協会) perspective course handouts.**
      Downloading to `E:\DaShaoHuo\downloads\janica\`. 5-6 MB each; `basic04` returned 404.
      - Why: `basic03` says *「結構自然に見えますが、このカットも『消失点を曖昧にして』描かれています」*
        — the natural-looking cut is the one with the **vanishing point deliberately left
        ambiguous**. Second independent source for "the geometric ideal is not the drawn
        thing". Consequence: fitting every scene to a detected vanishing point would be
        measurably correct and visually wrong.
- [ ] **Quantitative Evaluation of Line Thickness in AI-Generated Anime Line Art Using
      Image Processing** (Zenodo 18251029) — a published thickness metric to check this
      repo's width measurement against instead of trusting it. Direct
      [PDF](https://zenodo.org/records/18251029/files/%5Ben%5DQuantitative%20Evaluation%20of%20Line%20Thickness%20in%20AI-Generated%20Anime%20Line%20Art%20Using%20Image%20Processing.pdf?download=1).
- [ ] **Kawatani et al. (2010)**, *Feature Evaluation by **Moe-Factor** of ANIME Characters
      Images and its Application*, IEICE TR 109(415) 113-118 — a **numeric moe score**
      computed from character images. Earliest attempt found at turning the target into
      a number; also **Kawatani et al. (2008)**, IPSJ SIG 2008-CG-132, 35-38.
- [ ] **LineGAN: A Line Drawing Rendering Model with a Focus on Line Density
      Distribution**, J-STAGE *mta* 12(1) — **line density distribution** as a metric,
      which this repo could compute directly.
- [ ] **2次元アバターの輪郭線の太さがプロテウス効果に及ぼす影響**, 感性工学 24(4), `TJSKE-D-25-00036`
      — outline thickness of a 2D avatar affects the **Proteus effect**, i.e. line width
      changes user behaviour, not just appearance. Recent (submitted 2025).

## Tooling

- [ ] **CLI: take control points from a file.** Today `lineweight` can only draw its
      built-in demo, so nothing outside the test suite can be fed through it.
- [ ] Push any local commits when the network allows (last known pushed: `69d33e8`).

---

## Standing discipline

1. **Verify with an independent artifact.** Two things that share an assumption cannot
   check each other. This has bitten the project five times, four of them in the PSD
   writer.
2. **A helper that is right plus a serialiser that ignores its argument is a contract
   nothing checks.** It happened: `channel_bytes(-1)` was hardcoded for every channel,
   so every colour read back as white.
3. **Hand-computed offsets are a repeated error source.** Compute them, then verify them
   against a rasteriser.
