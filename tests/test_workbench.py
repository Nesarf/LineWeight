"""The loop a caller forgets: draw, check, revise, check again.

The two layers under this one are read-only -- `aesthetic` answers what the library knows, `standards` answers whether
a stroke is right -- and neither remembers which stroke you just drew. That is the whole reason `workbench` exists, and
it is why `failures()` is a method rather than something a caller assembles: **"I changed it" and "I fixed it" are
different claims**, and only the second one survives being checked again.

Nothing here is new work. `stroke` is `stroke_record` plus `add_stroke`, `check` is `standards.line`, `revise` is
`revise_mark`. These tests are about the wiring: that the loop closes, that a change is visible to the next check, and
that the session is a project with a memory rather than a new format.
"""
from __future__ import annotations

import pytest

from lineweight import Region, workbench


def a_region():
    return Region(points=[(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)],
                  d='M 0 0 L 40 0 L 40 30 L 0 30 Z')


def a_flat_line(session):
    """One width from end to end, which is the failure the variation check names."""
    return session.stroke([(10.0, 10.0), (80.0, 10.0), (150.0, 10.0)], 'ink', layer='LINE',
                          width_profile=[5.0, 5.0], absolute_width=True)


def test_a_session_is_a_project_with_a_loop_over_it():
    session = workbench.Session(200, 150, title='t')
    assert session.project.width == 200
    assert session.check() == [], 'nothing drawn, nothing to check'


def test_a_flat_stroke_is_reported_and_a_varied_one_is_not():
    session = workbench.Session(200, 150)
    flat = a_flat_line(session)
    assert session.check(flat.id)[0].ok is False

    varied = session.stroke([(10.0, 60.0), (80.0, 60.0), (150.0, 60.0)], 'brush', layer='LINE',
                            width_profile=[2.0, 12.0], absolute_width=True)
    assert session.check(varied.id)[0].ok is True


def test_failures_names_the_strokes_that_did_not_pass():
    session = workbench.Session(200, 150)
    flat = a_flat_line(session)
    session.stroke([(10.0, 60.0), (80.0, 60.0), (150.0, 60.0)], 'brush', layer='LINE',
                   width_profile=[2.0, 12.0], absolute_width=True)
    broken = session.failures()
    assert len(broken) == 1
    assert broken[0].stage == 'line'


def test_the_loop_closes_revise_makes_the_next_check_pass():
    """The only claim worth making about this layer: a change is visible to the check that follows it."""
    session = workbench.Session(200, 150)
    flat = a_flat_line(session)
    assert session.failures(), 'the stroke starts out flat'

    session.revise(flat.id, width_profile=[1.0, 9.0])
    assert session.failures() == [], 'the revision did not reach the judgement'


def test_revise_accepts_the_same_prefixes_the_command_line_does():
    session = workbench.Session(200, 150)
    mark = a_flat_line(session)
    session.revise(mark.id, **{'appearance.colour': '#ff0000'})
    assert session.project.by_id(mark.id).appearance['colour'] == '#ff0000'
    session.revise(mark.id, role='silhouette')
    assert session.project.by_id(mark.id).geometry['role'] == 'silhouette'


def test_rewind_undoes_the_revision_and_the_check_says_so_again():
    session = workbench.Session(200, 150)
    flat = a_flat_line(session)
    session.revise(flat.id, width_profile=[1.0, 9.0])
    assert session.failures() == []

    session.rewind(1)
    assert session.failures(), 'after the rewind the stroke is flat again, and the check has to see it'


def test_marks_filter_by_layer_and_stage():
    session = workbench.Session(200, 150)
    session.stroke([(5.0, 5.0), (50.0, 5.0)], 'ink', layer='LINE')
    session.fill(a_region(), layer='COLOUR')
    assert len(session.marks()) == 2
    assert [mark.layer for mark in session.marks(layer='COLOUR')] == ['COLOUR']


def test_a_session_saves_and_loads_its_project(tmp_path):
    session = workbench.Session(200, 150, title='round trip')
    session.stroke([(5.0, 5.0), (50.0, 40.0)], 'ink', layer='LINE')
    session.fill(a_region(), layer='COLOUR')
    path = str(tmp_path / 'session.json')
    session.save(path)

    back = workbench.Session.load(path)
    assert back.project.title == 'round trip'
    assert [mark.layer for mark in back.marks()] == ['LINE', 'COLOUR']


def test_render_gives_a_layer_the_size_of_the_session():
    session = workbench.Session(120, 90)
    session.stroke([(10.0, 10.0), (100.0, 70.0)], 'ink', layer='LINE')
    layer = session.render()
    assert (layer.width, layer.height) == (120, 90)
    assert any(layer.data[3::4]), 'the stroke has to have covered something'


def test_as_record_carries_the_colour_out_of_appearance():
    """The field that lives on the other side of the mark's own split. A record without it would redraw the stroke in
    its role's ink instead of the ink the caller chose."""
    session = workbench.Session(200, 150)
    mark = session.stroke([(5.0, 5.0), (60.0, 5.0)], 'ink', colour='#123456')
    assert mark.appearance['colour'] == '#123456'
    assert mark.as_record()['colour'] == '#123456'
    assert mark.as_record()['brush'] == 'ink'
