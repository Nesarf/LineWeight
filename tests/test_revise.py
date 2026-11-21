"""Revising one stroke from the command line: the handle the model was missing.

`Project.revise_mark` has been tested since it was written -- identity refused, neighbours byte-identical, previous
values kept in the log. What was not tested is the way a person reaches it, and that is the layer this file covers:
`--marks` to find out what a stroke is called, `--revise` to change it by that name.

Two failures here are quiet, and both are worth a test rather than a paragraph. A geometry field that does not exist
must be refused instead of written, because an unknown field renders nothing and survives every round trip -- it would
be found by a picture that did not change. And a revision that fails partway through a list must leave the file alone,
because a half-applied edit cannot be told from a finished one by looking at the drawing.
"""
from __future__ import annotations

import json

import pytest

from lineweight import Project, Region, core, load_project, save_project, stroke_record


def a_project(tmp_path):
    """Three marks of two kinds, so the listing and the refusal can both be checked against something real."""
    project = Project(width=500, height=500, title='revise')
    project.add_stroke(stroke_record([(10.0, 10.0), (120.0, 60.0), (200.0, 30.0)], 'ink', seed=3),
                       stage='line', layer='LINE', note='the contour')
    project.add_stroke(stroke_record([(40.0, 90.0), (160.0, 130.0)], 'brush', seed=7),
                       stage='line', layer='DETAIL', note='a detail')
    region = Region(points=[(0.0, 200.0), (300.0, 200.0), (300.0, 400.0), (0.0, 400.0)],
                    d='M 0 200 L 300 200 L 300 400 L 0 400 Z')
    project.add_fill(region, stage='colour', colour='#3355AA')
    path = str(tmp_path / 'revise.json')
    save_project(project, path)
    return project, path


def snapshot(path):
    """Every mark's own bytes, keyed by id -- the only view that can prove a neighbour was not regenerated."""
    project = load_project(path)
    return {mark.id: json.dumps(mark.to_dict(), sort_keys=True) for mark in project.marks}


def test_marks_lists_every_mark_and_the_id_it_answers_to(tmp_path, capsys):
    project, path = a_project(tmp_path)
    assert core.main(['--marks', path]) == 0
    out = capsys.readouterr().out
    for mark in project.marks:
        assert mark.id in out, 'the listing left out %s' % mark.id
    assert '3 mark(s)' in out
    assert 'region' in out, 'a fill has to be visible here too, or it can never be revised'


def test_marks_filters_by_stage(tmp_path, capsys):
    project, path = a_project(tmp_path)
    assert core.main(['--marks', path, '--stage', 'colour']) == 0
    out = capsys.readouterr().out
    fills = [m.id for m in project.marks if m.stage == 'colour']
    strokes = [m.id for m in project.marks if m.stage == 'line']
    for mark_id in fills:
        assert mark_id in out
    for mark_id in strokes:
        assert mark_id not in out, '--stage is a filter; it let %s through' % mark_id


def test_marks_limit_stops_the_list_and_says_how_many_are_left(tmp_path, capsys):
    project, path = a_project(tmp_path)
    assert core.main(['--marks', path, '--limit', '2']) == 0
    out = capsys.readouterr().out
    assert '1 more' in out, 'a truncated list that does not say so reads as the whole project'


def test_revise_writes_the_colour_and_leaves_the_file_loadable(tmp_path, capsys):
    project, path = a_project(tmp_path)
    target = project.marks[0]
    assert core.main(['--revise', path, '--mark-id', target.id, '--ink', '#00FF00']) == 0
    reread = load_project(path)
    assert reread.by_id(target.id).appearance['colour'] == '#00FF00'
    assert len(reread.marks) == len(project.marks)


def test_revise_only_touches_the_named_mark(tmp_path, capsys):
    project, path = a_project(tmp_path)
    before = snapshot(path)
    target = project.marks[1]
    assert core.main(['--revise', path, '--mark-id', target.id, '--ink', '#112233']) == 0
    after = snapshot(path)
    moved = sorted(k for k in before if before[k] != after[k])
    assert moved == [target.id], 'revising %s also touched %s' % (target.id, moved)


