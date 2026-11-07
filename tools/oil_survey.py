"""一块颜色能有多大：把画面压到有限色数，量同色连通块的面积。

**这个测量的起因是一个被数据推翻的猜想。** 看塞尚那张静物，我的第一判断是——他的苹果由四到六块颜色组成，
每块有自己的形状，眼睛读的是块与块之间的边界；而我画的苹果由两千六百笔组成，每一笔的颜色都略有不同，
所以同色区域只有一笔那么大，画面读起来是连续渐层。这个说法听起来对，而我当时正准备把它写进库里当成规律。

量完之后它反了。把七张公有领域的油画与三张自己画的图都压到十八色，再量同色连通块的面积：

    picture                     blocks   median      p90   top8 share
    cezanne-apples-1890           1611       74      384        29.5%
    cezanne-quince                1799       84      531        32.2%
    courbet-apples-1871           1231       68      373        39.6%
    met-apples-pears              1748       86      606        22.3%
    manet-two-apples               275       59      149        61.9%
    apple.png                      527      119     3769        36.7%
    cloth.png                     1461      140      886        24.6%
    fish.png                       275      131     5418        49.9%

**油画的中位块是五十九到八十六像素，我的是一百一十九到一百四十** —— 我画的画面比油画更「整块」。而 p90 差一个
数量级：油画最大六百，我那条鱼是五千四百。

**所以真正的问题不是笔触太碎，是画面里有大片没人碰过的地方** —— 苹果的背景、布的下摆、鱼的暗部，几百个像素
同一个颜色。油画里没有这种区域，每一个角落都在变。

**而「块大」本身不是错。** 马奈那张只有二百七十五块、top8 占六成二，他的笔触是整块下去的，一片颜色吃下画面
的大部分。区别在于他的大块里有笔触的起伏与颜色的微差，我的大块是空白。一个是选择，一个是没画。

**这是这个文件存在的理由**：那个猜想如果直接写进库里，会是一条假的规律，还会把人引向「把笔触改碎」这个错方向。
量它一次的成本是一张表，换来的是问题问对了地方。

**然后是这一列被它自己推翻的那一步。** 上面那张表之后，按「`p90` 不超过六百像素」改了三版苹果，`p90` 从 3769
一路到 808，而每一版都比上一版难看 —— 菊花、莲座、漩涡。判据如果最优解在画面最丑的地方，它量的就不是那件事。
所以加了 `within`：按面积加权的块内颜色标准差。它把「画面里有没有下过笔」与「块大不大」分开了 ——
七张油画 4.5 到 8.1，那条鱼 2.4，苹果从 3.1 到 4.6。两次推导在 `AESTHETIC-LIBRARY.md` 4.55 与 4.56 节。

注释与代码本体不掺语气；那份测量的判断在 `AESTHETIC-LIBRARY.md` 4.55、4.56 节。
"""

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage


def quantise(path, colours=18, long_side=1200):
    """把图画成 N 色，返回索引图与原始尺寸。"""
    image = Image.open(path).convert('RGB')
    scale = long_side / max(image.size)
    if scale < 1.0:
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.LANCZOS)
    small = image.quantize(colors=colours, method=Image.MEDIANCUT, dither=Image.NONE)
    return np.asarray(small, dtype=np.int32), image.size


def block_sizes(index_map):
    """每种颜色里各连通块的面积；千分之四以下的色块与四十像素以下的碎片都当噪点。"""
    sizes = []
    for value in np.unique(index_map):
        mask = index_map == value
        if mask.mean() < 0.0004:
            continue
        labelled, count = ndimage.label(mask)
        if not count:
            continue
        areas = ndimage.sum(mask, labelled, range(1, count + 1))
        sizes.extend(float(area) for area in areas if area >= 40)
    return sizes


def block_spread(index_map, pixels, floor=200.0):
    """大块内部的颜色标准差，**按面积加权**。

    **面积说不出大块是「选择」还是「没画」。** 马奈那张的 p90 是 149、最大八块吃掉六成二 —— 他的笔触是整块
    下去的，一片颜色占住画面大部分。这样的块在面积上和一片没画过的空白一模一样。区别在块里面：一片下过笔的
    颜色有自己的起伏，一片空白没有。所以量它一次，把这一列加在面积旁边。

    **必须是加权平均，不能是中位数。** 第一版取中位数，量出来油画 3.6 到 7.9、自己画的 1.1，看着分得漂亮；
    可是把苹果的偏移改小、颜色改连续之后，这个数一个点都没动。原因是中位数被「大于一千二百像素」的一大批
    小块主导，而那些块本来就只是一小片，内部当然均匀。要问的是画面的面积里有没有变化，所以按面积加权 ——
    一片七万像素的空白，比一百片一千二百像素的碎屑重要得多，而中位数给它俩同样的票。
    """
    spreads = []
    for value in np.unique(index_map):
        mask = index_map == value
        if mask.mean() < 0.0004:
            continue
        labelled, count = ndimage.label(mask)
        if not count:
            continue
        areas = ndimage.sum(mask, labelled, range(1, count + 1))
        boxes = ndimage.find_objects(labelled)
        for k, area in enumerate(areas):
            if area < floor:
                continue
            window = labelled[boxes[k]] == k + 1
            patch = pixels[boxes[k]][window]
            spreads.append((float(area), float(patch.std(axis=0).mean())))
    return spreads


def report(path, colours=18):
    image = Image.open(path).convert('RGB')
    size = image.size
    scale = 1200 / max(size)
    if scale < 1.0:
        image = image.resize((max(1, int(size[0] * scale)), max(1, int(size[1] * scale))), Image.LANCZOS)
    pixels = np.asarray(image, dtype=np.float64)
    small = image.quantize(colors=colours, method=Image.MEDIANCUT, dither=Image.NONE)
    index_map = np.asarray(small, dtype=np.int32)
    sizes = block_sizes(index_map)
    if not sizes:
        return None
    sizes = np.array(sizes)
    spreads = block_spread(index_map, pixels)
    lumped = (sum(area * spread for area, spread in spreads) / sum(area for area, _ in spreads)
              if spreads else float('nan'))
    return {'name': os.path.basename(path), 'px': size[0] * size[1], 'blocks': sizes.size,
            'median': float(np.median(sizes)), 'p90': float(np.percentile(sizes, 90)),
            'share_top': float(np.sort(sizes)[-8:].sum() / sizes.sum()),
            'spread': lumped}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--oil', default='', help='a folder of oil paintings to survey')
    parser.add_argument('--mine', default='', help='a folder of the library\'s own output to compare against')
    parser.add_argument('--colours', type=int, default=18, help='how many colours to quantise to')
    args = parser.parse_args(argv)
    paths = []
    for folder in (args.oil, args.mine):
        if folder:
            for pattern in ('*.jpg', '*.jpeg', '*.png'):
                paths += sorted(glob.glob(os.path.join(folder, pattern)))
    if not paths:
        parser.error('give --oil and/or --mine; there is nothing to measure otherwise')
    print('%-28s %10s %8s %8s %8s %9s %8s' % ('picture', 'pixels', 'blocks', 'median', 'p90', 'top8 share',
                                              'within'))
    for path in paths:
        try:
            row = report(path, args.colours)
        except Exception as error:                      # noqa: BLE001 - an unreadable file must not stop the table
            print('%-28s  %s' % (os.path.basename(path)[:28], error))
            continue
        if row:
            print('%-28s %10d %8d %8.0f %8.0f %8.1f%% %8.1f' %
                  (row['name'][:28], row['px'], row['blocks'], row['median'], row['p90'],
                   100.0 * row['share_top'], row['spread']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
