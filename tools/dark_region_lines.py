"""How much line a dark region carries, which is what "the hair reads as one solid mass" is missing.

`detail_density` was tried for this row and failed, and the reason is worth keeping: it measures contrast, and a fused
dark mass still carries rendering noise inside it, so the number barely moved (0.132 against 0.124). A line is a
different thing from contrast -- it is drawn where two areas meet -- so counting stroke points inside a dark region asks
whether anything was drawn in there at all, which is the question the row actually poses.

**What the number cannot do alone.** A dark region with few lines might be a fused mass or might be a flat area the
artist left alone; the render's own hair has both. So the reading is a comparison across regions of one picture, and
across one picture's before and after, not an absolute verdict.

    python tools/dark_region_lines.py --picture final.png --project lines.json
"""

import argparse
import json

import numpy as np
from PIL import Image
from scipy import ndimage


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--picture', required=True, help='the composited picture')
    parser.add_argument('--project', required=True, help='a project whose marks are the lines')
    parser.add_argument('--threshold', type=float, default=0.35,
                        help='luminance below which a pixel counts as dark')
    parser.add_argument('--min-share', type=float, default=0.002,
                        help='regions smaller than this share of the page are skipped')
    parser.add_argument('--top', type=int, default=8, help='how many regions to print')
    args = parser.parse_args()

    gray = np.asarray(Image.open(args.picture).convert('L'), dtype=np.float64) / 255.0
    height, width = gray.shape

    with open(args.project, encoding='utf-8') as handle:
        data = json.load(handle)
    points = []
    for mark in data['marks']:
        if mark.get('state') not in (None, 'live'):
            continue
        for point in mark.get('geometry', {}).get('centre') or []:
            points.append((point[0], point[1]))
    points = np.asarray(points, dtype=np.float64)
    print('  %d stroke points over a %dx%d picture' % (len(points), width, height))
    if not len(points):
        print('  no stroke points, so a dark region cannot be compared with anything')
        return 1

    dark = gray < args.threshold
    labels, count = ndimage.label(dark)
    # **The boxes are found once, because the first version compared the whole label image per region.** On a
    # 4915-long page that is thousands of full-image passes and it did not finish in five minutes; find_objects answers
    # the same question in one walk and lets each region be checked inside its own box.
    boxes = ndimage.find_objects(labels)
    areas = np.bincount(labels.ravel())
    floor = args.min_share * width * height
    rows = []
    for index, box in enumerate(boxes, start=1):
        if box is None:
            continue
        area = int(areas[index])
        if area < floor:
            continue
        ys, xs = box
        inside = ((points[:, 0] >= xs.start) & (points[:, 0] < xs.stop)
                  & (points[:, 1] >= ys.start) & (points[:, 1] < ys.stop))
        near = points[inside]
        if len(near):
            # **Inside the region itself, not its bounding box.** A crescent of hair has a box full of background, and
            # counting the strokes in that box would credit the hair with lines drawn somewhere else.
            keep = labels[near[:, 1].astype(np.int64), near[:, 0].astype(np.int64)] == index
            near = near[keep]
        rows.append((area, len(near)))

    rows.sort(reverse=True)
    print('  %-14s %10s %8s %12s' % ('region', 'area px', 'points', 'per 10k px'))
    for area, hits in rows[:args.top]:
        print('  %-14s %10d %8d %12.2f' % ('dark region', area, hits, 10000.0 * hits / area))
    total_area = sum(area for area, _ in rows)
    total_hits = sum(hits for _, hits in rows)
    if total_area:
        print('  %d regions, %.1f%% of the page, %.2f stroke points per 10k px'
              % (len(rows), 100.0 * total_area / (width * height), 10000.0 * total_hits / total_area))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
