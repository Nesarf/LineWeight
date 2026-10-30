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
import os
import re
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)

from copy_linework import thin
from lineweight.roles import role_for_part


def read_render(path):
    """The line pixels of a render, as a boolean mask.

    **A measurement render has one known backdrop, and that changes the right question.** `line_mask` asks whether a pixel
    is thin and darker than its own neighbourhood; that is the correct criterion for a painted reference, where a dark
    garment is as dark as a line. On a render it fails in a specific way: a line one pixel wide has a neighbourhood that
    is half line, so the local median sits near the line's own value and half its pixels get rejected. Measured on the
    1024 render, `line_mask` returned the line in **385 components with a median of 5 pixels** -- a dotted line rather
    than the line the renderer drew, and the cause of every broken stroke downstream.

    A flat backdrop makes the absolute question available: everything darker than a share of the backdrop is line. The
    mode is the backdrop because it covers most of the page by construction.
    """
    image = Image.open(path).convert('L')
    gray = np.asarray(image, dtype=np.float64)
    values, counts = np.unique(gray.astype(np.uint8), return_counts=True)
    background = float(values[counts.argmax()])
    mask = gray < background * 0.65
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
    """The part family a bone belongs to: `Hair_Pony_1` -> `hair`, `RightEye` -> `eye`.

    **Two naming styles sit in one rig.** `Upper_arm.L` separates with underscores; `RightEye` runs the words together
    with no separator at all. The first version took whatever stood before the first separator, which turned `RightEye`
    into a family called `righteye` -- a name that matches nothing, so the eye's line came back with no role while the
    word `eye` sat in the table the whole time. A false `none` is worse than a missing measurement: it says the corpus
    has no word for the eye.

    The side word is dropped because it says where the part is, not what it is, so `RightEye` and `LeftEye` both arrive
    at `eye` while `Upper_arm.L` keeps `upper`.
    """
    words = [w for w in re.split(r'[_.\s]', name) if w]
    if len(words) == 1:
        words = re.findall(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+', words[0]) or words
    side = {'left', 'right', 'l', 'r'}
    for word in words:
        if word.lower() not in side:
            return word.lower()
    return words[0].lower() if words else ''


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
    covered = sum(count for family, (_b, count) in ranked if role_for_part(family) is not None)
    total = sum(count for _f, (_b, count) in ranked)
    print('  %-12s %5s %7s %6s  %s' % ('family', 'bones', 'points', 'share', 'role'))
    for family, (bones, count) in ranked:
        if count == 0:
            continue
        role = role_for_part(family)
        print('  %-12s %5d %7d %5.1f%%  %s'
              % (family, bones, count, 100.0 * count / len(points), role.name if role else 'none'))
    # **The uncovered share is the measurement, not a rounding error.** A family that falls through to `none` is a part
    # the rig can name and the corpus never compared, so a line there has a position and no role.
    print('  the measured words cover %.1f%% of the line; %.1f%% has a position and no role'
          % (100.0 * covered / total if total else 0.0, 100.0 * (total - covered) / total if total else 0.0))
    empty = sum(1 for _family, (_bones, count) in ranked if count == 0)
    print('  families with no line at all: %d of %d' % (empty, len(ranked)))
    attributed = np.bincount(index[near], minlength=len(names))
    print('  bones holding at least one point within reach: %d of %d'
          % (int((attributed > 0).sum()), len(names)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
