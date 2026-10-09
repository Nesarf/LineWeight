# Source libraries, and how to reach them

Two things this file settles that cost real time to learn: **which library of drawing references exists**, and **which
route reaches it from this machine**. Both were wrong before this file existed.

---

## Egress: the archive is reachable, but only through the proxy

**`archive.org` does not connect direct from this machine, and the reason is two-layered.** DNS resolves it to
`108.160.167.174` (a **Dropbox** range) and `dn790009.ca.archive.org` to `2a03:2880::/32` (**Meta's** range) --
`face:b00c` in the IPv6 tail is Meta's signature, and archive.org is not hosted by Meta. So the **name layer** is
poisoned. Pinning a plausible real IP with `curl --resolve` also failed, and `ping` lost 100% of packets, so the
**route layer** is closed as well. DoH to `cloudflare-dns.com` and `dns.google` were both reset or timed out, so the
poisoned answers cannot be corrected from inside the machine either.

**Everything above is true and none of it is the answer.** The answer was already written down in this workspace:

> 🧠 **From Hindsight memory (Egress judgement: speed, stability and IP locality)** — 一切出网经 `127.0.0.1:10090`;
> git-bash's `curl` is a native Windows program that does not read WinINET, so **per source it must be told
> explicitly**: `curl -x http://127.0.0.1:10090 ...`. The same page records Wikipedia as **DNS-poisoned with no direct
> route**, where **through the local mihomo proxy `curl` returns HTTP 200**.

**So:**

```bash
curl -x http://127.0.0.1:10090 -L https://archive.org/metadata/<item>      # works, HTTP 200
```

Verified: the IA item page returns **HTTP 200, 1.7 MB**, and the metadata API returns in seconds. `git push` was also
failing with `Failed to connect to github.com:443 after 21054 ms` during this session, and the same page gives the fix
for that too -- `git -c http.proxy=http://127.0.0.1:10090 push origin master`.

**The lesson is not "archive.org is blocked".** It is that a poisoned name layer plus a closed direct route is the
*normal* condition here and says nothing about reachability, and that the workspace already contained the route. Two
independent diagnoses (mine: "blocked, needs an egress path"; the memory's: "the same shape as Wikipedia, use the
proxy") describe the identical symptom, and only one of them is actionable. **Check the recorded egress posture before
declaring a source unreachable.**

## The library: Internet Archive item `how-to-draw-como-desenhar`

**1306 files.** A complete professional drawing-textbook collection, and it covers both of this project's directions
without gaps.

### The OCR layer is the cheap way in

Every scanned book has a `_djvu.txt` OCR companion, and there are **115 of them totalling 13.5 MB** -- small enough to
take the whole text layer at once. Downloaded to `E:\DaShaoHuo\downloads\ia-ocr\` (115/115, zero failures, seconds
each through the proxy). **The OCR text is not committed to this repository** -- it is copyrighted book content; only
short quotations appear below.

Ranked by size, the books that bear on this project:

| OCR | book | direction |
|---|---|---|
| 370 KB | **アンミ (Anmi), CGイラストテクニック vol.9** | pro illustrator workflow |
| 239 KB | **漫画の教科書シリーズ No.02, 萌えキャラの上手な描き方** | moe |
| 196 KB | **DSマイル (DSmile), CGイラストテクニック vol.10** | pro illustrator workflow |
| 191 KB | コミックス ドロウイングブック No.01, 萌えスタイルの描き方 | moe |
| 186 KB | **萌えキャラクターの描き方（顔・からだ編）** — 伊原達矢・角丸つぶら | moe, face + body |
| 185 KB | 萌えキャラクターの描き方（コスチューム編） | moe, costume |
| 179 KB ×2 | How to draw Mini Characters 1 & 2 | chibi |
| 149 KB | How to paint realistic skin of a beautiful girl | painting |
| 141 KB | **漫画达人！漫画的背景与透视** | **background + perspective** |
| 140 KB | 萌え絵の教科書 (三才ムック vol.385) | moe |
| 126 KB | How to draw a men's moe character: face & body | moe, construction |
| 99 KB | 女の子キャラが思いどおりに描ける本 | moe |
| 58 KB | **おんなのこの髪型カタログ** | **hair** |
| 50 + 47 KB | 人体解剖図から学ぶキャラクターデッサンの描き方 | anatomy |
| 160 + 171 KB | **How to draw background for characters 1 & 2** | **background** |

### The honest answer about how much is in the text layer

**Less than the inventory suggests, and the reason is structural.** A keyword pass over all 115 files for
`線の強弱 / 線の太さ / 線を太く / 線が一定 / 入り・抜き / 輪郭線` hit **only 8 files, 17 passages**. These are
picture books: the OCR recovers captions and step text, and the diagrams -- which is where the actual instruction
lives -- are images.

So the text layer yields **rules stated in prose and concrete tool parameters**, not a systematic account. What it does
yield is good enough to be worth having:

**Anmi, vol.9 -- and this is the most architecturally interesting sentence found:**

> **線の強弱（太さ）は深く気にせず**、まずは形を取ることに集中して、顔の線から描き始めます。線の強弱は気にして
> 描いたほうが良いのですが、私の場合は**線画ではなく着彩の段階で強弱を加えることもあります**
> Don't worry much about line weight variation -- concentrate on getting the form. It is better to think about it, but
> in my case I sometimes **add the variation at the colouring stage, not in the line art.**

**A working professional splits geometry from weight, and applies the weight later, as its own pass.** That is exactly
the split `lineweight` is built on -- `stroke_record` holds the geometry, width is applied afterwards -- and it is the
answer to how the role model should be positioned: **not as something the drawing step must know, but as a pass that
runs over finished geometry.** Brush sizes given in the same book: main line `10–15`, fine detail `4–5`.

**DSmile, vol.10 -- the failure mode, admitted by a professional:**

> **私は髪を描くたび線画に強弱を付けることを忘れがち**なので、みなさんも注意して描いてくださいね。
> I **tend to forget to add line-weight variation every time I draw hair**, so be careful.
>
> ドレスの裾…**線が一定にならないよう**気をつけて、強弱を付けながら
> the dress hem… be careful **not to let the line become uniform**, adding variation.

**Uniform width is the named, recurring failure** -- and hair is where it happens. This is the practical statement of
what the library exists to prevent, from someone who does it for a living.

**漫画の教科書 No.02 -- concrete taper parameters, and the width rule with its reason:**

> ペン設定を「**髪の毛…丸ペン 0.3ー0.4mm**」（**入り、抜き on 5.0mm**、補正…）
> Pen settings, "hair … round nib 0.3–0.4 mm", **taper-in / taper-out ON at 5.0 mm**, stabilisation …
>
> **服の厚みや影になる部分を考えて線を太くしたり細くしたり**していきます
> **Thinking about the thickness of the clothes and the parts that become shadow**, make the line thicker or thinner.

The second is the line-weight table's rule with its *reason* attached (cloth thickness, cast shadow), and the first is
a **real parameter set** -- `入り` and `抜き` are taper-in and taper-out, with an explicit length in millimetres.
`lineweight`'s pressure model has no taper-length parameter at all. This is a measured value to calibrate against.

**And the sentence that matters most for the bridge work**, from the same collection:

> **SAI は Photoshop に比べ"入り"と"抜き"がきれいに描け**、直に描いているような滑らかな線が描ける
> **SAI draws taper-in and taper-out more cleanly than Photoshop**, producing smooth lines that look directly drawn.

SAI is the application this project already bridges to (``E:\Apps\SAI-en\sai.exe``). Its taper is the reference
implementation its own users cite.

**How_to_draw_a_mens_moe_character -- construction, in a form that is at least partly encodable:**

* the guide is called **メンズガイド**, described as 「〇に十字」 -- a circle with a cross -- "developed just slightly"
* **three face-contour types, S / M / L, sharing a common contour start point** marked on the centre line
* jaw width derived by **dividing the centre line in two, then in half again**
* explicit **首の位置・太さ** (neck position and thickness) as its own step
* construction order: 顔の輪郭 → 目と眉 → 鼻 → 首 → 髪

## What is still out of reach

**The diagrams.** Everything above is text that happened to be captioned. The systematic instruction in these books is
in the figures, which means:

* the **page images** are 10–100 MB per book (`_jp2.zip` variants are larger still) and would need downloading
  selectively, not wholesale;
* **nothing on this machine can rasterise a PDF page** -- `pdftoppm` absent, PyMuPDF absent, `pdftotext`/`pdfinfo`
  present but text-only. So "download the book and look at it" needs a rasteriser installed first;
* JP2 page images exist as an alternative path that bypasses PDF rendering entirely, but need a JP2 decoder.

**`_text.pdf` variants exist for some books** and are smaller than the scans; they are worth a look before assuming
the full scan is required.

**One download is confirmed impractical on this link**: Princeton TR 2009/856, *How well do line drawings depict
shape?*, **43.66 MB**. `curl --retry` restarts it from zero on every timeout, so it never passed ~11 MB. Fetch it
without `--retry`, or not at all.

## Also downloaded, and free

The complete **Princeton SIGGRAPH 2005 course notes**, *Line Drawings from 3D Models*, all nine parts, to
`E:\DaShaoHuo\downloads\papers\sg05\`: introduction, differential geometry, the annotated bibliography,
NPR motivation, *Defining Lines on Surfaces*, *Line Drawings and Perception*, *Algorithms for Finding Lines*,
*Stylization of Line Drawings*, and *Abstraction and Evaluation*. The bibliography and the perception and stylization
notes are analysed in `RESEARCH-VECTORIZATION.md`.
