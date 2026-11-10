"""三远并排：**同一片山，三种看它的方式。**

`paint_landscape.py` 一次只画一场，而三远的意思是**三者互相对照才成立** —— 郭熙把它们写在同一个句子里，并且
给每一条四样东西（眼睛在哪里、颜色怎样、体势怎样、人在里面多大）。单看一张，那是「一座山」；三张并排，才看得
见「这三张是同一种能力的三档」：脊的平滑遍数、层的数量与深度、浓度是往回走还是往下走、有没有水、有没有水花。

所以这个文件不画任何东西。它只做两件事：**把三张缩到同一个尺寸**，和**写上它们各自的名字**。

**名字用拼音加英文释义，不用汉字。** PIL 自带的字体没有中文字形，而为了两个字的标签去装一份字体，比这个工具本身
重得多。英文在这里是排版的需要，不是内容的需要。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SRC = os.environ.get('LAND_OUT') or os.path.join(os.getcwd(), 'landscape')
OUT = os.environ.get('TRIPTYCH_OUT') or SRC
TILE_W, TILE_H = 700, 450
LABEL_H = 56
PAPER = (232, 226, 212)
INK = (86, 80, 72)

SCENES = (
    ('ping', 'PING YUAN', 'from a near mountain looking at far ones'),
    ('gao', 'GAO YUAN', 'from the foot looking up at the summit'),
    ('shen', 'SHEN YUAN', 'from in front looking past to behind'),
)


def main():
    font = ImageFont.load_default()
    sheet = Image.new('RGB', (TILE_W * len(SCENES), TILE_H + LABEL_H), PAPER)
    draw = ImageDraw.Draw(sheet)
    for index, (name, title, gloss) in enumerate(SCENES):
        path = os.path.join(SRC, 'landscape-%s.png' % name)
        if not os.path.exists(path):
            print('  missing %s -- run tools/paint_landscape.py with LAND_MODE=%s first' % (path, name))
            return 1
        tile = Image.open(path).convert('RGB').resize((TILE_W, TILE_H), Image.LANCZOS)
        left = TILE_W * index
        sheet.paste(tile, (left, 0))
        draw.text((left + 20, TILE_H + 10), title, fill=INK, font=font)
        draw.text((left + 20, TILE_H + 28), gloss, fill=INK, font=font)
        if index:
            draw.line([(left, 0), (left, TILE_H + LABEL_H)], fill=(214, 207, 192), width=2)
    out = os.path.join(OUT, 'landscape-triptych.png')
    sheet.save(out)
    print('%s  %dx%d' % (out, sheet.width, sheet.height))
    return 0


if __name__ == '__main__':
    sys.exit(main())
