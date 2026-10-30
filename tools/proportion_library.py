"""Proportions measured from line drawings: head height, shoulder width, and the ratio between them.

**Where the numbers come from.** A figure's outline, read row by row, has a profile: a narrow band at the top that is the
head, a pinch below it that is the neck, and a sudden widening that is the shoulders. Those three features are enough to
put the two most basic proportions of a character on a number -- how tall the figure is in heads, and how wide the
shoulders are in heads -- without knowing anything about the picture beyond its ink.

**What this cannot do.** It finds the neck by looking for a pinch in the outline, so a figure with a high collar, hair over
the shoulders, or no neck visible at all has no pinch and is refused rather than guessed at. That refusal rate is part of
the result: a measurement that works on half the corpus and says so is worth more than one that silently reports the
hairline as a chin.

    python tools/proportion_library.py --glob "E:\\DaShaoHuo\\downloads\\pixiv-senga\\*.jpg" --limit 61
"""

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for extra in (ROOT, HERE):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np                       # noqa: E402
from PIL import Image                    # noqa: E402
from scipy import ndimage                # noqa: E402

import line_width_library as L           # noqa: E402


def profile(mask):
    """How many pixels wide each row of the **filled** figure is.

    **A line drawing is lines, so counting ink is not counting width.** The first version of this summed the ink per row,
    which on a face gives the two strokes either side of it -- four pixels, whatever the head's actual width. Measured that
    way the survey reported heads 1.79 times wider than tall, which no head is.

    So the mass is filled first: a closing pass bridges the small gaps a sketched contour leaves, and a hole fill turns
    the outline into a solid. Everything the measurement needs is outside the figure, and after this the outline is the
    figure.
    """
    return mask.sum(axis=1).astype(np.float32)


def smooth(values, window=9):
    """A moving average, so a single row of noise does not become a local maximum."""
    if values.size < window:
        return values
    kernel = np.ones(int(window), dtype=np.float32) / float(window)
    return np.convolve(values, kernel, mode='same')


def landmarks(mask):
    """The top of the head, the neck and the shoulders, or `None` when the outline has no neck to find.

    **Three features, in order.** The head is the first wide band; the neck is the first deep pinch under it; the shoulders
    are the widening after the pinch. A figure whose outline never pinches -- a cloak, a high collar, arms raised -- has no
    neck to find, and this returns None instead of calling the first narrowing a chin.
    """
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size < 40:
        return None
    top, bottom = int(rows[0]), int(rows[-1])
    height = bottom - top + 1
    width = smooth(profile(mask)[top:bottom + 1])
    if width.max() < 8:
        return None
    # The head band lives in the top third; its widest row is the widest the head gets.
    third = max(8, height // 3)
    head_peak = int(np.argmax(width[:third]))
    # The neck is the narrowest row between the head's peak and the shoulders' likely place, and it must be a real pinch.
    search_end = min(height - 8, max(head_peak + 6, int(height * 0.45)))
    if search_end <= head_peak + 4:
        return None
    neck = head_peak + int(np.argmin(width[head_peak:search_end]))
    if width[neck] > 0.85 * width[head_peak]:
        return None                        # no pinch: this figure's outline does not show a neck
    # The shoulders are the widest row below the neck, inside the top two thirds.
    shoulder_end = min(height, max(neck + 6, int(height * 0.65)))
    shoulder = neck + int(np.argmax(width[neck:shoulder_end]))
    if width[shoulder] < 1.05 * width[head_peak]:
        return None                        # the outline never widens again: not a standing figure
    return {'top': top, 'neck': top + neck, 'shoulder': top + shoulder,
            'head_width': float(width[head_peak]), 'shoulder_width': float(width[shoulder]),
            'figure_height': int(height)}


def proportions_of(path, long_side=1600):
    image = Image.open(path).convert('L')
    scale = min(1.0, long_side / float(max(image.size)))
    if scale < 1.0:
        image = image.resize((max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale))), Image.LANCZOS)
    gray = np.asarray(image, dtype=np.float32)
    mask = L.ink_mask(gray)
    stats = L.figure_stats(mask)
    if stats['box'] is None:
        return None
    y0, y1, x0, x1 = stats['box']
    mass = np.zeros_like(mask)
    labelled, count = ndimage.label(mask)
    if count == 0:
        return None
    sizes = np.bincount(labelled.ravel())
    sizes[0] = 0
    mass = labelled == int(sizes.argmax())
    # **Fill before measuring.** A sketched contour is a line, not a boundary of ink: without this, a row across a face
    # counts the two strokes either side of it. Closing bridges the gaps a hand-drawn outline leaves at the shoulder and
    # the waist, and the hole fill makes the interior part of the figure.
    mass = ndimage.binary_closing(mass, iterations=3)
    mass = ndimage.binary_fill_holes(mass)
    found = landmarks(mass)
    if found is None:
        return {'name': pathlib.Path(path).name, 'refused': 'no neck in the outline'}
    head = found['neck'] - found['top']
    if head < 10:
        return {'name': pathlib.Path(path).name, 'refused': 'head shorter than ten pixels'}
    return {'name': pathlib.Path(path).name,
            'figure_height': found['figure_height'],
            'head_height': head,
            'head_width': found['head_width'],
            'shoulder_width': found['shoulder_width'],
            'heads_tall': found['figure_height'] / float(head),
            'shoulders_in_heads': found['shoulder_width'] / float(head),
            'head_aspect': found['head_width'] / float(head)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glob', required=True)
    ap.add_argument('--limit', type=int, default=40)
    ap.add_argument('--long-side', type=int, default=1600)
    args = ap.parse_args()

    folder = pathlib.Path(args.glob).parent
    files = sorted(folder.glob(pathlib.Path(args.glob).name))[:args.limit]
    print('  %d files, measuring head height against the outline' % len(files))
    usable, refused = [], []
    for path in files:
        try:
            result = proportions_of(path, args.long_side)
        except Exception as problem:                       # a broken file must not stop the survey
            refused.append((path.name, str(problem)))
            continue
        if result is None:
            refused.append((path.name, 'too little ink'))
        elif 'refused' in result:
            refused.append((path.name, result['refused']))
        else:
            usable.append(result)
            print('  %-24s heads %5.2f   shoulders %5.2f heads   head aspect %.2f'
                  % (path.name[:24], result['heads_tall'], result['shoulders_in_heads'], result['head_aspect']))

    print()
    if refused:
        print('  refused %d of %d:' % (len(refused), len(files)))
        for name, why in refused[:8]:
            print('    %-24s %s' % (name[:24], why))
        if len(refused) > 8:
            print('    ... %d more' % (len(refused) - 8))
    if len(usable) < 3:
        print('  too few usable drawings to report a distribution')
        return 1
    for key, label in (('heads_tall', 'figure height in heads'),
                       ('shoulders_in_heads', 'shoulder width in heads'),
                       ('head_aspect', 'head width over head height')):
        values = np.array([row[key] for row in usable])
        print('  %-28s median %.2f   p10 %.2f   p90 %.2f   n %d'
              % (label, float(np.median(values)), float(np.percentile(values, 10)),
                 float(np.percentile(values, 90)), values.size))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
