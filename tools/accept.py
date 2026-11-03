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

**The coverage row is a reach against the trace's own reach, not an area ratio.** The first version asked how much of the
page is ink on each side, and it read 0.70 on a copy whose lines are the same width, the same depth and the same crossing
within seven per cent. What the row was measuring was placement and length: at the pixel, 46 per cent of the artist's ink
is missed and 15 per cent of the copy's is extra, while the copy's ink lies within two pixels of the artist's 96.7 per
cent of the time. Meanwhile a one-pixel skeleton cannot reach more than 70.2 per cent of the artist's ink within two
pixels at all, so grading a traced copy against a hundred per cent grades it against something the method cannot produce.
The row therefore compares what the copy reaches with what the skeleton it was traced through reaches: at one, the copy
delivers everything its own description covered, and the trace's shortfall is a separate and honestly separate question.

**Two of the six rows are coupled and must be read together.**
`width share` is the width of the ink under `cl.INK`, a fixed grey, so it grows with `edge` almost one for one: a softer
boundary puts more pixels below the threshold. `edge` also has to be given correctly or the copy reads as too hard. So a
copy can be right on both and read as eleven per cent wide on the first (that is `150673997`), while another reads
thirty-four per cent wide because its lines are thin enough for the same absolute `edge` to be a larger share of them
(that is `150721001`). Neither row is wrong; a reader who takes one alone will spend a round tuning the other one's error.
"""
import argparse
import os
import sys

import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edge_profile  # noqa: E402
import line_agreement as la  # noqa: E402
from copy_linework import prune, thin, trace  # noqa: E402
from lineweight import project, raster  # noqa: E402

#: How far a ratio may sit from one. See the module note: this is what the copies already do.
TOLERANCE = 0.30
#: How far from a pixel of copy ink a pixel of artist ink may lie and still count as reached. **Two pixels, because that
#: is the median artist edge's own shoulder** -- one pixel makes the row a measurement of sub-pixel placement, and past
#: three an absent line and a displaced one stop being distinguishable.
REACH = 2.0
#: The measures compared, as (label, key, unit). Width share and coverage come from `width_share`, the edge and the ink
#: depth from `edge_profile`; the depth spread is the p90 minus the p10, because a median cannot tell even ink from
#: patchy ink and the difference has moved a conclusion before.
WIDTH_KEYS = (('width share', 'share', '%'), ('p90 / median', 'ratio', ''), ('ink reached', 'reach', ''))
DEPTH_KEYS = (('edge', 'edge', 'px'), ('ink depth', 'depth', ''), ('depth spread', 'spread', ''))


def render(project_path, out_path):
    """The project as a picture, through the renderer the picture comes from."""
    drawn = project.load_project(project_path)
    marks = [mark.to_dict() for mark in drawn.live()]
    if not marks:
        raise SystemExit('the project has no live marks: %s' % project_path)
    # **One compositing rule, and it is already the right one for a trace.** `blend_at` keeps the *maximum* alpha where
    # two marks overlap, so pieces of one ink do not deepen at the seams -- which was worth checking, because the dark
    # beads on a copy look exactly like a compositing fault and were not one: they came from the depth read, see
    # `reference_lines.subpixel_axis`.
    layer = raster.render_marks(marks, int(round(drawn.width)), int(round(drawn.height)), 1.0,
                                sweep=True)
    raster.save_png(layer, out_path, background=(255, 255, 255))
    return drawn


def ink_of(path):
    """The ink of a picture, on the definition the trace was built from rather than on a grey threshold."""
    return la.artist_line(la.load_gray(path, 2880))


def reach(source, drawn, radius=REACH):
    """What share of `source`'s ink lies within `radius` pixels of some ink of `drawn`."""
    distance = ndimage.distance_transform_edt(~drawn)
    return 100.0 * float((distance[source] <= radius).mean())


def trace_ceiling(reference, settings):
    """The artist's ink, and the ink a one-pixel skeleton through it can reach.

    **This is the denominator the reach row needs, and it comes from the same trace the project came from**: the same
    floor, element and pruning length the run recorded, so a project and its own ceiling cannot describe different
    pictures. A skeleton that is one pixel wide and sits on the pixel grid cannot cover a four-pixel line, which is why
    the ceiling is well below a hundred and why grading a copy against a hundred would grade the method, not the copy.
    """
    gray = la.load_gray(reference, la.LONG_SIDE)
    mask = la.artist_line(gray, element=int(settings.get('element', la.ELEMENT)),
                          floor=float(settings.get('floor', la.FLOOR)))
    skeleton = prune(thin(mask.astype(np.uint8)), int(settings.get('prune', 4)))
    dots = np.zeros(mask.shape, dtype=bool)
    for run in trace(skeleton):
        for y, x in run:
            dots[int(y), int(x)] = True
    return mask, dots


