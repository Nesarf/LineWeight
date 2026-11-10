"""A probe for one rendering fault: a stroke whose width profile varies came out in beads.

**What is measured.** A straight stroke is rendered through the path a picture takes -- `Project.add_stroke` and then
`render_marks(..., sweep=True)`, not `sweep_layer` called directly, which is the same function with a different route
into it -- and the alpha along its own centreline is read back.

**What it read before the repair.**

    flat profile     centre 29  profile 3  alpha 0.541..0.600  jumps  0
    varying profile  centre 43  profile 4  alpha 0.310..1.000  jumps 24

**Two faults, and only the first one was visible.** `width_profile` and `alpha_profile` hold one value per control
point, and `sweep_layer` filled them out to the resampled path with `np.resize` -- which repeats the array rather than
stretching it, so a three-value profile became 6, 24, 6, 6, 24, 6, ... and the width swung along the stroke. That is
the beading. The second fault was one level up: `stroke_layer`, the other route into the renderer, indexed the same
profile by resampled segment number, so the curve covered the first per cent of the path and the last value covered
the rest -- which is why adjusting a width curve in a painting script had almost no visible effect.

Both now interpolate by position, and this file is what says so:

    python tools/probe_stroke_dab.py

The last two lines of its output are the statement to read. `jumps` counts places along the centreline where the alpha
moves by more than twenty levels between neighbouring pixels, and a stroke that is not beaded has none.
"""
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project   # noqa: E402
from lineweight import raster as r     # noqa: E402

W, H = 260, 120
CASES = (
    ('flat profile', [13.0, 13.0, 13.0], [0.6, 0.6, 0.6]),
    ('varying profile', [7.0, 13.0, 13.0, 6.0], [0.34, 0.58, 0.56, 0.30]),
)


def centre_line(widths, alphas):
    """Render one straight stroke and report the alpha along its centreline."""
    count = len(widths)
    xs = [30.0 + 50.0 * i for i in range(count)]
    record = core.stroke_record([(x, 60.0) for x in xs], 'brush', seed=610, colour='#161c1e',
                                absolute_width=True, edge=2.0, soft=0.25,
                                width_profile=widths, alpha_profile=alphas)
    fig = project.Project(width=W, height=H, title='probe')
    fig.add_stroke(record, stage='line', layer='paint', note='')
    layer = r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True)
    data = bytes(layer.data)
    values = [data[(60 * W + x) * 4 + 3] for x in range(30, int(xs[-1]))]
    jumps = sum(1 for i in range(1, len(values)) if (values[i] - values[i - 1]) > 20)
    return record, values, jumps


def main():
    print('  points after resampling, and profile values offered:')
    for label, widths, alphas in CASES:
        record, values, jumps = centre_line(widths, alphas)
        print('    %-16s centre %2d  profile %d  alpha %.3f..%.3f  jumps %2d'
              % (label, len(record['centre']), len(widths),
                 min(values) / 255.0, max(values) / 255.0, jumps))
    print()
    print('  A flat profile must read jumps 0, and so must a varying one. A varying profile reading more than a')
    print('  handful means the fill-out repeats the array instead of stretching it, and the stroke is beaded.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
