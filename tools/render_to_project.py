"""Turn a measurement render into a project, with every mark carrying the bone family it sits on.

**What the render gives, and what it cannot.** The same camera that drew the picture placed every bone, so a mark's part
comes from a distance rather than from a guess -- that is the whole reason this route exists. What the render does not
give is width: freestyle draws every line at one constant (`lineset.linestyle.thickness`), so the profile carried here is
that constant scaled to the page. The roles that come out are therefore only as good as the corpus behind `PART_TIERS`;
the part names are the part that is measured.

    python tools/render_to_project.py --render out.png --bones out.json --out cache/render-lines.json

The page follows the same rule as the rest of the tools: a drawing never has a long side below 2880, and never smaller
than the picture it copies. A 1024x1536 render is therefore traced at 2880.
"""

import argparse
import os
import sys

import numpy as np

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)

from copy_linework import prune, simplify, thin, trace
from lineweight import core, project
from lines_to_bones import family_of, nearest_bone, read_bones, read_render

#: **One number for the whole picture, and that is the renderer's choice rather than an artist's.** A mark's width here
#: says only that the renderer drew a line at this point. It is carried through because a project requires a width, not
#: because it is a measurement of anything -- see `AESTHETIC-LIBRARY.md` 4.30.
RENDER_WIDTH = 2.0

#: A run shorter than this is a spur hanging off a junction, not a mark a hand would make. `prune` removes those from the
#: skeleton first, and this is the second filter for whatever survives.
MIN_SEGMENT = 4


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--render', required=True, help='the PNG the render wrote')
    parser.add_argument('--bones', required=True, help='the JSON the render wrote beside it')
    parser.add_argument('--out', required=True, help='the project file to write')
    parser.add_argument('--prune', type=int, default=4, help='skeleton spurs shorter than this are cut')
    parser.add_argument('--min-segment', type=int, default=MIN_SEGMENT)
    parser.add_argument('--canvas-side', type=float, default=0.0, help='ask for a longer page than the rule gives')
    args = parser.parse_args()

    mask, size = read_render(args.render)
    names, heads, tails, bone_size = read_bones(args.bones)
    if tuple(size) != tuple(bone_size):
        raise SystemExit('the render is %s but the bones were projected into %s' % (size, bone_size))

    skeleton = prune(thin(mask.astype(np.uint8)), args.prune)
    segments = trace(skeleton)
    kept = [seg for seg in segments if len(seg) >= args.min_segment]
    print('  render      %d x %d, %d segments, %d longer than %d'
          % (size[0], size[1], len(segments), len(kept), args.min_segment))
    if not kept:
        print('  nothing to write')
        return 1

    # **The page rule the other tools use**: never below 2880 on the long side, never smaller than what it copies.
    canvas_long = max(2880.0, float(max(size)) * 1.2, float(args.canvas_side or 0.0))
    scale = canvas_long / float(max(size))
    page = project.Project(width=int(round(size[0] * scale)), height=int(round(size[1] * scale)),
                           title='lines from %s' % os.path.basename(args.render))

    # **One bone per mark, decided by the mark's middle.** A mark is short by construction -- the trace splits at every
    # junction -- so its middle is inside its own span, and the segment distance then measures a point to a limb rather
    # than to an infinitely long axis.
    middles = np.asarray([[seg[len(seg) // 2][1], seg[len(seg) // 2][0]] for seg in kept], dtype=np.float64)
    index, distance = nearest_bone(middles, heads, tails)

    families = {}
    written = 0
    for i, (seg, which) in enumerate(zip(kept, index)):
        family = family_of(names[int(which)])
        points = simplify([(float(x) * scale, float(y) * scale) for y, x in seg], 0.9)
        if len(points) < 2:
            continue
        samples = 6 * (len(points) - 1) + 1
        record = core.stroke_record(points, 'fine', seed=i, resolution=6,
                                    width_profile=[RENDER_WIDTH * scale] * samples)
        mark = page.add_stroke(record, stage='line', layer='ink',
                               note='%s near %s' % (family, names[int(which)]))
        mark.part = family
        written += 1
        families[family] = families.get(family, 0) + 1

    assigned, undecided = page.assign_roles_by_part()
    print('  marks       %d written, %d got a role' % (written, len(assigned)))
    if undecided:
        # **Grouped by part rather than listed per mark**, because the list is the finding and a list of one word
        # repeated twenty times hides it: these are the parts the corpus never compared, and how many marks each one
        # costs is what says whether the gap matters.
        tally = {}
        for name in undecided:
            tally[name] = tally.get(name, 0) + 1
        ranked_gap = sorted(tally.items(), key=lambda item: item[1], reverse=True)
        print('  undecided   %d marks over %d parts: %s'
              % (len(undecided), len(tally),
                 ', '.join('%s %d' % (name, count) for name, count in ranked_gap)))
    ranked = sorted(families.items(), key=lambda item: item[1], reverse=True)[:8]
    print('  families    %s' % '  '.join('%s %d' % (name, count) for name, count in ranked))

    out = os.path.abspath(args.out)
    folder = os.path.dirname(out)
    if folder:
        os.makedirs(folder, exist_ok=True)
    project.save_project(page, out)
    print('  written     %s' % out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
