"""Draw the part boxes back onto the drawing, so a labelling can be checked before it is measured.

**This exists because a box being a few tenths off is invisible in a table of medians.** On the second drawing the `face`
box was drawn from the eyes to the chin, missing the cheeks; it measured last of six, and widening it to the cheek moved it
to third. One box, two places.

    python tools/draw_part_boxes.py drawing.jpg regions.json out.png
"""

import json
import sys

from PIL import Image, ImageDraw

COLOURS = {'eye': (220, 0, 0), 'face': (0, 120, 220), 'hair': (0, 160, 0),
           'cloth': (200, 120, 0), 'leg': (140, 0, 200), 'boot': (0, 140, 140)}


def main():
    image_path, regions_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    image = Image.open(image_path).convert('RGB')
    width, height = image.size
    with open(regions_path, encoding='utf-8') as handle:
        regions = json.load(handle)

    draw = ImageDraw.Draw(image)
    for part, boxes in regions.items():
        for x0, y0, x1, y1 in boxes:
            draw.rectangle([x0 * width, y0 * height, x1 * width, y1 * height],
                           outline=COLOURS.get(part, (0, 0, 0)), width=3)
    image.save(out_path)
    print('  %d parts over %dx%d -> %s' % (len(regions), width, height, out_path))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
