"""The project file: marks stay individually addressable.

The reason this module exists is stated in `DESIGN-PROJECT.md` and is worth restating as the reason these tests are
shaped the way they are: lineweight's first-hand output is a drawing *project*, not an image, and the whole point of
that is that a single stroke or a single patch of colour can be revised, added or deleted **without regenerating
anything else**. So the tests below mostly assert identity and isolation --

    * a mark can be found by id;
    * changing or dropping one leaves the rest byte-identical;
    * order survives a round trip, because order is the picture;
    * the two passes are separable, because acceptance is per-pass.

A test that only checked "a file was written and read back" would pass on a format that had merged everything.
"""
from __future__ import annotations

import json

import pytest

from lineweight import (DEFAULT_STAGES, DRAFT, LIVE, SUPERSEDED, Mark, Project, Region, load_project,
                        region_fill, roles, save_project, stroke_record)
from lineweight.core import mark_ink


def quads():
    """Four near-closed squares, so `region_fill` has something to find."""
    out = []
    for i in range(4):
        x = 100.0 * i
        out.append([(x, 0.0), (x + 100.0, 0.0)])
        out.append([(x + 102.0, 2.0), (x + 102.0, 100.0)])
        out.append([(x + 100.0, 102.0), (x, 102.0)])
        out.append([(x - 2.0, 100.0), (x - 2.0, 2.0)])
    return out


def a_project_with_marks() -> Project:
    project = Project(width=500, height=500, title='quads')
    record = stroke_record([(0.0, 0.0), (50.0, 40.0), (120.0, 10.0)], 'ink', seed=3)
    project.add_stroke(record, stage='line', note='the first line')
    regions = region_fill(quads(), 3.0)
    for i, region in enumerate(regions):
        project.add_fill(region, stage='colour', colour='#%02X8080' % (40 * i), note='patch %d' % i)
    return project


def test_a_fill_is_a_mark_with_an_identity_not_a_string():
    """**The change this whole module was built for.** `region_fill` used to return bare `d` strings: paintable and
    nothing else. A caller could not say "remove the third patch", only "paint these". A fill mark carries the polygon
    it came from as well as the path data, so it can be pointed at."""
    regions = region_fill(quads(), 3.0)
    assert regions and isinstance(regions[0], Region)
    # both representations, and they must describe the same shape
    assert regions[0].points
    assert regions[0].d.startswith('M ') and regions[0].d.endswith(' Z')

    project = a_project_with_marks()
    fills = [m for m in project.marks if m.kind == 'fill']
    assert len(fills) == len(regions)
    for mark, region in zip(fills, regions):
        assert mark.geometry['points'] == [list(p) for p in region.points]
        assert mark.geometry['d'] == region.d
        assert mark.id and mark.state == LIVE


def test_deleting_one_fill_leaves_every_other_mark_untouched():
    """The property that a merged layer cannot have. Compare every other mark before and after: if any of them moved,
    changed or vanished, the project is not made of independent marks and the edit was not a local one."""
    project = a_project_with_marks()
    victim = [m for m in project.marks if m.kind == 'fill'][2]
    before = {m.id: json.dumps(m.to_dict(), sort_keys=True) for m in project.marks if m.id != victim.id}

    project.marks.remove(victim)

    after = {m.id: json.dumps(m.to_dict(), sort_keys=True) for m in project.marks}
    assert victim.id not in after
    assert before == after, 'removing one mark disturbed another'
    # and the survivors are still addressable afterwards
    assert [m.id for m in project.marks] == list(before)


def test_by_id_finds_exactly_one_mark_and_reports_a_missing_one():
    project = a_project_with_marks()
    wanted = project.marks[3]
    assert project.by_id(wanted.id) is wanted
    with pytest.raises(KeyError):
        project.by_id('m9999')


def test_order_is_the_picture_so_it_survives_a_round_trip(tmp_path):
    """Later marks cover earlier ones, so the sequence is not bookkeeping -- it is the drawing. A save that reordered
    marks would still look fine as JSON and render wrong."""
    project = a_project_with_marks()
    path = str(tmp_path / 'p.json')
    save_project(project, path)
    back = load_project(path)

    assert [m.id for m in back.marks] == [m.id for m in project.marks]
    assert [m.seq for m in back.marks] == [m.seq for m in project.marks]
    assert [m.seq for m in back.marks] == list(range(len(back.marks))), 'seq must be the drawing order, not a label'
    assert [m.stage for m in back.marks] == [m.stage for m in project.marks]
    assert back.width == 500 and back.height == 500 and back.title == 'quads'


def test_a_stroke_mark_keeps_its_geometry_apart_from_its_appearance(tmp_path):
    """Restyling without redrawing is what the split is for, and it is the same split `stroke_record` already had."""
    project = a_project_with_marks()
    path = str(tmp_path / 'p.json')
    save_project(project, path)
    back = load_project(path)

    stroke = [m for m in back.marks if m.kind == 'stroke'][0]
    original = json.dumps(stroke.geometry, sort_keys=True)
    stroke.appearance['colour'] = '#FF0000'
    assert json.dumps(stroke.geometry, sort_keys=True) == original, 'restyling moved the geometry'
    # and the fields a record needs to be redrawn are all there
    for key in ('centre', 'control', 'pressure', 'brush', 'seed', 'resolution'):
        assert key in stroke.geometry, key
    assert len(stroke.geometry['pressure']) == len(stroke.geometry['centre'])


def test_stages_partition_the_marks_and_can_be_rendered_one_at_a_time():
    """Acceptance is per pass, so a pass has to be extractable. `in_stage` is one pass; `upto` is the drawing as it
    stood at the end of that pass."""
    project = a_project_with_marks()
    assert project.stage_names() == [s['role'] for s in DEFAULT_STAGES]

    line = project.in_stage('line')
    colour = project.in_stage('colour')
    assert len(line) == 1 and len(colour) == 4
    assert not set(m.id for m in line) & set(m.id for m in colour), 'a mark is in two passes'

    assert [m.id for m in project.upto('line')] == [m.id for m in line]
    assert len(project.upto('colour')) == 5
    assert len(project.upto('refine')) == len(project.marks)


