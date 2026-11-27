"""Where a figure's time actually goes: rasterising, or writing the PSD.

This file was rescued from `cache/tmp`, where it had been written against the repository's previous location and then
left behind by the move from `E:` to `D:`. It is kept because the two numbers it prints are the ones that decide which
half of the pipeline is worth optimising, and nothing else in `tools/` reports them: the paint programs time their own
stages (trace, prune, simplify) but never the render or the write.

Two paths are compared rather than one, because `render_marks(sweep=...)` is a real fork in the renderer and the
difference between them is the difference between "draw the drawing" and "draw it the way the drawing is built".

**Nothing is left on disk.** The PSD is written to the working directory and removed in the same run, because a timing
probe that leaves a 2 MB artefact in the tree is a probe somebody has to clean up before committing.

    python tools/time_render.py [marks]
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineweight import core, project as project_module, psd          # noqa: E402
from lineweight import raster as r                                  # noqa: E402

W, H = 1400, 900


def build(count: int = 200):
    """A project of `count` two-point strokes spread over the canvas.

    **Random short strokes, not a drawing.** The point is to hold the mark count and the canvas size fixed while the
    two costs move, and a real drawing would confound that with its own distribution of stroke lengths.
    """
    rng = random.Random(1)
    project = project_module.Project(width=W, height=H, title='timing')
    for i in range(count):
        x0, y0 = rng.uniform(50, W - 50), rng.uniform(50, H - 50)
        record = core.stroke_record(
            [(x0, y0), (x0 + rng.uniform(-80, 80), y0 + rng.uniform(-80, 80))],
            'brush', seed=i, width_profile=[6.0, 9.0], alpha_profile=[0.5, 0.5],
            absolute_width=True, edge=4.0)
        project.add_stroke(record, stage='line', layer='LINE')
    return project


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    count = int(argv[0]) if argv else 200
    project = build(count)
    marks = [mark.to_dict() for mark in project.marks]
    print('%d marks, %dx%d' % (len(marks), W, H))

    for sweep in (False, True):
        start = time.perf_counter()
        r.render_marks(marks, W, H, sweep=sweep)
        print('render  sweep=%-5s %6.3f s' % (sweep, time.perf_counter() - start))

    layers = psd.layers_from_project(project)
    out = os.path.join(os.getcwd(), 'timing.psd')
    start = time.perf_counter()
    psd.save_psd(layers, out, width=W, height=H)
    print('psd     %d layers      %6.3f s  (%.1f KB)'
          % (len(layers), time.perf_counter() - start, os.path.getsize(out) / 1024.0))
    os.remove(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
