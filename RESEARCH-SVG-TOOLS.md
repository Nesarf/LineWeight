# SVG 优化工具 —— 评估与结论

**结论先行：不引入。** 理由不是「不需要」，是 **SVGO 的默认预设会删掉这个产品的定义**。下面每一条都是实测，不是转述。

来源：一份转来的速报（Gemini）推荐 SVGO 为主流 SVG 优化工具，并列了 oxvg / svgtidy / svgomg / scour /
php-svg-optimizer / SVGito / svg-sprite 等替代。

---

## 1. 实测：SVGO 4.1.0 对本项目的输出做了什么

`preset-default` 的内容**从源码读出**（`plugins/preset-default.js`），不靠记忆：

```
removeComments  removeMetadata  cleanupIds  removeUselessDefs  convertShapeToPath
collapseGroups  convertPathData  mergePaths  removeHiddenElems  ... 共 34 个
```

本机装了 SVGO 4.1.0（`E:\DaShaoHuo\cache\svgo-probe`），跑两份 40 笔画的 SVG——一份是**现在**的扁平输出，
一份是**产品要求**的每笔一层输出：

| | 大小 | `<path>` | `<g>` | `id` |
|---|---|---|---|---|
| 现在（扁平，每笔自带 opacity） | 83788 B | 40 | 0 | 0 |
| 同上，SVGO 之后 | 47114 B | **39** | 0 | 0 |
| 产品要求（每笔一层 `<g id="m0001">`） | 84535 B | 40 | **41** | **41** |
| 同上，SVGO 之后 | 47114 B | **39** | **0** | **0** |

**41 个 group 和 41 个 id 全部消失，40 笔被并成 39 个 path。**

关键在最后两行：**被毁掉的正是产品要求的那一层**。而危险的地方是**它现在不会出事**——当前的扁平输出没有
group 也没有 id，SVGO 跑上去几乎无害（`mergePaths` 只在计算样式完全相同时才合并，所以 40 笔里只并掉了 1 对）。
于是「引入 SVGO」这个决定会**现在通过、等到实现分层的那天再炸**，而那时它看起来会像分层代码写错了。

## 2. 那条 44% 不是魔法，也不需要它

同一个测试里，两边的体积都刚好落在 **47114 B**——扁平的那份没有 group/id 可删，省下的同样是 44%。
所以那 44% **不是结构换来的**，是路径数据压缩换来的（相对命令、更少的分隔符、更少的小数位）。

自己写相对坐标序列化，同样的 40 笔画：

| | 大小 | B/顶点 |
|---|---|---|
| 现在：绝对坐标 `%.2f` | 81882 B | 15.8 |
| 相对坐标 + 紧凑 `%.2f`（**精度完全不变**） | 57109 B | 11.0 |
| 相对坐标 `%.1f`（换来 0.05 单位误差） | 46757 B | 9.0 |
| SVGO 4.1.0 | 47114 B | 9.1 |

**相对坐标在精度不变的情况下白拿 30%，并且比 SVGO 那份还小、不删任何东西。**
剩下那 13% 要拿精度换。→ 记入 `TODO.md` P4.5。

### 相对坐标不是纯赚

每个 delta 独立舍入会**沿折线累积**。129 个顶点的轮廓上，每点 ±0.005 的最坏漂移是 **0.65 单位**。
绝对坐标的误差有界，相对的没有界——要么保留绝对，要么相对但周期性 rebase 回绝对。

---

## 3. 这是范畴错误，不只是不必要

SVGO 的判据是**渲染出来一样**。本项目的判据明确**不是**这个。

Metzger 2024 把这个项目的问题写成研究问题的原话：

> the resulting line-art vector image needs to be **semantically meaningful**, i.e., the arrangement,
> topology and parameterization of graphical primitives need to make sense and be **close to how artists
> would draw**

> It is **not** visual similarity -- a raster trace can be pixel-accurate and still be useless

所以 `collapseGroups` 删掉 `<g id="m0001">` **不是 SVGO 的 bug**，是 SVGO 在**正确地做它自己的事**。
两个工具不是「用不上」，是**衡量的是同一幅图上互斥的两件事**。

速报里唯一一条能直接执行的建议是「确保 `viewBox` 从 0 0 开始」——**已经满足**，
`demo()` 与 `inked_svg()` 写的是 `viewBox="0 0 W H"`。

`scour` 是速报里唯一与本项目同语言生态（Python）的一条，反对理由完全一样。

---

## 4. 但它指出了一个真实的缺口

速报的话题让下面这件事被看见了，这条值得单独记：

**cairo 裁判吃的是点，不是字符串。** 计划中的 cairo 自渲染把 `outline_polygon()` 吐出的 **点**交给 cairo，
于是「点 → `d` 字符串 → Illustrator」这条链上，**字符串那一段仍然没有任何东西验过**。
这正是本项目已经付过学费的那条纪律：*一个 helper 是对的、而序列化器忽略它的参数，这个契约就没有人检查*。

- **先做**：`polygon_to_path()` → `parse_path()` → 和原点比。抓得到丢点、错序、命令字母写错、子路径断开。
  抓不到「数字格式应用读不懂」——那个只有 Illustrator 当裁判，桥已经在做。
- **试过浏览器当独立 SVG 渲染器，暂不可靠**：本机 Chrome 与 Edge 都在，`--headless --screenshot` **确实渲染过**
  （200×120 的 SVG 截出来，左上角像素 = 纸色 `#F4F1E9`，说明纸张矩形画上了）。但两次里有一次是
  **半张没画完的帧**（矩形只剩上边一条灰线，其余全白），加了 `--virtual-time-budget=4000` 之后直接静默
  exit 2。**一个偶尔交出半张图的裁判比没有裁判更坏**，因为差分会看起来像几何 bug。
  要用得先证明截图稳定——不能先用后证。
