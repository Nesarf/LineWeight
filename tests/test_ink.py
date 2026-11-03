"""Which pixels of a reference count as ink, on the three definitions the tracer can be given.

**The top hat was wrong in a way no measurement in the project could see.** It keeps a pixel when it is darker than a
size-9 grey closing of itself, so a stroke thinner than nine pixels is ink and a *band* wider than nine is a ring: the
closing fills the band over, its middle stops being ink, and a trace of it walks the ring rather than the band. The copy
then draws a hairline down the middle of a twenty-pixel hem, and every width and edge figure still agreed, because the
width it was handed was the thickness of the ring.

Two tests, one for each way the definitions differ. They are cheap and they are about the failure that survived four
rounds of measurement, so they are worth more than a comment would be.
"""

import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for extra in (ROOT, ROOT / 'tools'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import reference_lines as rl   # noqa: E402


def a_page(height=200, width=200):
    return np.full((height, width), 255.0)


def test_a_solid_band_is_a_ring_under_the_top_hat_and_solid_under_the_union():
    """A band twenty pixels high, against an element of nine: the middle is not ink for one definition and is for the
    other. This is the whole of the difference and it is a single pixel that shows it."""
    gray = a_page()
    gray[80:100, 40:160] = 30.0
    top = rl.ink_mask(gray, 'tophat')
    both = rl.ink_mask(gray, 'both')
    assert not top[90, 100], 'the top hat kept the middle of a twenty-pixel band as ink'
    assert both[90, 100], 'the union lost the middle of a band its field test should keep'
    # **And the paper stays paper**, so the field is not simply answering "yes" everywhere.
    assert not both[10, 10] and not top[10, 10]


def test_a_pale_line_survives_the_union_where_one_fixed_threshold_would_lose_it():
    """The second drawing's case: ink at grey 210, which is a line to the floor and nothing to a level of 200.

    This is why the default is the union rather than the level. A relative test costs nothing on a drawing it suits; one
    fixed number has to be right about every drawing at once.
    """
    gray = a_page()
    gray[100, 40:160] = 210.0
    top = rl.ink_mask(gray, 'tophat')
    both = rl.ink_mask(gray, 'both')
    level = rl.ink_mask(gray, 'level', level=200.0)
    assert top[100, 100], 'the top hat lost a line 45 grey levels below its paper'
    assert both[100, 100], 'the union lost what the top hat kept'
    assert not level[100, 100], 'a level of 200 kept ink at 210, so this test is not measuring what it says'


def test_the_field_alone_misses_what_the_top_hat_keeps():
    """Close hatching: inside it the median window is nearly all ink, so nothing is darker than its surroundings.

    Stated as a test because it is the reason the union exists rather than the field being the answer on its own -- the
    field found 236 890 line pixels on `150673997` against the top hat's 618 557 at a window of 15.
    """
    gray = a_page()
    # **Five-pixel strokes one pixel apart**, so more than half of a nine-pixel window is ink and the median lands on the
    # ink itself. That is what hatching does to a small window; a wider spacing is a suite of lines, not hatching.
    for x in range(40, 160, 6):
        gray[40:160, x:x + 5] = 60.0
    top = rl.ink_mask(gray, 'tophat')
    field = rl.ink_mask(gray, 'field', window=9)
    assert top[100, 40], 'the top hat lost a stroke inside hatching'
    assert not field[100, 40], 'the field kept a stroke whose whole window is ink, so it is not measuring what it says'
