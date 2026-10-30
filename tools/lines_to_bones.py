"""Assign every drawn line to the bone it sits on, and report what the drawing says about each part.

**Why this can be done at all.** `render_with_bones.py` draws a picture and projects every bone into the same picture
with the same camera, so a bone's screen segment and the line beside it are in one coordinate system by construction.
This tool closes the loop: it takes the lines the render drew, reduces them to centrelines, and asks each point which
bone it is nearest to.

**What it measures, and what it does not.** A point's nearest bone is an answer about position, not about meaning: the
hair strand crossing the shoulder is nearest to the arm, and a fold in the sleeve is nearest to whichever bone the sleeve
covers. So the counts are a lower bound on how well a part is described -- a part can be under-counted because nothing is
near it, never over-counted by the distance rule alone.

    python tools/lines_to_bones.py --render out.png --bones out.json

The report is per bone family (the first word of the name) rather than per bone: 134 hair bones each holding nine points
is a different fact from one hair bone holding nine hundred, and the family line is where that shows.
"""

import argparse
import json
import re
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, __file__.rsplit('\\', 1)[0])
from copy_linework import thin
from line_width_library import line_mask


def read_render(path):
    """The line pixels of a render, as a boolean mask.

    The backdrop of a measurement render is not paper white, so a threshold on absolute darkness would count the
    backdrop or miss the line. `line_mask` asks the relative question instead: thin, and darker than its surroundings.
    """
    image = Image.open(path).convert('L')
    gray = np.asarray(image, dtype=np.float64)
    mask = line_mask(gray)
    return mask, image.size


def read_bones(path):
    """Bone screen segments, flattened to one row per bone."""
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    names, heads, tails = [], [], []
    for armature in data['armatures'].values():
        for name, bone in armature.items():
            if not bone.get('visible', True):
                continue
            names.append(name)
            heads.append(bone['head_px'])
            tails.append(bone['tail_px'])
    return names, np.asarray(heads, dtype=np.float64), np.asarray(tails, dtype=np.float64), data['size']


def nearest_bone(points, heads, tails, chunk=2048):
    """The nearest bone for each point, and how far away it is.

    **A bone is a segment, not a point**, so the distance is to the segment: clamping the projection parameter to
    0..1 means a point past the end of a limb measures to the end it passed, which is what a drawing does too.
    Points are processed in chunks because the (points x bones) array is the only thing here that grows with both.
    """
    ab = tails - heads
    denom = np.maximum((ab ** 2).sum(axis=1), 1e-9)
    index = np.empty(len(points), dtype=np.int32)
    distance = np.empty(len(points), dtype=np.float64)
    for start in range(0, len(points), chunk):
        block = points[start:start + chunk]
        ap = block[:, None, :] - heads[None, :, :]
        t = np.clip((ap * ab[None, :, :]).sum(axis=2) / denom[None, :], 0.0, 1.0)
        closest = heads[None, :, :] + t[:, :, None] * ab[None, :, :]
        gaps = np.linalg.norm(block[:, None, :] - closest, axis=2)
        index[start:start + chunk] = gaps.argmin(axis=1)
        distance[start:start + chunk] = gaps.min(axis=1)
    return index, distance


def family_of(name):
    """The part family a bone belongs to: `Hair_Pony_1` -> `hair`, `Upper_arm.L` -> `upper`."""
    word = re.split(r'[_.\s]', name)[0]
    return word.lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--render', required=True, help='the PNG the render wrote')
    parser.add_argument('--bones', required=True, help='the JSON the render wrote beside it')
    parser.add_argument('--reach', type=float, default=0.02,
                        help='a point further than this share of the picture height from any bone is unattributed')
    args = parser.parse_args()

    mask, size = read_render(args.render)
    names, heads, tails, bone_size = read_bones(args.bones)
    if tuple(size) != tuple(bone_size):
        raise SystemExit('the render is %s but the bones were projected into %s' % (size, bone_size))

    skeleton = thin(mask).astype(bool)
    ys, xs = np.nonzero(skeleton)
    points = np.stack([xs, ys], axis=1).astype(np.float64)
    print('  render       %d x %d, %d line px (%.2f%%), %d centreline points'
          % (size[0], size[1], int(mask.sum()), 100.0 * mask.sum() / mask.size, len(points)))
    if len(points) == 0:
        print('  no line was drawn, so there is nothing to assign')
        return 1

    index, distance = nearest_bone(points, heads, tails)
    limit = args.reach * size[1]
    near = distance <= limit
    print('  bones        %d, median distance %.2f px, %.1f%% of points within %.1f px'
          % (len(names), float(np.median(distance)), 100.0 * near.mean(), limit))

    counts = np.bincount(index, minlength=len(names))
    families = {}
    for name, count in zip(names, counts):
        group = families.setdefault(family_of(name), [0, 0])
        group[0] += 1
        group[1] += int(count)
    ranked = sorted(families.items(), key=lambda item: item[1][1], reverse=True)
    print('  %-16s %6s %8s %8s' % ('family', 'bones', 'points', 'share'))
    for family, (bones, count) in ranked[:16]:
        if count == 0:
            continue
        print('  %-16s %6d %8d %7.1f%%' % (family, bones, count, 100.0 * count / len(points)))
    empty = sum(1 for _family, (_bones, count) in ranked if count == 0)
    print('  families with no line at all: %d of %d' % (empty, len(ranked)))
    attributed = np.bincount(index[near], minlength=len(names))
    print('  bones holding at least one point within reach: %d of %d'
          % (int((attributed > 0).sum()), len(names)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
