"""Is a project the thing it was traced from? One command, six numbers, and a verdict.

**The tools this replaces were each a measurement and none of them was an acceptance.** Rendering the project was one
command, the width share another, the edge a third, and comparing them was done by eye across three terminal windows. A
layer is either inside the range its reference occupies or it is not, and that question deserves one command.

The rendering goes through `raster.render_marks`, the same renderer the picture comes from, so what is measured is what
the file draws rather than a second opinion about its geometry.

    python tools/accept.py --project cache/tmp/fidelity/150673997.json \
                           --reference downloads/pixiv-senga/150673997.jpg

**The tolerances are observations, not standards.** Thirty per cent on every ratio is what the traced copies already
achieve against their own sources -- width share 26 per cent high across eleven drawings, coverage 19 -- so it says
"within what this pipeline has demonstrated" rather than "good". A number that failed at thirty per cent would be a real
finding; a number inside it is not a pass, it is the absence of a surprise.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edge_profile  # noqa: E402
import line_agreement as la  # noqa: E402
import width_share  # noqa: E402
from lineweight import project, raster  # noqa: E402

#: How far a ratio may sit from one. See the module note: this is what the copies already do.
TOLERANCE = 0.30
#: The measures compared, as (label, key, unit). Width share and coverage come from `width_share`, the edge and the ink
#: depth from `edge_profile`; the depth spread is the p90 minus the p10, because a median cannot tell even ink from
#: patchy ink and the difference has moved a conclusion before.
WIDTH_KEYS = (('width share', 'share', '%'), ('p90 / median', 'ratio', ''), ('coverage', 'coverage', '%'))
DEPTH_KEYS = (('edge', 'edge', 'px'), ('ink depth', 'depth', ''), ('depth spread', 'spread', ''))


def render(project_path, out_path):
    """The project as a picture, through the renderer the picture comes from."""
    drawn = project.load_project(project_path)
    marks = [mark.to_dict() for mark in drawn.live()]
    if not marks:
        raise SystemExit('the project has no live marks: %s' % project_path)
    layer = raster.render_marks(marks, int(round(drawn.width)), int(round(drawn.height)), 1.0)
    raster.save_png(layer, out_path, background=(255, 255, 255))
    return drawn


def numbers(path):
    """The six quantities, or what could be measured of them, for one picture.

    **Coverage is taken from `artist_line`, not from `width_share`.** The two answer slightly different questions: that
    tool counts ink under a fixed grey threshold, because it is pricing a layer against its own span, while a trace is
    generated from the top hat's set -- and mixing them in one table produced a coverage ratio of 0.61 on a copy whose
    ink was within three per cent of its source. The width and the p90/median come from `width_share` because those are
    the same computation on both sides, which is what makes them comparable at all.
    """
    values = {}
    width = width_share.measure(path, 2880)
    if width:
        values['share'] = float(width['share'])
        values['ratio'] = float(width['ratio'])
    gray = la.load_gray(path, 2880)
    values['coverage'] = 100.0 * float(la.artist_line(gray).mean())
    rows = edge_profile.measure(path, samples=200)
    if rows:
        depths = np.array([row['depth'] for row in rows])
        values['edge'] = float(np.median([row['edge'] for row in rows]))
        values['depth'] = float(np.median(depths))
        values['spread'] = float(np.percentile(depths, 90) - np.percentile(depths, 10))
    return values


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--project', required=True, help='a version 2 project file')
    ap.add_argument('--reference', required=True, help='the picture it was traced from')
    ap.add_argument('--render', default='', help='keep the rendered PNG here (default: beside the project)')
    ap.add_argument('--tolerance', type=float, default=TOLERANCE)
    args = ap.parse_args(argv)

    out = args.render or os.path.splitext(args.project)[0] + '-rendered.png'
    drawn = render(args.project, out)
    settings = drawn.settings or {}
    print('  project    %s' % os.path.basename(args.project))
    print('  settings   %s' % (', '.join('%s=%s' % (k, v) for k, v in sorted(settings.items())) or 'not recorded'))
    print('  reference  %s' % os.path.basename(args.reference))
    print()

    traced = numbers(out)
    source = numbers(args.reference)
    print('  %-14s %10s %10s %8s %s' % ('quantity', 'reference', 'copy', 'ratio', 'within %.0f%%' % (100 * args.tolerance)))
    failures = 0
    for label, key, _unit in WIDTH_KEYS + DEPTH_KEYS:
        if key not in traced or key not in source or abs(source[key]) < 1e-9:
            print('  %-14s %10s %10s %8s   not measurable' % (label, '-', '-', '-'))
            failures += 1
            continue
        ratio = traced[key] / source[key]
        inside = abs(ratio - 1.0) <= args.tolerance
        if not inside:
            failures += 1
        print('  %-14s %10.4f %10.4f %8.3f   %s'
              % (label, source[key], traced[key], ratio, 'inside' if inside else 'OUTSIDE'))
    print()
    if failures:
        print('  %d of %d quantities sit outside the band this pipeline has demonstrated.'
              % (failures, len(WIDTH_KEYS + DEPTH_KEYS)))
    else:
        print('  every quantity sits inside the band this pipeline has demonstrated.')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
