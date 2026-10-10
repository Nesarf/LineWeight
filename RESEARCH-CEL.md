# Cel shading: what the sources say, and what this project may therefore claim

A separate file because it is a different kind of source from `RESEARCH-MOE.md`. That one is a professional
textbook's construction method for the *figure*; this is about the *shading pass* -- and the first thing worth
recording is that the useful answer came from a tool vendor's own tutorial rather than from an academic paper.

## The shadow boundary is placed where the surface changes direction

Source: **赛璐珞风格上色技巧**, Liz Staley, CLIP STUDIO TIPS.
<https://tips.clip-studio.com/zh-cn/articles/10901> (fetched 2026-10-10; the author is a Clip Studio Paint beta
tester and has written three books on the program.)

> 「我发现最简单的方法是将要上色的对象视为线框对象（3D 建模中常见的一种对象）……例如，让我们以常见的球体上色
> 练习为例……我们可以将球体垂直和水平地分割成段。**球体的每个面都显示了对象表面方向的变化。**通过选择将球体
> 分解成这些部分，我们就可以根据光源，并按照**分段线**来放置高光和阴影。」

**That is a method statement, and it is the one thing this project needed.** The shadow boundary is not offset from
the silhouette and it is not a projection: it runs along the lines where the form's **plane orientation changes** --
the edges of the facets a wireframe would show. For a face those are the 脸部平面 the author says artists have been
studying for centuries.

**And it means the library must not compute a shadow shape from a light vector.** A light direction votes on *which
side* of each facet boundary the shadow falls, but the boundary itself comes from the form's planes, and in practice
the author says she **draws the region by hand with the lasso tool**:

> 「我使用套索工具绘制出我想要用阴影颜色填充的区域。」

So the honest division for `lineweight` is the one it already has: **the caller supplies the region, the library
supplies the quantisation and the blend.** The alternative -- inventing a geometric shadow from an offset outline --
would produce something no source describes and no measurement here supports.

## The always-shadowed regions, stated as a rule

> 「给脸部上色时，**有些区域几乎总是处于阴影中**，除非有特殊的照明情况（即下方有光源）。这些区域是**眼睛上方、
> 鼻子下方、上唇和下巴正下方**。」

**A concrete, checkable list** -- and the same paragraph immediately qualifies it:

> 「此外，在大多数动漫风格中，**最好跳过上唇区域的阴影**，而是在嘴巴下方稍微放置一个小的三角形阴影，以暗示下唇。
> 当然，这完全取决于您的风格！」

So the list is a **default rather than a law**, which matches how this project treats every other rule it has taken
from a source: measured where it can be measured, a documented default where it cannot.

## The pass itself: multiply for shadow, screen for light

> 「我喜欢在我的基础平铺颜色**上方创建一个新图层**。将这个新的阴影图层设置为**正片叠底**混合模式，然后将不透明度
> 降低到大约 **50%**。然后我选择一种阴影颜色，通常是根据我想要的心情选择**深沉的去饱和蓝色或紫色**……」

> 「要添加高光，请创建另一个新图层并将其设置为**滤色**。下面的示例将不透明度设置为大约 **75%**……由于我选择了
> 冷色调的阴影颜色，所以我将选择**暖色调**的高光颜色。我使用了淡黄色。」

**Three numbers and two rules, from a practising illustrator**: a 50% multiply layer for shadow, a 75% screen
layer for highlight, and **the shadow cool against the base while the light is warm** -- a convention rather than a
physical result, and stated as one.

**Why this is the right shape for this library.** It is exactly the structure the 3D assets on this machine imply:
`_CodeMultiplyColor` set to the identity on all 460 materials is the multiply of "no shadow yet", which is what a
multiply layer's neutral element is.

## What this settles for P4

`lineweight/cel.py` had a quantiser and a hardness with a measured default, and an open question: **where does the
signal come from?** Three candidate answers were on the table -- sweep the silhouette along a light direction, take a
field from the caller, or threshold a brightness. **The source rules out the first and endorses the second**, and it
does so on the grounds that the boundary follows the form's planes rather than its outline. The measurement done here
agrees from the other side: the rigs' shadow slots are drawn artwork with hard edges in 62% of cases, which is a
shape someone chose, not a shape a formula produced.

## Not established

* **No studio documentation of a house light direction.** The Moegirlpedia article on 赛璐璐 as an animation technique
  was not retrievable -- the site is behind a JavaScript challenge and its API refuses unauthenticated calls -- and it
  is the kind of source that would carry the historical claim rather than the working one.
* **No numeric standard for the shadow's darkness.** 50% is one illustrator's default in a tutorial.
* **Whether the always-shadowed list holds in Japanese studio practice** as opposed to one author's teaching. It is
  quoted here as her statement, at her URL, and not promoted to a rule.
