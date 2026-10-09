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

from lineweight import (DEFAULT_STAGES, LIVE, SUPERSEDED, Mark, Project, Region, load_project, region_fill,
                        save_project, stroke_record)


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
    assert json.dumps(entry['geometry'], sort_keys=True) == geometry, 'the log should say what was lost'


def test_every_revision_is_recorded_in_order():
    """The log is what makes "the last thing you changed was wrong" answerable, which the stated use of this software
    -- describing, then correcting, repeatedly -- depends on."""
    project = a_project_with_marks()
    a, b = project.marks[0], project.marks[1]
    project.revise_mark(a.id, appearance={'colour': '#111111'})
    project.supersede(b.id)
    project.restore(b.id)
    project.revise_mark(a.id, note='second pass')
    project.remove_mark(b.id)

    assert [e['op'] for e in project.log] == ['revise', 'supersede', 'restore', 'revise', 'remove']
    assert [e['at'] for e in project.log] == list(range(5)), 'the log must keep its own order'
    assert project.log[0]['ids'] == [a.id] and 'appearance' in project.log[0]['changed']


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
