"""Writing a file that another program may have open, without ever leaving half of one behind.

**What these assert is not "the bytes arrived".** They assert the property that the atomic write exists for: **the
target is either the old file or the new one, and a failure leaves the old one exactly as it was.** A test that only
checked the happy path would pass on a writer that truncated the target first, which is the whole fault.

The hazard is concrete. These writers replace files that SAI, Animate and Illustrator open: a PSD that SAI is holding,
an XFL folder Animate is reading, a PNG a person is looking at. An application that reads during the window gets a
prefix of a drawing.

**The temporary is a sibling of the target**, and one test says why: a rename is only atomic within one filesystem, so
a temporary in the system directory would turn `os.replace` into a copy, which is neither atomic nor faster.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest


def test_a_failed_write_leaves_the_previous_file_exactly_as_it_was(tmp_path):
    """**The property, stated directly.** The render function raises halfway through and the old file is untouched.

    This is the case that a truncate-then-write cannot pass: it would have destroyed the old bytes before finding out
    that the new ones could not be produced.
    """
    from lineweight.atomic import write_atomic

    target = tmp_path / 'drawing.json'
    target.write_text('{"what": "the drawing SAI has open"}\n', encoding='utf-8')
    before = target.read_bytes()

    def explode(handle):
        handle.write('{"what": "half of the next one"')
        raise RuntimeError('the generator gave up midway')

    with pytest.raises(RuntimeError):
        write_atomic(str(target), explode)

    assert target.read_bytes() == before, 'the previous file must survive a failed replacement'
    assert not list(tmp_path.glob('.*.tmp')), 'and the temporary must not be left behind'


def test_a_successful_write_replaces_whole_and_leaves_no_temporary(tmp_path):
    from lineweight.atomic import write_atomic

    target = tmp_path / 'drawing.json'
    target.write_text('{"v": 1}\n', encoding='utf-8')
    write_atomic(str(target), lambda h: h.write('{"v": 2}\n'))
    assert json.loads(target.read_text(encoding='utf-8')) == {'v': 2}
    assert sorted(p.name for p in tmp_path.iterdir()) == ['drawing.json']


def test_the_temporary_is_a_sibling_of_the_target(tmp_path):
    """**A rename is atomic only within one filesystem**, so the temporary cannot live in the system temp directory.

    Put it there and `os.replace` becomes a cross-device copy: not atomic, and no faster than writing in place -- the
    fault would be back, wearing the code that was meant to remove it.
    """
    from lineweight.atomic import atomic_path

    target = tmp_path / 'sub' / 'drawing.xfl'
    temporary = atomic_path(str(target))
    assert os.path.dirname(temporary) == os.path.dirname(str(target))
    assert os.path.basename(temporary).startswith('.')


def test_the_project_and_the_stroke_list_are_written_atomically(tmp_path):
    """The two writers that carry a drawing rather than a picture."""
    from lineweight.core import save_strokes
    from lineweight.project import Project, load_project, save_project

    project = Project(width=200, height=200)
    path = tmp_path / 'drawing.lw'
    save_project(project, str(path))
    save_project(project, str(path))          # twice, over itself, which is the case that matters
    assert load_project(str(path)).width == 200
    assert not list(tmp_path.glob('.*.tmp'))

    strokes = tmp_path / 'strokes.json'
    save_strokes([{'centre': [[0, 0], [1, 1]]}], str(strokes))
    assert json.loads(strokes.read_text(encoding='utf-8'))['strokes']
    assert not list(tmp_path.glob('.*.tmp'))


def test_an_xfl_folder_replaces_the_old_one_rather_than_merging_with_it(tmp_path):
    """**A folder cannot be replaced in one operation, so what is asserted is the weaker property it does have.**

    Write a document, then write a different one to the same path. The result must be the second document *and
    nothing of the first* -- a merge would leave `DOMDocument.xml` from the new write next to library files from the
    old, which is a folder Animate opens and renders wrongly rather than refuses.
    """
    from lineweight.doc import Document
    from lineweight.xfl import write_xfl

    target = tmp_path / 'drawing.xfl'
    write_xfl(Document(width=100, height=100), str(target))
    (target / 'LIBRARY' / 'leftover.xml').write_text('<stale/>', encoding='utf-8')

    write_xfl(Document(width=50, height=50), str(target))

    assert (target / 'DOMDocument.xml').exists()
    assert not (target / 'LIBRARY' / 'leftover.xml').exists(), \
        'the new tree must not be merged into the old one'
    assert not (tmp_path / 'drawing.xfl.old').exists(), 'and the retired tree must be cleaned up'
    assert not (tmp_path / 'drawing.xfl.new').exists()