def test_an_unknown_stage_is_refused_rather_than_silently_accepted():
    """A typo in a stage name must not create a fifth pass that renders nowhere and is never checked."""
    project = Project()
    record = stroke_record([(0.0, 0.0), (10.0, 10.0)], 'fine')
    with pytest.raises(ValueError) as err:
        project.add_stroke(record, stage='lineart')
    assert 'lineart' in str(err.value)
    assert not project.marks, 'a refused mark was added anyway'


def test_loaded_ids_are_never_reused():
    """After a load, the next mark must not collide with an existing id. Reusing one would silently make two marks
    indistinguishable, which is the failure mode this format exists to prevent."""
    project = a_project_with_marks()
    taken = {m.id for m in project.marks}
    record = stroke_record([(0.0, 0.0), (10.0, 10.0)], 'fine')
    fresh = project.add_stroke(record, stage='refine')
    assert fresh.id not in taken
    assert len({m.id for m in project.marks}) == len(project.marks), 'ids are not unique'


def test_a_version_1_file_is_rejected_rather_than_misread():
    """`save_strokes` wrote `{"version": 1, "strokes": [...]}`. v2 has marks with ids, stages and states, and reading
    a v1 file as v2 would produce a project whose marks have no identity."""
    with pytest.raises(ValueError) as err:
        Project.from_dict({'version': 1, 'strokes': []})
    assert 'version' in str(err.value).lower()


# --- revising a mark: the hard rule, made structural -------------------------------------------------------------

def ops_since(project, baseline: int) -> list[str]:
    """The operations logged after `baseline`, so a test can talk about what it did rather than what the fixture did.

    This became necessary when additions started being logged: a fixture that builds five marks now logs five `add`
    entries, and a test asserting an exact log was really asserting the fixture's construction order.
    """
    return [e['op'] for e in project.log[baseline:]]


def snapshot(project) -> dict:
    """Every mark's serialised bytes, keyed by id. The unit of comparison for "nothing else moved"."""
    return {m.id: json.dumps(m.to_dict(), sort_keys=True) for m in project.marks}


def test_revising_one_mark_changes_nothing_else():
    """**The rule the whole format exists for, tested the only way that can catch a rebuild.** A rebuild that happened
    to produce the same picture would look identical from the outside, so this compares every other mark's bytes
    before and after. Anything that regenerates its neighbours fails here even if the drawing comes out the same."""
    project = a_project_with_marks()
    before = snapshot(project)
    target = [m for m in project.marks if m.kind == 'fill'][1]

    project.revise_mark(target.id, appearance={'fill': '#123456'})

    after = snapshot(project)
    moved = [k for k in before if before[k] != after[k]]
    assert moved == [target.id], 'revising %s also touched %s' % (target.id, moved)
    assert project.by_id(target.id).appearance['fill'] == '#123456'


def test_a_mark_s_identity_is_not_revisable():
    """`id`, `kind` and `seq` are refused loudly rather than ignored. Renaming is a different operation; turning a
    stroke into a fill leaves the id pointing at something nobody asked for; and moving a mark in the drawing order
    would change what covers what. Accepting any of them quietly is the failure mode -- the caller would get a mark
    whose identity no longer means what it did."""
    project = a_project_with_marks()
    mark = project.marks[0]
    for field, value in (('id', 'm9999'), ('kind', 'fill'), ('seq', 99)):
        with pytest.raises(ValueError) as err:
            project.revise_mark(mark.id, appearance={field: value})
        assert field in str(err.value)
        with pytest.raises(ValueError):
            project.revise_mark(mark.id, geometry={field: value})
    assert mark.id == 'm0001' and mark.kind == 'stroke' and mark.seq == 0


def test_a_field_that_is_not_mentioned_is_not_touched():
    """Changing a colour must not require restating the geometry. A merge-style update would make every revision a
    full rewrite by accident, and the caller would have no way to ask for a partial one."""
    project = a_project_with_marks()
    mark = project.marks[0]
    geometry = json.dumps(mark.geometry, sort_keys=True)
    project.revise_mark(mark.id, appearance={'colour': '#00FF00'})
    assert json.dumps(mark.geometry, sort_keys=True) == geometry
    assert mark.appearance['colour'] == '#00FF00'


def test_revising_an_unknown_id_is_an_error_not_a_silent_no_op():
    project = a_project_with_marks()
    with pytest.raises(KeyError):
        project.revise_mark('m9999', appearance={'colour': '#000000'})


def test_superseding_takes_a_mark_out_of_the_drawing_without_destroying_it():
    """Erasing is ordinary practice -- the analysed recording drew five times the line it kept -- so a mark that was
    painted over stops rendering but keeps its geometry, and the ordered accessors stop returning it."""
    from lineweight.raster import render_marks

    project = a_project_with_marks()
    victim = [m for m in project.marks if m.kind == 'fill'][0]

    # measure what it covers while it is still live -- afterwards `render_marks` will correctly skip it, so a
    # check of "it would have rendered" has to be taken before the supersede, not after
    before_layer = render_marks([victim.to_dict()], 500, 500, 0.5)
    before_px = sum(1 for i in range(0, before_layer.width * before_layer.height * 4, 4)
                    if before_layer.data[i + 3] > 0)
    assert before_px > 0, 'the victim covers nothing, so this test would prove nothing'

    geometry = json.dumps(victim.geometry, sort_keys=True)
    others = {k: v for k, v in snapshot(project).items() if k != victim.id}

    project.supersede(victim.id, reason='the contour moved')

    assert victim.id not in [m.id for m in project.live()]
    assert victim.id not in [m.id for m in project.upto('colour')]
    assert victim.id in [m.id for m in project.marks], 'the mark must still be in the file'
    assert json.dumps(victim.geometry, sort_keys=True) == geometry, 'superseding must not alter the geometry'
    assert {k: v for k, v in snapshot(project).items() if k != victim.id} == others

    # and it now renders to nothing, which is the point
    after_layer = render_marks([victim.to_dict()], 500, 500, 0.5)
    after_px = sum(1 for i in range(0, after_layer.width * after_layer.height * 4, 4)
                   if after_layer.data[i + 3] > 0)
    assert after_px == 0, 'a superseded mark must not render'


