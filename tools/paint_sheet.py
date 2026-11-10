"""把这条线画过的六张放在一张纸上：**一条线的能力，一眼可见。**

它不是一张画，也不是一个工具的输出模板 —— 它是一个**目录**：每一格说明一种画法能立住什么，而六格合起来说明这个库
现在会做什么、不会做什么。

选择哪六张是有意的，它按媒介与手段分开：

```
油画（掩膜与裁）    苹果、布、两只果子、鱼
水墨（减法与留白）  没骨的鱼、三远
```

前四张是加法：算出形，然后把墨放上去。后两张有一半是减法：被画下来的不是水，是水两侧的石头。**而两种手段在同一个
库里，用的是一套 `stroke_record` 与一套 `render_marks`** —— 那一句才是这张纸想说的。

标签用英文，理由和 `landscape_triptych.py` 相同：PIL 自带字体没有中文字形，而为了几个标签装一份字体比这个工具本身
重得多。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SRC = os.environ.get('PAINT_OUT') or os.path.join(r'E:\DaShaoHuo\cache\paint')
OUT = os.environ.get('SHEET_OUT') or SRC
TILE_W, TILE_H = 620, 399
LABEL_H = 58
COLS, ROWS = 3, 2
PAPER = (232, 226, 212)
INK = (84, 78, 70)

TILES = (
    ('apple', 'APPLE', 'oil - 520 arcs around a core'),
    ('cloth', 'CLOTH', 'oil - contour first, then clip'),
    ('pair', 'TWO FRUIT', 'oil - depth by dimming and order'),
    ('fish', 'FISH', 'oil - mask, distance field, gradient'),
    ('ink', 'MOGU FISH', 'ink - nine strokes, edges by union'),
    ('landscape-shen', 'THREE DISTANCES', 'ink - subtraction, blank paper'),
)


def main():
    font = ImageFont.load_default()
    sheet = Image.new('RGB', (TILE_W * COLS, (TILE_H + LABEL_H) * ROWS), PAPER)
    draw = ImageDraw.Draw(sheet)
    for index, (name, title, gloss) in enumerate(TILES):
        path = os.path.join(SRC, '%s.png' % name)
        if not os.path.exists(path):
            print('  missing %s' % path)
            return 1
        tile = Image.open(path).convert('RGB')
        # **按比例放进去，不裁。** 第一版把每一格裁成 16:10，于是那块竖构图的布被裁成一条中间带 —— 一个总览如果
        # 让每一格失真，它就不是目录。留纸边比删内容诚实，而格子本身就是纸色。
        width, height = tile.size
        scale = min(TILE_W / float(width), TILE_H / float(height))
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
        fitted = tile.resize(size, Image.LANCZOS)
        cell = Image.new('RGB', (TILE_W, TILE_H), PAPER)
        cell.paste(fitted, ((TILE_W - size[0]) // 2, (TILE_H - size[1]) // 2))
        left = TILE_W * (index % COLS)
        top = (TILE_H + LABEL_H) * (index // COLS)
        sheet.paste(cell, (left, top))
        draw.rectangle([left, top, left + TILE_W - 1, top + TILE_H - 1], outline=(214, 207, 192))
        draw.text((left + 16, top + TILE_H + 10), title, fill=INK, font=font)
        draw.text((left + 16, top + TILE_H + 30), gloss, fill=INK, font=font)
    out = os.path.join(OUT, 'paint-sheet.png')
    sheet.save(out)
    print('%s  %dx%d' % (out, sheet.width, sheet.height))
    return 0


if __name__ == '__main__':
    sys.exit(main())
