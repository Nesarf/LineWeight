"""A probe for one rendering fault: a stroke whose width profile varies comes out in beads.

**What is measured.** A straight stroke is rendered through the path a picture takes -- `Project.add_stroke` and then
`render_marks(..., sweep=True)`, not `sweep_layer`, which is a different loop -- and the alpha along its own centreline
is read back. A stroke with one width value is flat along its length. A stroke with four width values is not: it swings
between about 0.31 and 1.00 with a period near eight pixels, and the picture shows it as separate discs.

**Two numbers that make the fault visible, and the second one is not what it looks like.**

    python tools/probe_stroke_dab.py

The centre of a four-point stroke is resampled to forty-three points, while the profile keeps four values. The renderer
indexes the profile by the resampled segment number, so **the profile covers the first seven per cent of the path and the
last value covers everything after it.** That is why adjusting a width curve here has almost no visible effect, and it
is a separate fault from the beading -- although a bead and a width that jumps in the same place are easy to mistake for
one another.

**Not fixed here.** The repair is a resample of the profile against arc length before the dab loop, and it changes every
painting already made; it needs its own round and its own before-and-after picture. This file exists so the measurement
is not lost, and so the day it is fixed there is something to compare against.
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
    print('  A flat profile must read jumps 0. A varying one reading more than a handful is the fault.')
    print('  The profile covers ceil(profile / centre) of the path; the rest takes the last value.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
