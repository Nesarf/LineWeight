"""A fill must look the same wherever the renderer chooses to put its buffer.

**This is the acceptance test for a change that is invisible when it works.** Fills used to be rasterised into a
page-sized buffer and composited over the whole canvas; on a large reference that made twenty-seven thousand areas spend
more than fifty minutes in the composer, so each fill is now rasterised into its own bounding box and composited at that
offset. The arithmetic is meant to be identical, and "meant to be" is exactly what a test is for: a shifted gradient, a
hole left in page coordinates, or a one-pixel offset at an edge would each produce a picture that still looks like a
drawing and is not the drawing the project file describes.

The reference implementation here is the old path, written out by hand: fill on the page, blend over the whole canvas.
"""

from lineweight import raster


def a_fill(points, fill='#3a7bd5', holes=None, gradient=None):
    mark = {
        'id': 'f',
        'kind': 'fill',
        'state': 'live',
        'geometry': {'points': points},
        'appearance': {'fill': fill, 'opacity': 1.0, 'blend': 'normal'},
    }
    if holes:
        mark['geometry']['holes'] = holes
    if gradient:
        mark['geometry']['gradient'] = gradient
    return mark


def on_the_page(marks, width, height, scale=1.0):
    """The old path: every fill into a page-sized buffer, then blended over the whole canvas."""
    out = raster.Layer(width, height)
    for mark in marks:
        out = raster.blend(out, raster.fill_layer(mark, width, height, scale), 'normal', 1.0)
    return out


def in_its_own_box(marks, width, height, scale=1.0):
    return raster.render_marks(marks, width, height, scale)


def compare(marks, width, height, scale=1.0):
    slow = on_the_page(marks, width, height, scale)
    fast = in_its_own_box(marks, width, height, scale)
    assert len(fast.data) == len(slow.data)
    differing = [i for i in range(len(slow.data)) if slow.data[i] != fast.data[i]]
    assert not differing, '%d bytes differ, first at %d' % (len(differing), differing[0] if differing else -1)
    return fast


def test_a_plain_shape_is_identical():
    marks = [a_fill([(20, 20), (80, 25), (55, 75), (25, 60)])]
    drawn = compare(marks, 100, 90)
    assert any(pixel for pixel in drawn.data[3::4]), 'the shape did not reach the page at all'


def test_a_shape_touching_the_page_edge_is_identical():
    """A box clipped by the canvas is where an offset would show up first."""
    marks = [a_fill([(-10, -5), (40, 10), (35, 60), (-8, 45)])]
    compare(marks, 70, 70)


def test_a_shape_with_a_hole_is_identical():
    """**A hole is stated in page coordinates and the outer ring is not where it was.** A hole left behind is invisible
    under `nonzero` -- the ring would simply fill solid -- so this case only shows up in a comparison, not in a picture.
    """
    marks = [a_fill([(10, 10), (90, 10), (90, 80), (10, 80)],
                    holes=[[(35, 30), (65, 30), (65, 60), (35, 60)]])]
    compare(marks, 100, 90)


def test_a_gradient_starts_where_it_says():
    """The gradient's endpoints are page coordinates, so they move with the shape's offset."""
    marks = [a_fill([(30, 20), (90, 20), (90, 70), (30, 70)],
                    gradient={'from': [30, 20], 'to': [90, 70], 'colour0': '#ffffff', 'colour1': '#101010'})]
    compare(marks, 120, 90)


def test_several_shapes_and_an_overlap_are_identical():
    """Order still decides the picture, so a later shape over an earlier one must land the same way in both paths."""
    marks = [
        a_fill([(10, 10), (70, 15), (60, 70)], fill='#c04030'),
        a_fill([(40, 30), (95, 35), (85, 80)], fill='#30a060'),
        a_fill([(20, 50), (60, 45), (55, 85)], fill='#3050c0'),
    ]
    compare(marks, 100, 95)


def test_one_mark_renders_the_same_twice():
    """Determinism, because a difference between two runs and a difference between two paths look the same."""
    marks = [a_fill([(12, 9), (77, 21), (66, 66)])]
    first = in_its_own_box(marks, 90, 80)
    second = in_its_own_box(marks, 90, 80)
    assert first.data == second.data
