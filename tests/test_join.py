"""Joining the pieces of one stroke, and refusing to join two strokes that merely meet.

The tracer breaks a skeleton at every branch, so one of the artist's strokes arrives as two to five runs. Drawing them
separately gives a chain of round-capped capsules and the union's edge is scalloped -- visible in the magnified copy of
`150673997` and not fixable with alpha or edge, because it is the shape of the union. The join is therefore geometry:
ends within one line's width, with the two runs' inward directions opposed, one end used once.

The tests are about the two ways this can be wrong. It can fail to join a stroke that bends, which leaves the scallop;
and it can join two strokes that cross, which turns two lines into one and changes the drawing rather than its rendering.
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for extra in (ROOT, ROOT / 'tools'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import reference_lines as rl   # noqa: E402


def a_curve(start, end, bend=0.0, steps=20):
    """A run as the tracer gives one: (row, column) pairs along a path."""
    out = []
    for i in range(steps):
        t = i / float(steps - 1)
        y = start[0] + (end[0] - start[0]) * t
        x = start[1] + (end[1] - start[1]) * t + bend * t * (1.0 - t)
        out.append((y, x))
    return out


def test_two_pieces_of_a_bent_stroke_become_one_path():
    """A stroke that bends is cut in two; the halves' inward directions still oppose, so they join."""
    left = a_curve((100.0, 100.0), (100.0, 200.0), bend=14.0)
    right = a_curve((100.0, 200.5), (100.0, 300.0), bend=-14.0)
    joined = rl._join_runs([left, right], gap=2.0, straight=0.6)
    assert len(joined) == 1, 'a stroke cut in two came back as %d paths' % len(joined)
    assert len(joined[0]) == len(left) + len(right), 'points were lost or duplicated at the join'


def test_two_strokes_that_merely_meet_are_not_joined():
    """Two parallel strokes with facing ends are 12 pixels apart: further than a line's own width, so no join."""
    first = a_curve((100.0, 100.0), (100.0, 200.0))
    second = a_curve((100.0, 200.0), (100.0, 300.0))
    second = [(y + 12.0, x) for y, x in second]
    joined = rl._join_runs([first, second], gap=2.0, straight=0.6)
    assert len(joined) == 2, 'two separate strokes were joined into %d' % len(joined)


def test_a_crossing_pairs_each_stroke_with_its_own_continuation():
    """Four runs meeting at a point: the pairing is decided by which continuation is straightest, not by distance.

    This is the case a grid-binning stitch got wrong -- it joined whatever ends landed in the same cell and turned 5 310
    marks into 6 138. Each of the four runs here arrives at the crossing from a different direction, so the correct
    answer is two paths through it, not one path and two stubs.
    """
    centre = (100.0, 200.0)
    arms = [a_curve(centre, (100.0, 100.0)),                 # from the crossing, west
            a_curve(centre, (100.0, 300.0)),                 # east
            a_curve(centre, (0.0, 200.0)),                   # north
            a_curve(centre, (200.0, 200.0))]                 # south
    joined = rl._join_runs(arms, gap=2.0, straight=0.6)
    # Either two long paths or the four arms left alone is defensible; one path swallowing three arms is not, because
    # the fourth arm would then be drawn as a stroke that it is not a piece of.
    assert len(joined) == 2, 'a crossing produced %d paths' % len(joined)
    lengths = sorted(len(path) for path in joined)
    assert lengths == [40, 40], 'the crossing was paired unevenly: %r' % (lengths,)