def test_restoring_puts_a_mark_back_where_it_was_not_at_the_end():
    """`seq` is never touched by supersede, so restore is exact. Appending to the end instead would silently change
    what covers what -- a restored mark would jump to the front of the drawing."""
    project = a_project_with_marks()
    order = [m.id for m in project.live()]
    middle = order[len(order) // 2]

    project.supersede(middle)
    assert [m.id for m in project.live()] == [i for i in order if i != middle]
    project.restore(middle)
    assert [m.id for m in project.live()] == order, 'the restored mark did not return to its place'


def test_superseding_twice_is_one_entry_in_the_log():
    """Idempotence matters because the operation arrives from a conversation: "remove that one" said twice must not
    leave two entries, or the log stops being a record of what happened."""
    project = a_project_with_marks()
    mark = project.marks[0]
    project.supersede(mark.id)
    depth = len(project.log)
    project.supersede(mark.id)
    assert len(project.log) == depth
    # and restoring a live mark is likewise a no-op
    project.restore(project.marks[1].id)
    assert len(project.log) == depth


def test_removing_outright_is_a_different_operation_from_superseding():
    """The caller has to mean it: this is the one operation that cannot be undone from the file, so it is not the
    default, and the log keeps what was removed even though the mark itself is gone."""
    project = a_project_with_marks()
    removed = project.marks[0]
    geometry = json.dumps(removed.geometry, sort_keys=True)
    project.remove_mark(removed.id)

    assert removed.id not in [m.id for m in project.marks]
    with pytest.raises(KeyError):
        project.by_id(removed.id)
    entry = [e for e in project.log if e['op'] == 'remove'][-1]
    assert entry['ids'] == [removed.id]
    assert json.dumps(entry['mark']['geometry'], sort_keys=True) == geometry, 'the log should say what was lost'


def test_every_revision_is_recorded_in_order():
    """The log is what makes "the last thing you changed was wrong" answerable, which the stated use of this software
    -- describing, then correcting, repeatedly -- depends on."""
    project = a_project_with_marks()
    base = len(project.log)
    a, b = project.marks[0], project.marks[1]
    project.revise_mark(a.id, appearance={'colour': '#111111'})
    project.supersede(b.id)
    project.restore(b.id)
    project.revise_mark(a.id, note='second pass')
    project.remove_mark(b.id)

    assert ops_since(project, base) == ['revise', 'supersede', 'restore', 'revise', 'remove']
    assert [e['at'] for e in project.log] == list(range(len(project.log))), 'the log must keep its own order'
    assert project.log[base]['ids'] == [a.id] and 'appearance' in project.log[base]['changed']


def test_the_log_survives_a_round_trip(tmp_path):
    project = a_project_with_marks()
    project.revise_mark(project.marks[0].id, appearance={'colour': '#222222'})
    project.supersede(project.marks[-1].id, reason='off the edge')
    path = str(tmp_path / 'p.json')
    save_project(project, path)
    back = load_project(path)
    assert back.log == project.log
    assert [m.state for m in back.marks] == [m.state for m in project.marks]


def test_seq_is_what_orders_a_render_not_the_list_position():
    """`seq` is the drawing order and it is authoritative; a mark's position in the list is incidental. Anything that
    reordered the list -- a sort by colour, a merge from two sources -- would otherwise change the picture, and the
    failure would look like a plausible drawing rather than like a bug."""
    project = a_project_with_marks()
    ordered = [m.id for m in project.live()]
    project.marks.reverse()
    assert [m.id for m in project.live()] == ordered, 'the accessors must sort by seq, not by list position'
    assert [m.id for m in project.upto('colour')] == ordered
    assert [m.id for m in project.in_stage('colour')] == \
           [i for i in ordered if project.by_id(i).kind == 'fill']


def test_saved_files_are_utf8_and_end_with_a_newline(tmp_path):
    """The file is meant to be read and diffed by a person, so it is indented, UTF-8, and ends with a newline."""
    project = Project(title='日本語のタイトル')
    record = stroke_record([(0.0, 0.0), (10.0, 10.0)], 'fine')
    project.add_stroke(record, stage='line', note='顔の輪郭')
    path = tmp_path / 'p.json'
    save_project(project, str(path))

    raw = path.read_bytes()
    assert raw.endswith(b'\n')
    assert '日本語のタイトル'.encode('utf-8') in raw
    assert b'\\u' not in raw, 'the file escaped its non-ASCII instead of writing it'


# --- rendering a project: what makes a pass checkable ------------------------------------------------------------

def covered(layer) -> int:
    return sum(1 for i in range(0, layer.width * layer.height * 4, 4) if layer.data[i + 3] > 0)


def test_filling_a_polygon_covers_the_area_it_says_and_no_more():
    """An area check, because a fill that leaks or that stops short is still a plausible-looking patch of colour.
    Three shapes whose areas are known exactly by hand."""
    from lineweight.raster import Layer, fill_polygon

    square = Layer(60, 60)
    fill_polygon(square, [(10.0, 10.0), (50.0, 10.0), (50.0, 50.0), (10.0, 50.0)], (200, 60, 60), 1.0)
    assert covered(square) == 1600, '40x40 is 1600 pixels'

    triangle = Layer(60, 60)
    fill_polygon(triangle, [(5.0, 5.0), (55.0, 5.0), (30.0, 55.0)], (20, 20, 20), 1.0)
    assert 1200 <= covered(triangle) <= 1300, 'a 50x50 triangle is about 1250'

    # a closed loop as `weld_endpoints` actually returns it: first point repeated at the end
    loop = Layer(80, 40)
    fill_polygon(loop, [(5.0, 5.0), (35.0, 5.0), (35.0, 35.0), (5.0, 35.0), (5.0, 5.0)], (10, 10, 10), 1.0)
    assert covered(loop) == 900, 'the repeated closing point must not double the edge'


def test_rendering_respects_drawing_order_because_order_is_the_picture():
    """A renderer that grouped by kind, or sorted by stage, would produce a perfectly plausible image of something that
    was never drawn. Two fills over the same square: whichever is later must win."""
    from lineweight.raster import Layer, fill_polygon, render_marks

    square = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)]
    def mark(mid, colour, seq):
        return {'id': mid, 'kind': 'fill', 'stage': 'colour', 'seq': seq, 'state': 'live',
                'geometry': {'points': square, 'd': 'M 0 0 L 40 0 L 40 40 L 0 40 Z'},
                'appearance': {'fill': colour, 'opacity': 1.0, 'blend': 'normal'},
                'provenance': {}}

    red, blue = mark('m0001', '#FF0000', 0), mark('m0002', '#0000FF', 1)
    for order, expected, why in ((('m0001', 'm0002'), (0, 0, 255), 'blue was drawn last'),
                                 (('m0002', 'm0001'), (255, 0, 0), 'red was drawn last')):
        marks = [red, blue] if order == ('m0001', 'm0002') else [blue, red]
        out = render_marks(marks, 40, 40, 1.0)
        index = ((20 * 40) + 20) * 4
        got = tuple(out.data[index:index + 3])
        assert got == expected, '%s, but got %s' % (why, got)


