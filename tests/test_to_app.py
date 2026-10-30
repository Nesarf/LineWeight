"""The bridge from a finished project to a drawing application, without opening the application.

**What can be checked here and what cannot.** Whether Illustrator rebuilds the drawing needs Illustrator, a window and a
person watching it; that check lives in `tools/to_app.py --run` and is run by hand. What *can* be checked here is
everything before the launch: that a project becomes a document with the marks and layers it should, that drafts stay out,
and that the generated script carries the layer names and the sentinel path -- because a script that asks the application
to report somewhere else than where we wait would hang the run for its whole timeout.
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for extra in (ROOT, ROOT / 'tools'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from lineweight import app, core, project   # noqa: E402
import to_app                                # noqa: E402


def a_project(draft=False):
    p = project.Project(width=400, height=300)
    live = p.add_stroke(core.stroke_record([(40, 40), (360, 200)], 'ink', seed=1),
                        stage='line', note='a', layer='contour')
    live.appearance['colour'] = '#203040'
    p.next_turn()
    p.add_stroke(core.stroke_record([(40, 200), (360, 60)], 'ink', seed=2),
                 stage='line', note='b', layer='detail', commit=not draft)
    return p


def test_a_project_becomes_a_document_with_its_marks_and_layers():
    drawn = a_project()
    document, count, layers = to_app.project_to_document(drawn)
    assert count == 2
    assert layers == {'contour', 'detail'}
    assert len(document.layers) == 2, 'the two layers should survive as two'


def test_a_draft_is_not_handed_to_the_application():
    """A draft is a candidate. Handing one over turns "I am still deciding" into "this is in the document"."""
    drawn = a_project(draft=True)
    _document, count, layers = to_app.project_to_document(drawn)
    assert count == 1
    assert layers == {'contour'}


def test_the_script_carries_the_layers_and_the_sentinel():
    drawn = a_project()
    document, _count, _layers = to_app.project_to_document(drawn)
    jsx = app.jsx_document(document, report='C:/tmp/r.txt', done='C:/tmp/s.done')
    assert 'contour' in jsx and 'detail' in jsx
    # **The sentinel path is the one thing that has to match the waiting side exactly.** If the script writes its report
    # somewhere else than the path `run_jsx` was given, the wait runs to the timeout and reports a failure that is
    # really a disagreement between two string literals.
    assert 'C:/tmp/s.done' in jsx or 'C:\\tmp\\s.done' in jsx or 's.done' in jsx


def test_the_layer_argument_is_only_a_default():
    drawn = project.Project(width=200, height=150)
    mark = drawn.add_stroke(core.stroke_record([(20, 20), (180, 120)], 'ink', seed=3), stage='line', note='n')
    document, count, layers = to_app.project_to_document(drawn, layer='INK')
    assert count == 1
    assert layers == {'INK'}, 'a mark with no layer of its own takes the default'
    assert len(document.layers) == 1