def test_revise_can_set_a_geometry_field(tmp_path, capsys):
    project, path = a_project(tmp_path)
    target = project.marks[0]
    assert core.main(['--revise', path, '--mark-id', target.id, '--set', 'role=silhouette']) == 0
    assert load_project(path).by_id(target.id).geometry['role'] == 'silhouette'


def test_a_geometry_field_that_does_not_exist_is_refused_and_the_file_is_untouched(tmp_path, capsys):
    """The quiet failure: a misspelled field would sit in the mark looking like a decision and change no pixel."""
    project, path = a_project(tmp_path)
    before = open(path, 'rb').read()
    with pytest.raises(SystemExit) as err:
        core.main(['--revise', path, '--mark-id', project.marks[0].id, '--set', 'wobble=4'])
    assert 'wobble' in str(err.value)
    assert open(path, 'rb').read() == before, 'a refused field still reached the file'


def test_an_unknown_mark_id_is_refused_before_anything_is_written(tmp_path, capsys):
    project, path = a_project(tmp_path)
    before = open(path, 'rb').read()
    with pytest.raises(SystemExit) as err:
        core.main(['--revise', path, '--mark-id', project.marks[0].id + ',' + 'm9999',
                   '--ink', '#000000'])
    assert 'm9999' in str(err.value)
    assert '--marks' in str(err.value), 'a refusal that does not name the way to find the id is a dead end'
    assert open(path, 'rb').read() == before, 'the first id was revised before the second was checked'


def test_identity_is_refused_at_the_command_line_too(tmp_path):
    project, path = a_project(tmp_path)
    with pytest.raises(SystemExit) as err:
        core.main(['--revise', path, '--mark-id', project.marks[0].id, '--set', 'id=m9999'])
    assert 'id' in str(err.value)


def test_dry_prints_the_result_and_writes_nothing(tmp_path, capsys):
    project, path = a_project(tmp_path)
    before = open(path, 'rb').read()
    assert core.main(['--revise', path, '--mark-id', project.marks[0].id,
                      '--ink', '#00FF00', '--dry']) == 0
    out = capsys.readouterr().out
    assert '#00ff00' in out.lower(), 'a dry run that does not show the result is not a dry run'
    assert 'nothing written' in out
    assert open(path, 'rb').read() == before


def test_revise_with_nothing_to_change_says_so(tmp_path):
    project, path = a_project(tmp_path)
    with pytest.raises(SystemExit) as err:
        core.main(['--revise', path, '--mark-id', project.marks[0].id])
    assert 'nothing to change' in str(err.value)


def test_a_revision_can_be_undone_from_the_file_alone(tmp_path, capsys):
    """The log is the half of the format that makes a revision safe to attempt: `--log --rewind 1` puts it back."""
    project, path = a_project(tmp_path)
    target = project.marks[0]
    original = load_project(path).by_id(target.id).appearance.get('colour')
    assert core.main(['--revise', path, '--mark-id', target.id, '--ink', '#00FF00']) == 0
    assert load_project(path).by_id(target.id).appearance['colour'] == '#00FF00'
    assert core.main(['--log', path, '--rewind', '1']) == 0
    assert load_project(path).by_id(target.id).appearance.get('colour') == original


def test_the_filter_flag_and_the_setter_flag_are_not_the_same_flag(tmp_path, capsys):
    """`--stage` filters a listing and `--to-stage` moves a mark. One name for both is how two quantities end up
    sharing a parameter, which is the error this project has paid for more than once."""
    project, path = a_project(tmp_path)
    target = project.marks[0]
    assert core.main(['--revise', path, '--mark-id', target.id, '--to-stage', 'value']) == 0
    assert load_project(path).by_id(target.id).stage == 'value'
    assert core.main(['--marks', path, '--stage', 'value']) == 0
    out = capsys.readouterr().out
    assert target.id in out
    assert project.marks[1].id not in out