def test_a_superseded_mark_is_not_rendered():
    """Erasing is a normal part of drawing -- the analysed video drew five times the line it kept -- so a mark that was
    painted over must not reappear the next time the project is rendered."""
    from lineweight.raster import render_marks

    square = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)]
    mark = {'id': 'm0001', 'kind': 'fill', 'stage': 'colour', 'seq': 0, 'state': SUPERSEDED,
            'geometry': {'points': square, 'd': 'M 0 0 L 40 0 L 40 40 L 0 40 Z'},
            'appearance': {'fill': '#FF0000', 'opacity': 1.0}, 'provenance': {}}
    assert covered(render_marks([mark], 40, 40, 1.0)) == 0
    mark['state'] = LIVE
    assert covered(render_marks([mark], 40, 40, 1.0)) == 1600


def test_an_unrenderable_kind_is_refused_rather_than_skipped():
    """Silently skipping a mark the renderer does not understand would produce a drawing quietly missing something."""
    from lineweight.raster import render_marks

    with pytest.raises(ValueError) as err:
        render_marks([{'id': 'm0001', 'kind': 'gradient', 'stage': 'colour', 'seq': 0, 'state': LIVE,
                       'geometry': {}, 'appearance': {}}], 20, 20, 1.0)
    assert 'gradient' in str(err.value)


def test_each_pass_renders_to_a_different_picture():
    """The point of staging: acceptance is per pass, so the passes have to come out separately. If two stages rendered
    identically, one of them is not doing anything."""
    from lineweight.raster import render_marks

    project = a_project_with_marks()
    shots = {}
    for stage in ('line', 'colour'):
        shots[stage] = render_marks([m.to_dict() for m in project.in_stage(stage)], 500, 500, 0.5)
    assert covered(shots['line']) > 0 and covered(shots['colour']) > 0
    assert covered(shots['line']) != covered(shots['colour'])

    # and `upto` is a superset: it must contain both
    everything = render_marks([m.to_dict() for m in project.upto('colour')], 500, 500, 0.5)
    assert covered(everything) >= max(covered(shots['line']), covered(shots['colour']))


# --- going back --------------------------------------------------------------------------------------------------

def project_after_three_changes():
    """A project, and the state it was in before anything was revised."""
    project = a_project_with_marks()
    before = json.dumps(project.to_dict(), sort_keys=True)
    stroke = [m for m in project.marks if m.kind == 'stroke'][0]
    fill = [m for m in project.marks if m.kind == 'fill'][0]
    project.revise_mark(fill.id, appearance={'fill': '#3355AA'})
    project.supersede(stroke.id, reason='not where it should be')
    project.remove_mark(project.marks[-1].id)
    return project, before, stroke, fill


def test_rewinding_everything_restores_the_file_exactly():
    """**The requirement on the log: it must be sufficient to reverse itself.** Not "the drawing looks the same" --
    the file, byte for byte. Anything less means a round trip through a correction leaves a residue, and a residue
    that accumulates over a long conversation is what makes people stop trusting undo."""
    project, before, _, _ = project_after_three_changes()
    assert json.dumps(project.to_dict(), sort_keys=True) != before

    undone = project.rewind(3)          # the three changes this test made, not the fixture's construction

    assert [e['op'] for e in undone] == ['remove', 'supersede', 'revise'], 'newest first'
    # **The marks come back byte for byte; the log does not, and should not.** The rewind is itself recorded, so a
    # project that was walked back does not look like one that was drawn in fewer steps.
    assert json.dumps([m.to_dict() for m in project.marks], sort_keys=True) ==            json.dumps(json.loads(before)['marks'], sort_keys=True)
    assert project.log and project.log[-1]['op'] == 'rewind'
    assert project.log[-1]['undid'] == ['remove', 'supersede', 'revise']
    assert [m.id for m in project.marks] == ['m0001', 'm0002', 'm0003', 'm0004', 'm0005']
    assert all(m.state == LIVE for m in project.marks)


def test_rewinding_a_removal_puts_the_mark_back_where_it_was():
    """`remove` is the one operation whose mark is taken out of the list entirely. Appending it on undo would leave
    the file's order different from the order it had, so undoing everything would still not restore the file -- the
    mark's `seq` was never lost and the list has to respect it."""
    project = a_project_with_marks()
    before = json.dumps(project.to_dict(), sort_keys=True)
    victim = project.marks[0]
    project.remove_mark(victim.id)
    assert victim.id not in [m.id for m in project.marks]

    base = len(project.log)
    project.rewind(1)                   # undo the removal, not the fixture's construction
    assert [m.id for m in project.marks] == [m['id'] for m in json.loads(before)['marks']]
    # The marks are exactly as they were; the log ends with the record that a rewind happened. That difference is the
    # point -- a project walked back must not look like one that was drawn in fewer steps.
    assert json.dumps([m.to_dict() for m in project.marks], sort_keys=True) == \
           json.dumps(json.loads(before)['marks'], sort_keys=True)
    assert ops_since(project, base - 1) == ['rewind']


def test_rewinding_partway_lands_on_a_state_the_drawing_was_actually_in():
    """Newest first, so a partial rewind is one of the project's own past states rather than a half-applied edit."""
    project, _, stroke, fill = project_after_three_changes()
    base = len(project.log)
    project.rewind(2)
    assert ops_since(project, base - 3) == ['revise', 'rewind']
    assert project.by_id(fill.id).appearance['fill'] == '#3355AA', 'the revise should still stand'
    # the stroke is back and the removed mark is back, because both were undone
    assert project.by_id(stroke.id).state == LIVE
    assert len(project.marks) == 5


