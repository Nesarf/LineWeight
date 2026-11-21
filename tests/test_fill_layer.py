"""Colour gets a sheet of its own, and so does the eraser.

`add_stroke` has taken a `layer` for as long as the layer stack has existed. `add_fill` and `add_erase` did not, and
nothing complained: a project file lists every mark and every mark renders, so a fill without a layer looks complete
from inside. It is `psd.layers_from_project` that groups by `Mark.layer` -- so all the colour went into the sheet whose
name is empty, and every eraser went there too, where it could not remove what it was drawn to remove.

These tests are about that grouping rather than about pixels: which sheet a mark says it is on, what the PSD writer
makes of that, and whether the answer survives a save.
"""
from __future__ import annotations

import pytest

from lineweight import Project, Region, load_project, psd, save_project, stroke_record


def a_region(x=10.0, y=10.0):
    return Region(points=[(x, y), (x + 60.0, y), (x + 60.0, y + 40.0), (x, y + 40.0)],
                  d='M %g %g L %g %g L %g %g L %g %g Z' % (x, y, x + 60, y, x + 60, y + 40, x, y + 40))


def test_a_fill_carries_the_layer_it_was_given():
    project = Project(width=200, height=150)
    mark = project.add_fill(a_region(), colour='#3355AA', layer='COLOUR')
    assert mark.layer == 'COLOUR'
    assert 'COLOUR' in project.layers_in_use()


def test_an_erase_carries_the_layer_it_was_given():
    project = Project(width=200, height=150)
    mark = project.add_erase(a_region(), layer='LINE')
    assert mark.layer == 'LINE'


def test_a_fill_without_a_layer_is_unchanged_for_every_existing_caller():
    """The default is the empty name, which is what these two methods produced before the parameter existed. Adding an
    argument must not move a single existing mark."""
    project = Project(width=200, height=150)
    assert project.add_fill(a_region()).layer == ''
    assert project.add_erase(a_region()).layer == ''


def test_the_layer_survives_a_save_and_a_load(tmp_path):
    project = Project(width=200, height=150)
    project.add_stroke(stroke_record([(5.0, 5.0), (80.0, 60.0)], 'ink', seed=2), layer='LINE')
    project.add_fill(a_region(), colour='#3355AA', layer='COLOUR')
    path = str(tmp_path / 'layers.json')
    save_project(project, path)
    reread = load_project(path)
    assert reread.marks[1].layer == 'COLOUR'
    assert set(reread.layers_in_use()) == {'LINE', 'COLOUR'}


def test_the_psd_writer_makes_one_sheet_per_name_and_the_colour_has_its_own():
    """The reason the parameter exists. Before it, this project produced one sheet: DEFAULT_LAYER, holding the line and
    the colour together, and nothing in the file said which was which."""
    project = Project(width=120, height=90)
    project.add_stroke(stroke_record([(6.0, 6.0), (100.0, 70.0)], 'ink', seed=3), layer='LINE')
    project.add_fill(a_region(20.0, 20.0), colour='#3355AA', layer='COLOUR')
    sheets = psd.layers_from_project(project)
    assert [sheet.name for sheet in sheets] == ['LINE', 'COLOUR'], 'the order is the drawing order'


def test_a_figure_that_declares_its_layers_refuses_an_undeclared_one():
    """`_check_layer` is the gate, and it was never reached by a fill before because the call was not there."""
    from lineweight import figure

    project = Project(width=200, height=150)
    project.set_figure(figure.standard())
    named = sorted(project.figure.layer_names())[0]
    assert project.add_fill(a_region(), layer=named).layer == named
    with pytest.raises(ValueError) as err:
        project.add_fill(a_region(), layer='NOT-A-LAYER')
    assert 'NOT-A-LAYER' in str(err.value)
    with pytest.raises(ValueError):
        project.add_erase(a_region(), layer='NOT-A-LAYER')
