"""Merging the fills project and the lines project into one drawing.

**Why the merge is not cosmetic.** The two passes wrote their own project files and the two met only at the moment of
compositing a PNG. `DESIGN-PROJECT.md` requires every line and every colour application to be an individually addressable
entry in the project file, so a drawing that exists as two files cannot be revised as one drawing -- "revise this line by
id" has no single file to look in.

**What these tests are for.** The merge is a place where a mistake is silent: a duplicate id makes "revise by id"
ambiguous with no error, and a canvas mismatch puts two sets of absolute coordinates on one page as if they belonged
together. Neither shows up in the picture.
"""

import pytest

from lineweight import project


def a_page(width=100, height=80):
    return {'canvas': {'width': width, 'height': height}}


def a_fill(identifier, seq=0):
    return {'id': identifier, 'kind': 'fill', 'seq': seq, 'geometry': {}, 'appearance': {}}


def a_stroke(identifier, seq=0):
    return {'id': identifier, 'kind': 'stroke', 'seq': seq, 'geometry': {}}


def fills_doc(*marks, **kwargs):
    doc = a_page(**kwargs)
    doc['movies'] = []
    doc['marks'] = list(marks)
    doc['stages'] = [{'role': 'colour'}]
    doc['title'] = 'fills'
    return doc


def lines_doc(*marks, **kwargs):
    doc = a_page(**kwargs)
    doc['marks'] = list(marks)
    doc['stages'] = [{'role': 'line'}]
    doc['title'] = 'lines'
    return doc


def test_fills_come_first_and_lines_after():
    """Order is the drawing order, so ink goes on top of paint and the merge must not sort."""
    merged = project.combine(fills_doc(a_fill('f1'), a_fill('f2')),
                                  lines_doc(a_stroke('s1')))
    assert [m['id'] for m in merged['marks']] == ['f1', 'f2', 's1']


def test_sequence_is_rewritten_to_the_merged_order():
    merged = project.combine(fills_doc(a_fill('f1', seq=0), a_fill('f2', seq=1)),
                                  lines_doc(a_stroke('s1', seq=0)))
    assert [m['seq'] for m in merged['marks']] == [0, 1, 2]
    assert merged['counter'] == 3


def test_a_page_that_does_not_match_is_refused():
    """A mark's coordinates are absolute, so two pages are only one drawing if they are the same page."""
    with pytest.raises(ValueError):
        project.combine(fills_doc(a_fill('f1')), lines_doc(a_stroke('s1'), width=120))


def test_a_duplicate_id_is_refused():
    with pytest.raises(ValueError):
        project.combine(fills_doc(a_fill('same')), lines_doc(a_stroke('same')))


def test_a_mark_without_an_id_is_refused():
    with pytest.raises(ValueError):
        project.combine(fills_doc(a_fill('')), lines_doc(a_stroke('s1')))


def test_the_stage_list_is_the_union():
    merged = project.combine(fills_doc(a_fill('f1')), lines_doc(a_stroke('s1')))
    assert merged['stages'] == [{'role': 'colour'}, {'role': 'line'}]


def test_the_merge_does_not_mutate_its_inputs():
    """The second pass reads the same areas the first one wrote, so a merge that edited them would break a rerun."""
    fills = fills_doc(a_fill('f1', seq=5))
    lines = lines_doc(a_stroke('s1', seq=7))
    project.combine(fills, lines)
    assert fills['marks'][0]['seq'] == 5
    assert lines['marks'][0]['seq'] == 7