def test_an_operation_the_log_cannot_reverse_is_refused_without_corrupting_the_log():
    """Forward compatibility matters here: a newer writer could leave an entry this version does not understand. The
    honest answer is to stop, not to guess -- and to leave the log as it was so the file is still usable."""
    project = a_project_with_marks()
    project._record('teleport', ids=['m0001'])
    depth = len(project.log)
    with pytest.raises(ValueError) as err:
        project.rewind(None)
    assert 'teleport' in str(err.value)
    assert len(project.log) == depth, 'a refused rewind must not eat log entries'


def test_rewinding_more_steps_than_exist_undoes_what_there_is_and_no_more():
    """Asking to go back further than the history goes is not an error -- it undoes everything there is."""
    project = a_project_with_marks()
    base = len(project.log)
    project.revise_mark(project.marks[0].id, appearance={'colour': '#000000'})
    undone = project.rewind(999)
    assert len(undone) == base + 1, 'every operation there is, and no more'
    assert project.marks == [], 'undoing everything includes the additions'
    assert set(e['op'] for e in project.log) == {'rewind'}

    with pytest.raises(ValueError):
        project.rewind(-1)


def test_a_supersede_reason_is_kept_because_removed_and_never_drawn_are_different():
    """A mark taken out and a mark that was never made look identical in the rendered image. The reason is the only
    thing that tells them apart, and it is also what a report can show without re-deriving anything."""
    project = a_project_with_marks()
    mark = project.marks[2]
    project.supersede(mark.id, reason='この線は位置が違う')

    entry = [e for e in project.log if e['op'] == 'supersede'][-1]
    assert entry['reason'] == 'この線は位置が違う'
    assert entry['ids'] == [mark.id]

    # and it survives a round trip, so a project opened tomorrow still knows why
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), 'p.json')
    save_project(project, path)
    assert [e for e in load_project(path).log if e['op'] == 'supersede'][-1]['reason'] == 'この線は位置が違う'


def test_the_log_records_the_previous_values_not_only_that_something_changed():
    """Without them the log says an edit happened but cannot put it back, and "go back to how it was two steps ago"
    -- which is the sentence this software exists to answer -- would be unanswerable from the file."""
    project = a_project_with_marks()
    fill = [m for m in project.marks if m.kind == 'fill'][0]
    was = fill.appearance['fill']
    project.revise_mark(fill.id, appearance={'fill': '#ABCDEF'})

    entry = project.log[-1]
    assert entry['before']['appearance']['fill'] == was
    assert entry['after']['appearance']['fill'] == '#ABCDEF'
    assert entry['changed'] == ['appearance']


# --- the commit gate ---------------------------------------------------------------------------------------------
#
# A drawing program does not put a stroke into the drawing when the pen lifts. It sits provisionally, and starting the
# next one without confirming clears it. Two jobs, and both are about the drawing rather than the file: the artist gets
# a moment to decide that this stroke is the one, and meaningless lines do not accumulate. Without the gate every
# experimental stroke stays and the picture silts up, because adding is the easy action and discarding is the effortful
# one. Here it is the other way round.

def a_draft(project, seed=1, commit=False):
    from lineweight import stroke_record
    return project.add_stroke(stroke_record([(20.0, 20.0), (150.0, 60.0 + seed * 10)], 'ink', seed=seed),
                              commit=commit)


def test_a_draft_is_drawn_but_is_not_part_of_the_drawing():
    """It does not render and the ordered accessors do not return it. Anything else would mean the gate does nothing:
    a provisional stroke that is already in the picture is simply a stroke."""
    from lineweight.raster import render_marks

    project = Project(width=200, height=200)
    draft = a_draft(project)
    assert draft.state == DRAFT
    assert project.drafts() == [draft]
    assert project.live() == []
    assert project.in_stage('line') == []
    assert project.upto('line') == []
    assert covered(render_marks([m.to_dict() for m in project.live()], 200, 200, 1.0)) == 0


def test_starting_the_next_attempt_clears_the_uncommitted_one():
    """**This is the feature.** The previous candidate does not survive into the next attempt, because a mark that
    survives by default is one nobody decided to keep."""
    project = Project(width=200, height=200)
    first = a_draft(project, seed=1)
    dropped = project.begin()
    assert [m.id for m in dropped] == [first.id]
    assert project.marks == []

    second = a_draft(project, seed=2)
    assert project.marks == [second]
    assert first.id not in [m.id for m in project.marks]


def test_committing_is_what_puts_a_mark_in_the_drawing():
    project = Project(width=200, height=200)
    draft = a_draft(project)
    accepted = project.commit()
    assert [m.id for m in accepted] == [draft.id]
    assert draft.state == LIVE
    assert [m.id for m in project.live()] == [draft.id]
    assert project.drafts() == []


def test_the_next_attempt_does_not_disturb_what_was_already_committed():
    """Otherwise the gate would be unusable: every new stroke would threaten the ones already accepted."""
    project = Project(width=200, height=200)
    a_draft(project)
    project.commit()
    kept = json.dumps([m.to_dict() for m in project.marks], sort_keys=True)

    a_draft(project, seed=2)
    project.begin()
    a_draft(project, seed=3)
    assert json.dumps([m.to_dict() for m in project.marks], sort_keys=True) != kept, \
        'the new draft should be in the file'

    project.begin()
    # **The marks are what has to match, not the whole file.** The log and the id counter legitimately record that
    # attempts were made and thrown away -- a project that has had failed attempts is not the same file as one that
    # has not, and pretending otherwise would mean not keeping the record.
    assert json.dumps([m.to_dict() for m in project.marks], sort_keys=True) == kept, \
        'after the drafts are dropped the committed marks must be exactly as they were'
    assert [e['op'] for e in project.log].count('discard') == 2, 'the attempts should still be in the log'


def test_discarding_a_committed_mark_is_refused_rather_than_silently_ignored():
    """`discard` means "this was never accepted". Pointing it at a committed mark is a different intent -- taking
    something out of the drawing -- and that operation is `supersede`. Quietly doing the wrong one would lose work."""
    project = Project(width=200, height=200)
    mark = a_draft(project)
    project.commit()
    with pytest.raises(ValueError) as err:
        project.discard(mark.id)
    assert mark.id in str(err.value)
    assert mark.state == LIVE, 'a refused discard must not have taken effect'


