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
import subprocess
import sys

import numpy as np

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)

from copy_linework import prune, simplify, thin, trace
from lineweight import core, project
from lineweight.roles import role_for_part
from lines_to_bones import family_of, nearest_bone, read_bones, read_render

#: **One number for the whole picture, and that is the renderer's choice rather than an artist's.** A mark's width here
#: says only that the renderer drew a line at this point. It is carried through because a project requires a width, not
#: because it is a measurement of anything -- see `AESTHETIC-LIBRARY.md` 4.30.
RENDER_WIDTH = 2.0

#: A run shorter than this is a spur hanging off a junction, not a mark a hand would make. `prune` removes those from the
#: skeleton first, and this is the second filter for whatever survives.
MIN_SEGMENT = 4


def stitch(segments, gap=2.0, straight=0.5, rounds=20):
    """Join the runs whose ends meet, when the direction says one line continues through the join.

    **Why this is needed at all.** A hand-drawn line ends at two points, so `copy_linework`'s walk starts at one end and
    arrives at the other. A render's contour is closed: the skeleton has almost no degree-one ends, so `trace` falls back
    to starting from arbitrary points, and its walks cancel each other through `used`. Measured at 2048, one connected
    component of 32126 skeleton pixels came back as **3240 runs with a median of three pixels** -- the pixels were
    continuous, the runs were not. The drawing then read as dashes, which is a failure of granularity rather than of
    geometry.

    `gap` is in pixels: two ends further apart than this are two different lines meeting near each other, which is what a
    crossing looks like. `straight` is the cosine below which a join is refused -- a corner is also two runs meeting, and
    joining across it would round off the one thing a corner is.

    **Either end joins, because a closed contour is walked from both ways.** Restricting joins to a tail meeting a head
    halved the runs at 1024 and left two thirds of them at 2048, and the reason is visible in what a closed loop does: the
    first walk goes round one way and the run that meets it arrives going the other way, so a tail-to-head test refuses
    exactly the joins a contour needs. A tail therefore joins a tail by reversing it, which is the same line read
    backwards rather than a different claim.
    """
    paths = [[(float(y), float(x)) for y, x in seg] for seg in segments]
    for _ in range(rounds):
        ends = {}
        for i, path in enumerate(paths):
            if len(path) < 2:
                continue
            ends.setdefault((int(path[0][0] // gap), int(path[0][1] // gap)), []).append((i, 0))
            ends.setdefault((int(path[-1][0] // gap), int(path[-1][1] // gap)), []).append((i, 1))
        joined = 0
        for i, path in enumerate(paths):
            if len(path) < 2:
                continue
            tail = path[-1]
            step_y = path[-1][0] - path[-2][0]
            step_x = path[-1][1] - path[-2][1]
            span = (step_y * step_y + step_x * step_x) ** 0.5
            if span == 0.0:
                continue
            best = None
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    cell = (int(tail[0] // gap) + oy, int(tail[1] // gap) + ox)
                    for j, which in ends.get(cell, ()):
                        if j == i or len(paths[j]) < 2:
                            continue
                        other = paths[j]
                        near, nxt = (other[0], other[1]) if which == 0 else (other[-1], other[-2])
                        away = ((near[0] - tail[0]) ** 2 + (near[1] - tail[1]) ** 2) ** 0.5
                        if away > gap:
                            continue
                        next_y = nxt[0] - near[0]
                        next_x = nxt[1] - near[1]
                        next_span = (next_y * next_y + next_x * next_x) ** 0.5
                        if next_span == 0.0:
                            continue
                        if (step_y * next_y + step_x * next_x) / (span * next_span) < straight:
                            continue
                        if best is None or away < best[0]:
                            best = (away, j, which)
            if best is not None:
                _away, j, which = best
                paths[i] = paths[i] + (paths[j] if which == 0 else paths[j][::-1])
                paths[j] = []
                joined += 1
        if not joined:
            break
    return [path for path in paths if len(path) >= 2]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--blend', help='a .blend to render first; the picture and the bones land beside --out')
    parser.add_argument('--blender', default=r'E:\Blender Foundation\Blender 4.4\blender.exe',
                        help='the Blender used when --blend is given')
    parser.add_argument('--size', default='2048x3072',
                        help='page size when rendering a .blend; 1024 leaves a fifth of the skeleton unwalked')
    parser.add_argument('--render', help='the PNG the render wrote')
    parser.add_argument('--bones', help='the JSON the render wrote beside it')
    parser.add_argument('--out', required=True, help='the project file to write')
    parser.add_argument('--prune', type=int, default=4, help='skeleton spurs shorter than this are cut')
    parser.add_argument('--min-segment', type=int, default=MIN_SEGMENT)
    parser.add_argument('--stitch-reach', type=float, default=0.0035,
                        help='how far apart two ends may be, as a share of the page long side; 0 turns stitching off')
    parser.add_argument('--stitch-straight', type=float, default=0.0,
                        help='cosine below which a join is a corner rather than a continuation')
    parser.add_argument('--canvas-side', type=float, default=0.0, help='ask for a longer page than the rule gives')
    args = parser.parse_args()

    if args.blend:
        # **One command from a rig to a project, because four runs taught the parameters and a fifth would not.** The
        # size lives here rather than in `render_with_bones.py` because 1024 is a fine page for other studies and a
        # broken one for this: at 1024 the skeleton is 7991 pixels and the walk leaves 621 of them unvisited, against 4
        # at 2048. A default that silently produces a dashed drawing is the failure this option exists to prevent.
        stem = os.path.splitext(os.path.abspath(args.out))[0]
        args.render = stem + '.png'
        args.bones = stem + '-bones.json'
        print('  rendering   %s at %s' % (os.path.basename(args.blend), args.size))
        command = [args.blender, '--background', '--factory-startup',
                   '--python', os.path.join(TOOLS, 'render_with_bones.py'),
                   '--', args.blend, args.render, args.bones, '--freestyle', '--size', args.size]
        result = subprocess.run(command, capture_output=True, text=True)
        if not os.path.exists(args.bones):
            # **The failure is printed rather than raised blind**, because the likely causes are a Blender that is not
            # where this file thinks and a scene whose rig it cannot read -- and each has its own line in the output.
            print((result.stdout or '')[-1500:])
            print((result.stderr or '')[-1500:])
            raise SystemExit('Blender wrote no bones, so there is nothing to measure')
    elif not (args.render and args.bones):
        parser.error('give --blend, or both --render and --bones')

    mask, size = read_render(args.render)
    names, heads, tails, bone_size = read_bones(args.bones)
    if tuple(size) != tuple(bone_size):
        raise SystemExit('the render is %s but the bones were projected into %s' % (size, bone_size))

    skeleton = prune(thin(mask.astype(np.uint8)), args.prune)
    runs = trace(skeleton)
    if args.stitch_reach > 0:
        # **The reach scales with the page, because the gap it bridges does.** Measured on the same drawing at two sizes
        # the useful distance was 5.4 px at 1024 and 10.8 px at 2048 -- 0.35 per cent of the long side either way. Held
        # at a constant, a value that works at one size is a no-op at the other.
        segments = stitch(runs, gap=args.stitch_reach * float(max(size)), straight=args.stitch_straight)
    else:
        segments = runs
    kept = [seg for seg in segments if len(seg) >= args.min_segment]
    # **Both counts, because the pair is the measurement.** The traced number says what the walk produced; the stitched
    # one says how much of that was one line cut into pieces.
    print('  render      %d x %d, %d traced, %d after stitching, %d longer than %d'
          % (size[0], size[1], len(runs), len(segments), len(kept), args.min_segment))
    if not kept:
        print('  nothing to write')
        return 1

    # **The page rule the other tools use**: never below 2880 on the long side, never smaller than what it copies.
    canvas_long = max(2880.0, float(max(size)) * 1.2, float(args.canvas_side or 0.0))
    scale = canvas_long / float(max(size))
    page = project.Project(width=int(round(size[0] * scale)), height=int(round(size[1] * scale)),
                           title='lines from %s' % os.path.basename(args.render))

    # **A run is filed only when both of its ends agree on the part.** Three rules were tried and two failed in ways worth
    # recording. The middle: `eye` got nothing, because the run holding the lid's pixels had its middle out on the hair.
    # The vote: `skirt` fell from 10217 to 6333 px and `lower` rose from 1829 to 5860, because a skirt contour that sweeps
    # past the legs spends most of its pixels near them -- a majority is a majority of pixels, not of meaning.
    #
    # So neither one point nor a majority settles it. A run whose two ends land in different families is counted as
    # crossing and left without a part, which is the same choice `role_for_part` makes when it returns None: a part nobody
    # has decided about must not be filled in with the part that happens to touch it most.
    ends = np.asarray([[seg[0][1], seg[0][0]] for seg in kept]
                      + [[seg[-1][1], seg[-1][0]] for seg in kept], dtype=np.float64)
    end_index, _distance = nearest_bone(ends, heads, tails)
    half = len(kept)
    chosen = []
    crossing = 0
    for first, last in zip(end_index[:half], end_index[half:]):
        one = family_of(names[int(first)])
        other = family_of(names[int(last)])
        if one == other:
            chosen.append(one)
        else:
            chosen.append(None)
            crossing += 1

    families = {}
    lengths = {}
    written = 0
    for i, seg in enumerate(kept):
        family = chosen[i]
        if family is None:
            continue
        # **Length rather than point count.** A run is a pixel chain, so its length is its number of pixels; counting
        # sampled control points would weight a straight run and a wiggly one differently for no reason.
        lengths[family] = lengths.get(family, 0) + len(seg)
        points = simplify([(float(x) * scale, float(y) * scale) for y, x in seg], 0.9)
        if len(points) < 2:
            continue
        samples = 6 * (len(points) - 1) + 1
        record = core.stroke_record(points, 'fine', seed=i, resolution=6,
                                    width_profile=[RENDER_WIDTH * scale] * samples)
        mark = page.add_stroke(record, stage='line', layer='ink',
                               note='%s near %s' % (family, chosen[i]))
        mark.part = family
        written += 1
        families[family] = families.get(family, 0) + 1

    assigned, undecided = page.assign_roles_by_part()
    print('  marks       %d written, %d got a role, %d crossing two parts'
          % (written, len(assigned), crossing))
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
    # **What the render can say about a part, in the one currency it has.** It cannot say how wide a line is -- freestyle
    # draws every line at one constant -- but it can say how much line each part carries and how long its runs are. If the
    # measured tiers show a pattern here (short runs where the corpus draws heavy, long runs where it draws light) then
    # length stands in for width; if they do not, length is a separate fact and the table needs both columns.
    total_length = sum(lengths.values()) or 1
    print('  %-12s %6s %8s %8s %7s  %s' % ('part', 'marks', 'length', 'mean', 'share', 'role'))
    for family, count in sorted(families.items(), key=lambda item: item[1], reverse=True):
        total = lengths.get(family, 0)
        role = role_for_part(family)
        print('  %-12s %6d %8d %8.1f %6.1f%%  %s'
              % (family, count, total, total / count, 100.0 * total / total_length,
                 role.name if role else 'none'))

    out = os.path.abspath(args.out)
    folder = os.path.dirname(out)
    if folder:
        os.makedirs(folder, exist_ok=True)
    project.save_project(page, out)
    print('  written     %s' % out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
