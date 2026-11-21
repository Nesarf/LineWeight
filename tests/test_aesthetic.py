"""The library's own judgement has to be askable, and it has to be findable from anywhere.

Until now the only way to find out what this library knows was to read `AESTHETIC-LIBRARY.md` -- 352 KB -- or to run
`tools/check_learn.py`, which hard-coded `E:\\lineweight\\learn` and so worked on exactly one machine. The module under
test is the name for that knowledge, and these tests are about three things: the shape each accessor answers with, that
`verify()` finds nothing wrong with data that is in fact in order, and that the path does not depend on where the caller
happens to be standing.

**The check itself is the load-bearing part.** `verify()` caught eleven mistakes in its own first version against data
the proven checker called clean -- a `count` without an `items` list reported as an error when it is a note, a citation
matched before its page number was taken off, and an opacity comparison written as a set membership test. Those are
recorded in the module; the test that matters here is that the two implementations now agree.
"""
from __future__ import annotations

import os

import pytest

from lineweight import aesthetic


def test_the_facts_table_loads_with_its_purpose_and_its_entries():
    table = aesthetic.facts()
    assert isinstance(table, dict)
    assert 'purpose' in table, 'the file says what it collects, in the file'
    assert len(aesthetic.names()) == 47
    assert 'purpose' not in aesthetic.names(), 'the note about the file is not one of its facts'


def test_one_fact_keeps_the_shape_the_file_gave_it():
    entry = aesthetic.fact('line_kinds')
    assert entry['count'] == 3
    assert entry['items'] == ['C curve', 'straight', 'S curve']
    assert entry['source'], 'a fact without a source is a claim, not a fact'


def test_an_unknown_name_is_an_error_that_names_the_ones_that_exist():
    with pytest.raises(KeyError) as err:
        aesthetic.fact('no_such_fact')
    assert 'no_such_fact' in str(err.value)
    assert 'line_kinds' in str(err.value)


def test_the_error_table_carries_what_where_why():
    rows = aesthetic.errors()
    assert len(rows) == 10
    for row in rows:
        for field in ('pattern', 'what', 'why'):
            assert row.get(field), '%s has no %s' % (row.get('pattern', '<unnamed>'), field)


def test_the_shelf_parses_into_rows_with_their_headers():
    rows = aesthetic.sources()
    assert len(rows) >= 12
    assert all('title' in row and 'file' in row for row in rows), 'the table heads are the keys'


def test_the_extract_index_is_a_list_and_says_which_book_each_page_came_from():
    index = aesthetic.extracts()
    assert isinstance(index, list)
    assert index, 'the repository ships extracts'
    assert all('book' in row and 'file' in row for row in index if isinstance(row, dict))


def test_every_check_passes_on_data_that_is_in_order():
    problems = aesthetic.verify()
    assert problems == [], 'verify reported: %s' % problems


def test_the_data_is_found_whatever_the_working_directory(monkeypatch, tmp_path):
    """The old checker hard-coded an absolute path, so it only ever ran where it was written. This one resolves the
    directory from the module's own location."""
    monkeypatch.setattr(aesthetic, '_LEARN', None)
    monkeypatch.chdir(tmp_path)
    assert os.path.isdir(aesthetic.learn_dir())
    assert aesthetic.learn_dir() == aesthetic.learn_dir(), 'the lookup is cached rather than repeated'


def test_verify_notices_a_fact_that_disagrees_with_the_code(monkeypatch):
    """The failure the whole check exists for, injected: a part whose role the code does not agree with."""
    table = aesthetic.facts()
    broken = dict(table)
    entry = dict(broken['part_roles'])
    items = [dict(item) for item in entry['items']]
    items[0] = dict(items[0], role='no-such-role')
    entry['items'] = items
    broken['part_roles'] = entry
    monkeypatch.setattr(aesthetic, 'facts', lambda: broken)
    problems = aesthetic.verify()
    assert problems
    assert any('no-such-role' in problem for problem in problems), problems