def test_an_id_is_not_reused_after_a_discard_because_the_log_would_become_ambiguous():
    """The log is the record of what happened. If a discarded mark released its id, the log would read `draft m0001`,
    `discard m0001`, `draft m0001` -- which says one stroke was drafted twice when it was two different strokes."""
    project = Project(width=200, height=200)
    ids = []
    for seed in range(4):
        project.begin()
        ids.append(a_draft(project, seed=seed).id)
    project.commit()

    assert len(set(ids)) == len(ids), 'ids were reused across attempts: %s' % ids
    drafted = [i for e in project.log if e['op'] == 'draft' for i in e['ids']]
    assert len(set(drafted)) == len(drafted), 'the log names the same id for two different attempts'


def test_the_discarded_attempts_do_not_pile_up_in_the_file():
    """The second job of the gate. Five attempts must leave a five-mark drawing no larger than the one mark kept,
    because the alternative -- every experiment staying -- is what silts a drawing up."""
    project = Project(width=200, height=200)
    for seed in range(5):
        project.begin()
        a_draft(project, seed=seed)
    project.commit()

    assert len(project.marks) == 1, 'the discarded attempts are still in the file: %s' % [m.id for m in project.marks]
    assert len(project.log) == 10, 'the log should still say what happened: %d' % len(project.log)


def test_drafts_survive_a_round_trip_so_an_unfinished_attempt_is_not_lost():
    """A project saved mid-attempt has to come back mid-attempt. Silently committing the draft, or dropping it, would
    both be ways of losing a decision that had not been made yet."""
    from lineweight import save_project, load_project
    import tempfile, os

    project = Project(width=200, height=200)
    a_draft(project)
    project.commit()
    pending = a_draft(project, seed=2)

    path = os.path.join(tempfile.mkdtemp(), 'p.json')
    save_project(project, path)
    back = load_project(path)

    assert [m.id for m in back.drafts()] == [pending.id]
    assert len(back.live()) == 1
    # and continuing the attempt still clears only the unfinished one
    back.begin()
    assert len(back.live()) == 1 and back.drafts() == []


# --- the switch, and the layer structure a project may choose -----------------------------------------------

def test_incremental_is_a_project_setting_not_a_baked_in_behaviour():
    """Artists differ on whether every stroke must be accepted, and the same artist differs by task: it is the right
    setting for careful linework and the wrong one for blocking in tone. So it is a setting."""
    from lineweight import stroke_record

    off = Project(width=200, height=200)
    off.add_stroke(stroke_record([(10.0, 10.0), (90.0, 40.0)], 'ink', seed=1))
    assert off.marks[-1].state == LIVE, 'with the gate off a mark is in the drawing immediately'

    on = Project(width=200, height=200, incremental=True)
    on.add_stroke(stroke_record([(10.0, 10.0), (90.0, 40.0)], 'ink', seed=1))
    assert on.marks[-1].state == DRAFT, 'with the gate on a mark has to be accepted'
    assert on.live() == []


def test_a_single_call_can_override_the_project_setting():
    """A project can reasonably want the gate on for the linework and off for a fill, so the argument wins over the
    setting rather than the other way round."""
    from lineweight import stroke_record
    from lineweight.raster import render_marks
    from lineweight import region_fill

    project = Project(width=200, height=200, incremental=True)
    project.add_stroke(stroke_record([(10.0, 10.0), (90.0, 40.0)], 'ink', seed=1), commit=True)
    assert project.marks[-1].state == LIVE
    square = [[(20.0, 100.0), (120.0, 100.0)], [(122.0, 102.0), (122.0, 180.0)],
              [(120.0, 182.0), (20.0, 182.0)], [(18.0, 180.0), (18.0, 102.0)]]
    from lineweight import Region
    region = region_fill(square, 3.0)[0]
    project.add_fill(region, commit=False)
    assert project.marks[-1].state == DRAFT

    # and with the gate off, a caller can still ask for a draft explicitly
    plain = Project(width=200, height=200)
    plain.add_fill(region, commit=False)
    assert plain.marks[-1].state == DRAFT


def test_the_switch_survives_a_round_trip(tmp_path):
    """Reopening a project must not silently change whether work has to be accepted, or a file saved with the gate on
    would start committing strokes the artist never confirmed."""
    project = Project(width=200, height=200, incremental=True)
    path = str(tmp_path / 'p.json')
    save_project(project, path)
    assert load_project(path).incremental is True
    assert Project.from_dict(Project().to_dict()).incremental is False


def test_a_rough_pass_can_sit_underneath_the_others():
    """The base-draft workflow: build a rough, then draw the clean passes over it. Offered rather than assumed --
    of two recorded processes examined, one began on a genuinely blank canvas and the other traced a faded image, so
    the staging has to be the project's choice and `stages` is a per-project list for exactly that reason."""
    from lineweight import ROUGH_STAGES, stroke_record

    assert [s['role'] for s in ROUGH_STAGES] == ['rough', 'line', 'value', 'colour', 'refine']
    project = Project(width=200, height=200, stages=ROUGH_STAGES)
    rough = project.add_stroke(stroke_record([(10.0, 10.0), (180.0, 90.0)], 'pencil', seed=1), stage='rough')
    clean = project.add_stroke(stroke_record([(15.0, 12.0), (178.0, 88.0)], 'ink', seed=2), stage='line')

    assert [m.id for m in project.upto('rough')] == [rough.id], 'the rough on its own is the first state'
    assert [m.id for m in project.upto('line')] == [rough.id, clean.id], 'the clean line sits over it'
    assert [m.id for m in project.in_stage('rough')] == [rough.id]

    # the rough can be taken out once it has done its job, and brought back: it stays in the file either way
    project.supersede(rough.id, reason='clean line is done')
    assert [m.id for m in project.upto('line')] == [clean.id]
    project.restore(rough.id)
    assert [m.id for m in project.upto('line')] == [rough.id, clean.id]


