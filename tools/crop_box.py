"""Crop one box out of an image, so a candidate error can be looked at closely before it is written down.

**A thumbnail is enough to judge whether a figure is there and not enough to judge whether a shape lost its
form.** That is not a guess: a cel-shaded reference was once read at thumbnail size and a background was taken
for a missing face.

    python tools/crop_box.py in.png out.png x0,y0,x1,y1
"""

import sys

from PIL import Image


def main():
    source, out, box = sys.argv[1], sys.argv[2], [int(value) for value in sys.argv[3].split(',')]
    image = Image.open(source)
    crop = image.crop(tuple(box))
    crop.save(out)
    print('  %s %dx%d cropped to %dx%d -> %s'
          % (source.rsplit('\\', 1)[-1], image.size[0], image.size[1], crop.size[0], crop.size[1], out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