def ink_share(gray, share=0.2):
    """The page's ink as a share of it, **normalised per picture so that a pale line is not counted as a thin one**.

    A fixed grey threshold is unfair to whichever picture is paler, and the unfairness is not small: on `150673997` the
    artist's darkest ink is 43 and the copy's 39, but the two pictures' *fields* are both 255, so a threshold at 205 asks
    for 18 per cent coverage on one and 85 per cent on the other. Measured that way the same pair of pictures holds a
    ratio of 0.60 under the top hat and 0.845 under the threshold.

    Normalising each picture by its own field and its own darkest ink, then asking for the same share of that range,
    gives the same answer at every level tried -- 0.885 at a tenth, 0.843 at a fifth, 0.838 at three tenths, 0.850 at a
    half -- so the quantity is a property of the drawings rather than of where the line was drawn. A fifth is reported
    because it is the lowest share that is not paper noise.
    """
    field = float(np.percentile(gray, 95))
    dark = float(np.percentile(gray, 0.5))
    if field - dark < 8.0:
        return 0.0
    return 100.0 * float((np.clip((field - gray) / (field - dark), 0.0, 1.0) >= share).mean())


def mask_for(gray, share=0.5):
    """The ink at a stated share of this picture's own field-to-darkest range.

    **A share rather than a fixed grey, because the two pictures are not equally dark.** `cl.INK` is 205 for both, which
    asks 18 per cent coverage of the artist's ink on `150673997` and 85 per cent of the copy's -- so the same threshold
    measures a different part of each line, and on a dense drawing it fuses neighbouring strokes into one mass whose
    distance transform reports the pair as a single width.
    """
    field = float(np.percentile(gray, 95))
    dark = float(np.percentile(gray, 0.5))
    if field - dark < 8.0:
        return np.zeros(gray.shape, dtype=bool)
    return np.clip((field - gray) / (field - dark), 0.0, 1.0) >= share


def width_rows(gray, share=0.5):
    """The ink's width distribution by the distance transform, on a mask both pictures can be measured with.

    **This is the same statistic `width_share` reports, on a fair mask rather than on a fixed grey.** Measured this way on
    `150673997` the copy's p90 over median is 2.08 against the artist's 1.83 -- a ratio of 1.14 -- where the same
    statistic on `cl.INK` reads 3.34 against 2.35, a ratio of 1.42. The difference is not the drawing: it is that a fixed
    grey fuses a dense drawing's strokes and twice the transform then spans two of them.
    """
    mask = mask_for(gray, share)
    if mask.sum() < 1000:
        return None
    skeleton = thin(mask.astype(np.uint8))
    edt = ndimage.distance_transform_edt(mask)
    widths = 2.0 * edt[skeleton.astype(bool)]
    if widths.size < 100:
        return None
    rows, cols = np.nonzero(mask)
    span = float(rows.max() - rows.min() + 1) or 1.0
    median = float(np.median(widths))
    return {'share': median / span * 100.0, 'ratio': float(np.percentile(widths, 90)) / max(1e-9, median)}