def test_a_rewind_is_itself_recorded_because_a_truncatable_record_is_not_one():
    """The log is the file's account of how the drawing got there. If rewinding popped the entries and said nothing,
    a project walked back ten times would read exactly like one drawn in ten fewer steps -- the file would claim to be
    a record while quietly losing the part where the artist changed their mind."""
    project = a_project_with_marks()
    project.revise_mark(project.marks[0].id, appearance={'colour': '#111111'})
    project.supersede(project.marks[1].id, reason='not this one')

    undone = project.rewind(1)
    assert [e['op'] for e in undone] == ['supersede']
    assert project.log[-1]['op'] == 'rewind'
    assert project.log[-1]['undid'] == ['supersede']

    # and rewinding again records that too, rather than replacing the previous record. Counted rather than sliced:
    # a rewind *shortens* the log, so an index captured before it points somewhere different afterwards -- which is
    # how an earlier version of this test ended up asserting about an empty slice.
    project.rewind(1)
    markers = [e for e in project.log if e['op'] == 'rewind']
    assert len(markers) == 2, 'both rewinds should be on the record'
    assert [e['undid'] for e in markers] == [['supersede'], ['revise']]


def test_a_rewind_marker_is_not_itself_undoable():
    """It records an action rather than being one. Otherwise rewinding twice would undo the record of the first
    rewind, and the log would end up saying less the more the artist went back."""
    project = a_project_with_marks()
    project.revise_mark(project.marks[0].id, appearance={'colour': '#111111'})
    project.rewind(1)
    assert [e['op'] for e in project.log if e['op'] == 'rewind'] == ['rewind']

    # the next rewind moves on to the fixture's additions -- it does not undo the marker. The way to tell is that the
    # marker count only ever grows.
    undone = project.rewind(1)
    assert [e['op'] for e in undone] == ['add'], 'the marker is not what gets undone next'
    assert len([e for e in project.log if e['op'] == 'rewind']) == 2, 'and the first marker is still there'


def test_rewinding_a_commit_puts_the_mark_back_to_draft():
    """Acceptance is a state on a mark, so undoing it restores the state it had -- the stroke goes back to being a
    candidate rather than disappearing."""
    from lineweight import stroke_record

    project = Project(width=200, height=200, incremental=True)
    mark = project.add_stroke(stroke_record([(10.0, 10.0), (90.0, 40.0)], 'ink', seed=1))
    assert mark.state == DRAFT
    project.commit()
    assert mark.state == LIVE

    project.rewind(1)
    assert mark.state == DRAFT, 'undoing an acceptance restores the draft, not nothing'
    assert mark in project.marks


# --- turns: the unit a person actually corrects in ----------------------------------------------------------

def test_a_mark_knows_which_instruction_produced_it():
    """The stated use is describing a drawing and then correcting it, so the unit somebody thinks in is the
    instruction -- "the eyebrow I just asked for" -- not the mark id. Nothing can walk back a conversation without
    knowing which marks a sentence produced."""
    from lineweight import stroke_record

    project = Project(width=200, height=200)
    project.next_turn('draw a rough')
    a = project.add_stroke(stroke_record([(10.0, 10.0), (90.0, 40.0)], 'ink', seed=1))
    b = project.add_stroke(stroke_record([(10.0, 60.0), (90.0, 90.0)], 'ink', seed=2))
    project.next_turn('add an inner line')
    c = project.add_stroke(stroke_record([(20.0, 20.0), (80.0, 80.0)], 'fine', seed=3))

    assert [m.id for m in project.marks_from_turn(1)] == [a.id, b.id]
    assert [m.id for m in project.marks_from_turn(2)] == [c.id]
    assert project.turns() == [1, 2]
    assert a.provenance['turn'] == 1 and c.provenance['turn'] == 2
    # and every mark carries one, including the very first, so there is no mark outside the conversation
    assert all(m.provenance.get('turn') is not None for m in project.marks)


def test_a_turn_survives_a_round_trip(tmp_path):
    from lineweight import stroke_record

    project = Project(width=200, height=200)
    project.next_turn('first')
    project.add_stroke(stroke_record([(10.0, 10.0), (90.0, 40.0)], 'ink', seed=1))
    project.next_turn('second')
    project.add_stroke(stroke_record([(10.0, 60.0), (90.0, 90.0)], 'ink', seed=2))

    path = str(tmp_path / 'p.json')
    save_project(project, path)
    back = load_project(path)
    assert back.turn == 2
    assert [m.provenance['turn'] for m in back.marks] == [1, 2]
    assert [m.id for m in back.marks_from_turn(2)] == [project.marks[1].id]


def test_undoing_the_last_turn_means_the_last_turn_that_did_something():
    """**The corrective instruction is a turn of its own.** The artist says "that line is wrong" and that sentence
    advances the turn counter before anything is undone -- so looking only at the current turn finds nothing and the
    correction silently does nothing at all."""
    from lineweight import stroke_record

    project = Project(width=200, height=200)
    project.next_turn('draw a rough')
    project.add_stroke(stroke_record([(10.0, 10.0), (90.0, 40.0)], 'ink', seed=1))
    project.add_stroke(stroke_record([(10.0, 60.0), (90.0, 90.0)], 'ink', seed=2))
    kept = [m.id for m in project.live()]

    project.next_turn('add an inner line')
    inner = project.add_stroke(stroke_record([(20.0, 20.0), (80.0, 80.0)], 'fine', seed=3))

    project.next_turn('no, that line is wrong')
    undone = project.undo_last_turn()

    assert [e['op'] for e in undone] == ['add'], 'only the inner line should go'
    assert [m.id for m in project.live()] == kept, 'the first instruction must survive'
    assert inner.id not in [m.id for m in project.marks]


def test_undoing_turns_lays_one_instruction_on_top_of_another():
    """Walking back a conversation means walking back instructions, in order, until the drawing is where it was."""
    from lineweight import stroke_record

    project = Project(width=200, height=200)
    for turn, count in ((1, 2), (2, 1), (3, 3)):
        project.next_turn('instruction %d' % turn)
        for i in range(count):
            project.add_stroke(stroke_record([(10.0 + i, 10.0), (90.0, 40.0 + i)], 'ink', seed=turn * 10 + i))

    assert [len(project.marks_from_turn(t)) for t in (1, 2, 3)] == [2, 1, 3]
    project.next_turn('undo that')
    project.undo_last_turn()
    assert len(project.marks_from_turn(3)) == 0 and len(project.live()) == 3

    project.next_turn('and that')
    project.undo_last_turn()
    assert len(project.live()) == 2, 'back to the first instruction only'


