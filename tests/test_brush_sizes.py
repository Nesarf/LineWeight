"""A brush is a kind of line, and a size is how heavy it was laid down.

**The gap these tests exist for.** The brush table gave exactly one width per brush -- four brushes, four line weights
for a whole drawing -- and the pressure model cannot supply the rest, because it works in ratios around that width: a
stroke's `p / median` moves the line by tens of per cent, never by five times. So the size is a separate axis.

**Why scaling `width` alone is the whole of it.** Every other length in a brush is quoted as a multiple of its own
width, which is the unit the table was designed around: a nib's entry is `width * 14.3` in total so it takes the same
distance on a long stroke as on a short one, and the tremor is a fraction of the width. Raising the width raises all of
them, which is what "the same brush, bigger" means.
"""

import statistics

import numpy as np
import pytest

from lineweight import core, raster


A_PATH = [(0, 0), (30, 2), (60, 14), (95, 6), (130, 20), (170, 4), (210, 16)]


def widths_at(name, size, seed=7):
    record = core.stroke_record(A_PATH, name, seed=seed, size=size)
    return core.stroke_widths(record)


def test_a_size_scales_the_width_and_leaves_the_rest_alone():
    plain = core.brush_at('ink', 1.0)
    bigger = core.brush_at('ink', 2.5)
    assert bigger['width'] == pytest.approx(plain['width'] * 2.5)
    for field in ('taper_in', 'taper_out', 'spacing', 'speed', 'corner', 'noise', 'wobble', 'curve'):
        assert bigger[field] == plain[field], field


def test_the_taper_grows_with_the_line():
    """The taper is a distance the nib travels, quoted in width multiples, so it must scale with the size."""
    plain = core.brush_at('fine', 1.0)
    bigger = core.brush_at('fine', 2.0)
    assert bigger['taper_in'] * bigger['width'] == pytest.approx(
        2.0 * plain['taper_in'] * plain['width'])


def test_the_same_stroke_at_two_sizes_is_that_much_wider():
    """**Not exactly the ratio, and the reason is the taper.** A taper is a fixed distance, so on the same path a bigger
    brush spends a larger share of its length building pressure and the profile is not a uniform multiplication. Measured
    on a fine brush: 1.42 at size one and 3.88 at size three, a ratio of 2.73. The claim worth pinning is the range."""
    small = statistics.median(widths_at('fine', 1.0))
    large = statistics.median(widths_at('fine', 3.0))
    assert large / small > 2.0
    assert large / small < 4.0


def test_every_brush_can_be_laid_down_at_every_size():
    for name in core.BRUSHES:
        widths = [core.brush_at(name, size)['width'] for size in core.SIZES]
        assert widths == sorted(widths), name
        assert widths[-1] / widths[0] == pytest.approx(core.SIZES[-1] / core.SIZES[0])


def test_a_record_carries_its_size():
    record = core.stroke_record(A_PATH, 'fine', seed=1, size=2.0)
    assert record['size'] == pytest.approx(2.0)
    assert core.stroke_widths(record) == core.stroke_widths(
        core.stroke_record(A_PATH, 'fine', seed=1, size=2.0))


def test_a_record_written_before_sizes_existed_expands_as_it_did():
    """An absent size is one, not an error -- the same rule every other optional field in a record follows."""
    record = core.stroke_record(A_PATH, 'fine', seed=3)
    record.pop('size')
    assert core.stroke_widths(record) == core.stroke_widths(
        core.stroke_record(A_PATH, 'fine', seed=3, size=1.0))


def test_a_smaller_size_keeps_its_variation():
    """**強弱 is a property of the brush, not of the size.** A thin line must still breathe; the taper's share of the
    stroke grows as the brush shrinks, and that is why the variation reads slightly higher rather than lower."""
    for size in (0.5, 1.0, 2.0, 3.0):
        record = core.stroke_record(A_PATH, 'fine', seed=7, size=size)
        assert core.stroke_variation(record) < core.UNIFORM_FLOOR, size


def test_a_brush_is_read_against_the_page_its_table_was_drawn_on():
    """**The table's widths were fixed on one page and never said which.**

    `BRUSH_REFERENCE_LONG` names it: 800 long, inferred from the canvas the drawing tools of that period work on and
    confirmed by what the widths come to there -- `fine` covers 0.2331 per cent of the page, against an artist's median
    of 0.2219, where the same number on a 2880 page covers 0.0648 and falls below the lowest of eleven. So the width
    follows the page the record names, and the record is the only thing allowed to say: **not the canvas**, because a
    thumbnail fills a canvas smaller than the drawing, and six tests broke when the renderer started believing its own
    size instead of the record's."""
    for name in ('fine', 'ink', 'wash'):
        small = sum(core.stroke_widths(core.stroke_record(A_PATH, name, seed=3, page_long=1440)))
        large = sum(core.stroke_widths(core.stroke_record(A_PATH, name, seed=3, page_long=2880)))
        assert small / 1440 == pytest.approx(large / 2880, rel=0.01), name


def test_the_share_a_brush_covers_is_the_same_on_two_page_sizes():
    """The same rule, read off the picture rather than off the table: the alpha a column carries, over the page's own
    length. This is the number the eye sees, so it is the one that has to hold."""
    def share(name, page_long):
        mid = 240.0
        record = core.stroke_record([(page_long * 0.2, mid), (page_long * 0.8, mid)], name,
                                    seed=5, page_long=page_long)
        layer = raster.sweep_layer(record, page_long, 480, scale=1.0)
        alpha = np.frombuffer(layer.data, dtype=np.uint8).reshape(480, page_long, 4)[:, :, 3]
        columns = np.arange(page_long)
        middle = (columns > page_long * 0.3) & (columns < page_long * 0.7)
        return float(np.median(alpha[:, middle].sum(axis=0) / 255.0)) / page_long

    for name in ('ink', 'maru'):
        assert share(name, 1440) == pytest.approx(share(name, 2880), rel=0.03), name
