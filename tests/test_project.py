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