def test_rewinding_to_a_turn_undoes_everything_from_it_onwards_and_records_it():
    from lineweight import stroke_record

    project = Project(width=200, height=200)
    project.next_turn('first')
    project.add_stroke(stroke_record([(10.0, 10.0), (90.0, 40.0)], 'ink', seed=1))
    project.next_turn('second')
    project.add_stroke(stroke_record([(10.0, 60.0), (90.0, 90.0)], 'ink', seed=2))
    project.next_turn('third')
    project.add_stroke(stroke_record([(20.0, 20.0), (80.0, 80.0)], 'fine', seed=3))

    project.rewind_to_turn(2)
    assert len(project.live()) == 1, 'turns two and three should be gone'
    assert project.log[-1]['op'] == 'rewind', 'and the walk back is on the record'

    # the turn markers survive as history even though the work they introduced is gone
    assert [e['turn'] for e in project.log if e['op'] == 'turn'] == [1, 2, 3]


def test_undoing_a_turn_that_did_nothing_is_not_an_error():
    """A turn that only asked a question, or was corrected before it drew anything, has nothing to undo and saying so
    by doing nothing is right -- raising would make the caller special-case it."""
    project = Project(width=200, height=200)
    project.next_turn('just thinking')
    assert project.undo_last_turn() == []
    assert project.live() == []


# ------------------------------------------------------------------------ the second pass: roles on finished work

def test_assigning_a_role_leaves_the_geometry_untouched():
    """**This is the property that makes it a second pass rather than a second attempt.**

    The drawing convention's order of work is form first and width variation afterwards. So a role is a decision about
    a stroke that already exists, and assigning one must not move a single point -- if it did, the first pass would
    have been wasted and "get the shape right, then decide the hierarchy" would not be available.

    Compared field by field over the whole geometry rather than just `centre`, because a role that quietly resampled,
    or that reset the seed and therefore the tremor, would be just as damaging and would not show up in a centre
    check alone.
    """
    from lineweight.core import stroke_record

    project = Project(width=200, height=200)
    project.add_stroke(stroke_record([(10, 10), (100, 40), (180, 20)], 'ink', seed=7, resolution=11))
    before = dict(project.by_id('m0001').geometry)

    project.assign_role('m0001', 'silhouette')
    after = dict(project.by_id('m0001').geometry)

    assert set(after) == set(before), 'a role assignment added or removed a field'
    changed = {k for k in after if after[k] != before[k]}
    assert changed == {'role'}, 'assigning a role changed %r as well' % sorted(changed - {'role'})
    for field in ('centre', 'control', 'pressure', 'brush', 'seed', 'resolution'):
        assert after[field] == before[field], 'assigning a role changed %r' % field


def test_the_role_changes_the_drawing_without_redrawing_anything():
    """The point of touching only the role: one record, two drawings.

    The record is unchanged and the *expansion* of it is not, because every width comes from `stroke_widths`, which
    reads the role. That is what makes the second pass cheap and reversible -- there is no second copy of the stroke
    to keep in step.
    """
    from lineweight.core import from_record, stroke_record

    record = stroke_record([(10, 10), (100, 40), (180, 20)], 'ink', seed=7)
    project = Project(width=200, height=200)
    project.add_stroke(record)
    plain, _ = from_record(project.by_id('m0001').geometry)

    project.assign_role('m0001', 'silhouette')
    heavy, _ = from_record(project.by_id('m0001').geometry)

    assert plain != heavy, 'the outline did not change, so the role is being ignored'
    assert project.by_id('m0001').geometry['centre'] == record['centre']


def test_a_whole_second_pass_is_one_undoable_operation():
    """`assign_roles` is one decision even when it covers many strokes.

    Forty roles assigned one at a time appear in the log as forty operations, and "undo the hierarchy I just set" then
    has no answer -- which is the sentence this software exists to answer. The undo has to restore the *inks* too, and
    it does so because they were never written down: an absent colour means the role decides, so rewinding the role
    rewinds the ink with it.
    """
    from lineweight.core import mark_ink, stroke_record

    project = Project(width=200, height=200)
    for i in range(4):
        project.add_stroke(stroke_record([(10, 10 + i * 20), (100, 40 + i * 20), (180, 20 + i * 20)],
                                         'ink', seed=i))
    before_inks = [mark_ink(m.to_dict()) for m in project.live()]
    assert len(set(before_inks)) == 1

    project.next_turn('the line hierarchy')
    project.assign_roles({m.id: 'silhouette' for m in project.live()})
    assert {mark_ink(m.to_dict()) for m in project.live()} == {roles.ROLES['silhouette'].ink}

    # the correction is a turn of its own -- that is what "undo the last thing I said" means
    project.next_turn('no, that hierarchy is wrong')
    project.undo_last_turn()
    assert [m.geometry.get('role', '') for m in project.live()] == [''] * 4
    assert [mark_ink(m.to_dict()) for m in project.live()] == before_inks, \
        'undoing the roles did not undo the inks'


def test_a_fill_cannot_be_given_a_line_role():
    """A role describes a line. Accepting it on a fill would store a claim that nothing can act on."""
    project = Project(width=200, height=200)
    project.add_fill(Region(points=[(10.0, 10.0), (90.0, 10.0), (90.0, 90.0)], d='M 10 10 L 90 10 L 90 90 Z'))
    with pytest.raises(ValueError):
        project.assign_role(project.by_id('m0001').id, 'silhouette')


def test_an_unknown_role_is_refused_by_the_document_and_a_role_can_be_cleared():
    """The document refuses the same names the registry does, and clearing is a real operation.

    Clearing matters because a role is not a permanent classification: an artist who decides a line is an interior
    line after all has to be able to say so, and the result must be the brush width exactly as given rather than some
    other role's.
    """
    from lineweight.core import stroke_record, stroke_widths

    project = Project(width=200, height=200)
    project.add_stroke(stroke_record([(10, 10), (100, 40), (180, 20)], 'ink', seed=7))
    with pytest.raises(ValueError):
        project.assign_role('m0001', 'outline')
    project.assign_role('m0001', 'detail')
    thinned = stroke_widths(project.by_id('m0001').geometry)
    project.assign_role('m0001', '')
    assert project.by_id('m0001').geometry['role'] == ''
    assert stroke_widths(project.by_id('m0001').geometry) > thinned