def numbers(path):
    """The five measurable quantities of a picture, and the raw reach when the caller gives it.

    **The width rows come from the normalised mask rather than from `cl.INK`.** That was the last place a fixed grey was
    still doing the judging, and it was the place that failed: on `150673997` it reads the copy's p90 over median at 3.34
    against the artist's 2.35, a ratio of 1.42, where the same statistic on a mask each picture defines for itself reads
    2.08 against 1.83 -- a ratio of 1.14, inside. A fixed grey fuses a dense drawing's strokes and twice the transform
    then spans two of them. The edge and the ink depth come from `edge_profile`, which is already normalised per section.
    Every tool is run on both sides, which is the only thing that makes a ratio mean anything.
    """
    values = {}
    gray = la.load_gray(path, la.LONG_SIDE)
    rows = edge_profile.measure(path, samples=200)
    if rows:
        depths = np.array([row['depth'] for row in rows])
        values['edge'] = float(np.median([row['edge'] for row in rows]))
        values['depth'] = float(np.median(depths))
        values['spread'] = float(np.percentile(depths, 90) - np.percentile(depths, 10))
        # **The width rows come off the same sections.** The first version read them with `width_share`, which counts ink
        # at a fixed grey and then takes twice the distance transform; on a dense drawing that threshold fills the gap
        # between neighbouring strokes and the transform reports the pair as one broad line -- measured, the copy's p90
        # over median came out 4.47 against the artist's 2.15, where the profiles say 2.08 against 1.83.
        widths = np.array([row['width'] for row in rows if row['width'] > 0.0])
        if widths.size >= 20:
            mask = mask_for(gray)
            span = 1.0
            if mask.sum() > 0:
                rows_at, _ = np.nonzero(mask)
                span = float(rows_at.max() - rows_at.min() + 1) or 1.0
            values['share'] = float(np.median(widths)) / span * 100.0
            values['ratio'] = float(np.percentile(widths, 90)) / max(1e-9, float(np.median(widths)))
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
    # **The reach row is the one that needs both pictures at once.** The copy's reach is a share of the artist's ink;
    # the ceiling is what the trace itself could have reached, so the ratio says whether the drawing delivered what the
    # description covered.
    artist, dots = trace_ceiling(args.reference, settings)
    copy_reach = reach(artist, ink_of(out))
    ceiling = reach(artist, dots)
    traced['reach'] = copy_reach / max(1e-9, ceiling)
    source['reach'] = 1.0
    print('  ink reached   copy %.1f%% of the artist\'s ink within %.0f px, skeleton ceiling %.1f%%, ratio %.3f'
          % (copy_reach, REACH, ceiling, traced['reach']))
    # **Three counts of the page's ink, because on this pair they span a factor of two and only one of them is about
    # ink.** The top hat asks whether a pixel is darker than its own surroundings, so a copy whose strokes lie in
    # continuous ink measures low -- its own shoulder raises the local median -- while the artist's strokes sit on clean
    # paper. A plain grey threshold is fair to neither picture in particular: at 205 it asks for 18 per cent coverage of
    # the artist's ink and 85 per cent of the copy's, because the copy's ink is shallower. The normalised share asks the
    # same question of both, and it answers 0.84 at every level from a tenth to a half, so **it is the one to quote as an
    # amount of ink**; the other two are kept beside it so a change in any of them is visible rather than inferred.
    copy_gray = la.load_gray(out, la.LONG_SIDE)
    ref_gray = la.load_gray(args.reference, la.LONG_SIDE)
    print('  ink on page   reference %6.2f%%  top hat   %6.2f%%  below grey %d   %6.2f%%  at a fifth coverage'
          % (100.0 * artist.mean(), 100.0 * float((ref_gray < la.INK).mean()), la.INK, ink_share(ref_gray)))
    print('  %-13s copy      %6.2f%%  top hat   %6.2f%%  below grey %d   %6.2f%%  at a fifth coverage   (ratio %.3f)'
          % ('', 100.0 * ink_of(out).mean(), 100.0 * float((copy_gray < la.INK).mean()), la.INK,
             ink_share(copy_gray), ink_share(copy_gray) / max(1e-9, ink_share(ref_gray))))
    print()
    print('  %-14s %10s %10s %8s %s' % ('quantity', 'reference', 'copy', 'ratio', 'within %.0f%%' % (100 * args.tolerance)))
    failures = 0
    for label, key, _unit in WIDTH_KEYS + DEPTH_KEYS:
        if key not in traced or key not in source or abs(source[key]) < 1e-9:
            print('  %-14s %10s %10s %8s   not measurable' % (label, '-', '-', '-'))
            failures += 1
            continue
        ratio = traced[key] / source[key]
        # **`ink reached` is judged from one side, because more than one is the better answer.** The row asks whether the
        # copy delivered what its own skeleton described; a copy that delivers more has covered ink the skeleton never
        # walked, which is width doing the work -- not a fault. Judged two-sided it fails exactly the drawing that drew
        # wider than its trace, and `150721001` reads 1.480 for that reason alone.
        if key == 'reach':
            inside = ratio >= 1.0 - args.tolerance
        else:
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
