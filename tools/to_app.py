"""Hand a finished drawing to a drawing application, and prove the application built it.

**Why the application and not SVG.** The library can already write plain SVG, and that is the right output for a browser
or a repository. It is the wrong output for Illustrator, because SVG throws away the things that make a document workable:
which layer a shape is on, whether it is a filled outline or a stroked centre line, how opaque it is. The JSX route makes
the application rebuild those natively -- real layers, real path objects -- instead of asking somebody downstream to parse
them back out of a format that flattened them.

**Why the completion sentinel.** A drawing application opens a window, runs the script and then sits there, so "the process
started" says nothing about whether the drawing was built. The generated script writes a sentinel as its last act, and
`run_jsx` waits for that rather than for the process: a script that throws halfway writes no sentinel and the failure comes
back as a timeout with the report beside it.

**The one step that is not automation.** Illustrator guards against a script arriving from outside itself, and that guard
is a dialog a person clicks. So this bridge is not unattended: a run with nobody at the screen ends in a timeout, and the
output says so rather than blaming the drawing. What the bridge does guarantee is that the application's own report comes
back -- measured once: `app=Adobe Illustrator 28.5.0, layers=2 paths=3926, ALL_OK`, 103.8 seconds after the launch, with
the path count equal to the number of marks handed over.

**Default is to write the script and stop.** Launching an application opens a window on somebody's desktop, so `--run` is
the flag that does it and the run is a decision rather than a side effect of asking where a file is.

    python tools/to_app.py --project cache/paint14/picture.json --out cache/from-app/picture.jsx
    python tools/to_app.py --project ... --out ... --run --timeout 240
"""

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lineweight import app, core, doc, project as project_module, run   # noqa: E402

DEFAULT_LAYER = 'LINE'


def project_to_document(drawn: project_module.Project, layer: str = DEFAULT_LAYER) -> tuple[doc.Document, int, set]:
    """The drawing as a layered document, plus how many marks went in and which layers they landed on.

    **A stroke's outline is rebuilt from its geometry, not copied from anywhere.** `core.outline_polygon` takes the same
    centre line and width profile the renderer uses, so what the application receives is the same shape that was drawn --
    one construction, two destinations.

    **Drafts are skipped**, for the same reason `render_marks` skips them: a draft is a candidate, and handing a candidate
    to an application turns "I am still deciding" into "this is in the document".
    """
    strokes = []
    for mark in drawn.marks:
        if mark.kind != 'stroke' or mark.state != project_module.LIVE:
            continue
        outline = core.outline_polygon(dict(mark.geometry))
        if len(outline) < 3:
            continue
        colour = mark.appearance.get('colour') or '#1A1620'
        strokes.append({'outline': outline, 'colour': colour,
                        'layer': mark.layer or layer, 'name': mark.id})
    document = doc.from_strokes(strokes, drawn.width, drawn.height, layer)
    used = {item['layer'] for item in strokes}
    return document, len(strokes), used


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True, help='a version 2 project file')
    ap.add_argument('--out', required=True, help='where to write the JSX script')
    ap.add_argument('--layer', default=DEFAULT_LAYER, help='the layer a mark with no layer of its own goes on')
    ap.add_argument('--export-ai', default='', help='ask the application to save an .ai file at this path')
    ap.add_argument('--run', action='store_true', help='actually open the application and run the script')
    ap.add_argument('--timeout', type=float, default=180.0, help='seconds to wait for the sentinel')
    ap.add_argument('--keep-open', action='store_true', help='do not close the application afterwards')
    args = ap.parse_args()

    drawn = project_module.load_project(args.project)
    document, count, layers = project_to_document(drawn, args.layer)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    script = out.with_suffix('.jsx')
    report = out.with_suffix('.report.txt')
    sentinel = out.with_suffix('.done')

    jsx = app.jsx_document(document, export_ai=(args.export_ai or None),
                           report=str(report), done=str(sentinel))
    script.write_text(jsx, encoding='utf-8')
    print('  %d strokes on %d layer%s -> %s (%d KB)'
          % (count, len(layers) or 1, '' if len(layers) == 1 else 's', script, len(jsx) // 1024))
    if layers:
        print('  layers: %s' % ', '.join(sorted(layers)))

    if not args.run:
        print('  not run. --run opens %s and waits for %s' % (run.illustrator_path() or 'the application', sentinel.name))
        return 0

    app_path = run.illustrator_path()
    if not app_path:
        print('  no Illustrator found; the script is written and can be run by hand')
        return 2
    print('  handing it to %s' % app_path)
    # **The one step that is not automation, and it belongs in the output rather than in a document nobody reads.**
    # Illustrator guards against a script arriving from outside the application, and the guard is a dialog somebody has to
    # click. The run below waits for the sentinel, so that click is not a hang -- but a run with nobody in front of the
    # screen does end in a timeout, and a timeout that says "the script never finished" would be blaming the drawing for a
    # security prompt. Measured once on this machine: the window appeared, a person clicked through it, and the report
    # arrived 103.8 seconds after the launch with all 3926 paths counted.
    print('  if Illustrator asks whether to allow this script, that dialog is the run: click through it.')
    result = run.run_jsx(jsx, script, str(report), str(sentinel), app_path=app_path,
                         timeout=args.timeout, close_when_done=not args.keep_open)
    print('  %s' % result.describe())
    if not result.ok and not result.sentinel_seen and result.spawned:
        print('  no sentinel, and the application is running: the likely cause is the script-security dialog,')
        print('  not a failure in the drawing. The report file says whatever the script got as far as.')
    if not result.ok and result.report:
        print('  report tail:')
        for line in result.report.splitlines()[-8:]:
            print('    %s' % line)
    for artifact in result.artifacts:
        print('  artifact %s' % artifact)
    return 0 if result.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
