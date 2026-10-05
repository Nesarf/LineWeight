"""Handing a drawing to a drawing application.

**What this file is for.** The library can already produce plain SVG, and plain SVG is the right output when the
destination is a browser or a repository. It is the wrong output when the destination is Illustrator, because SVG
throws away the things that make a document workable: which layer a shape is on, whether it is a filled outline or a
stroked centre line, and how opaque it is -- all of which survive only if somebody re-derives them by parsing.

So the drawing is written as a **script for the application** instead, and the application rebuilds it natively:
real layers, real path objects, real fill and opacity. Nothing is lost to a format's limits, because no format is
crossed. This is the honest version of "automation" -- the application is not driven, it is handed a drawing.

**Verified against Illustrator 28.5, not inferred.** Three things here were measured and are not guesses:

* `ExportType.SVG` is the working constant. `ExportType.SVGFORMAT` does not exist in 28.5 and fails with the
  unhelpful `Invalid enumeration value` -- with no line number, which is why it is written down here.
* A closed filled outline arrives intact: a 64-point variable-width contour exports back out as a single
  `<polygon>` with its `opacity` preserved to the decimal. Variable width survives because it is geometry.
* Illustrator's y axis points **up** and SVG's points **down**, so every y is flipped once, here, against the
  document height. A script that forgets this draws the picture upside down and looks plausible in the code.

**Animate is a different situation and is not pretended otherwise.** `Animate.exe script.jsfl` opens the file as a
document rather than running it; `FlashFactory.FlashFactory` is registered but refuses to be created out of process;
and a JSFL placed in `Configuration/Commands` does **not** run when a document opens. Animate therefore receives SVG
and imports it, which puts weight on the Animate SVG importer rather than on a bridge that does not exist.

**SAI has no scripting interface at all.** It reads layered PSD and PNG, so that is the door, written elsewhere.
"""
from __future__ import annotations

import json

from .doc import Document, Path, parse_colour

# Sizes are in points and Illustrator's canvas starts at the bottom-left, so a document built from an SVG-sized
# drawing is positioned by flipping y about the document height. One flip, in `jsx_document`.
DEFAULT_EXPORT_CONSTANT = 'ExportType.SVG'


def _num(value: float) -> str:
    """ExtendScript numbers. Six decimals is far below a pixel and keeps the generated file readable."""
    return ('%.6f' % float(value)).rstrip('0').rstrip('.') or '0'


def _points(path: Path, height: float) -> str:
    """The path's points as an ExtendScript array literal, with y flipped.

    `setEntirePath` takes an array of `[x, y]` pairs and is the only efficient way to build a path: adding points one
    at a time works too, but it is one round trip per point and it is what a 300-point contour cannot afford.
    """
    parts = []
    for x, y in path.points:
        parts.append('[%s,%s]' % (_num(x), _num(height - y)))
    return '[' + ','.join(parts) + ']'


def _appearance_lines(path: Path, indent: str) -> list[str]:
    """Fill, stroke and opacity as ExtendScript assignments.

    Opacity is a percentage in the scripting model and a fraction everywhere else in this library, and the conversion
    lives here rather than in the model because it is an application's convention, not a fact about the drawing.
    """
    lines: list[str] = []
    if path.appearance.filled:
        r, g, b = parse_colour(path.appearance.fill)
        lines.append('%sitem.filled = true; item.stroked = false;' % indent)
        lines.append('%scolour = new RGBColor(); colour.red = %d; colour.green = %d; colour.blue = %d;'
                     % (indent, r, g, b))
        lines.append('%sitem.fillColor = colour;' % indent)
    else:
        stroke = path.appearance.stroke or path.appearance.fill
        r, g, b = parse_colour(stroke)
        lines.append('%sitem.filled = false; item.stroked = true;' % indent)
        lines.append('%scolour = new RGBColor(); colour.red = %d; colour.green = %d; colour.blue = %d;'
                     % (indent, r, g, b))
        lines.append('%sitem.strokeColor = colour;' % indent)
        lines.append('%sitem.strokeWidth = %s;' % (indent, _num(path.appearance.stroke_width)))
    lines.append('%sitem.opacity = %s;' % (indent, _num(path.appearance.opacity * 100.0)))
    if path.closed:
        lines.append('%sitem.closed = true;' % indent)
    if not path.appearance.filled:
        # An open stroked path must not be closed by Illustrator's default for a 2-point path.
        lines.append('%sitem.filled = false;' % indent)
    return lines


def jsx_layer(layer_name: str) -> str:
    """A get-or-create for a layer, emitted as a helper so a document can address layers by name."""
    return (
        'function lwLayer(doc, name) {\n'
        '  for (var i = 0; i < doc.layers.length; i++) { if (doc.layers[i].name === name) return doc.layers[i]; }\n'
        '  var made = doc.layers.add(); made.name = name; return made;\n'
        '}\n'
    )


def jsx_document(document: Document, export_svg: str | None = None, export_ai: str | None = None,
                 report: str | None = None, done: str | None = None) -> str:
    """The whole drawing as one ExtendScript, ready to be run by Illustrator.

    A report file and a completion sentinel are written at the end. The sentinel is what makes the run checkable from
    outside: a script that fails halfway leaves no sentinel, so "it produced no error" is never mistaken for "it
    finished", which is the failure mode this library has been bitten by before.
    """
    height = document.height
    out: list[str] = []
    out.append('// generated by lineweight -- do not edit; edit the drawing and generate again')
    out.append('// destination: Adobe Illustrator (verified against 28.5 / ExtendScript 4.5.6)')
    out.append('')
    out.append(jsx_layer(''))
    lines: list[str] = []
    if report:
        lines.append('var lwReport = new File(%s);' % json.dumps(report.replace('\\', '/')))
        lines.append('lwReport.encoding = "UTF-8"; lwReport.open("w");')
        lines.append('function lwSay(s) { lwReport.writeln(s); }')
    else:
        lines.append('function lwSay(s) {}')
    lines.append('try {')
    lines.append('  lwSay("app=" + app.name + " " + app.version);')
    lines.append('  var doc = app.documents.add();')
    lines.append('  var colour;')
    lines.append('  var item;')
    written = 0
    for layer in document.layers:
        if not layer.visible or not layer.paths:
            continue
        lines.append('  // ---- layer %s (%d paths)' % (json.dumps(layer.name), len(layer.paths)))
        lines.append('  var lay = lwLayer(doc, %s);' % json.dumps(layer.name))
        lines.append('  lay.visible = %s; lay.locked = %s;'
                     % ('true' if layer.visible else 'false', 'true' if layer.locked else 'false'))
        for path in layer.paths:
            lines.append('  item = lay.pathItems.add();')
            lines.append('  item.setEntirePath(%s);' % _points(path, height))
            lines.extend(_appearance_lines(path, '  '))
            written += 1
        lines.append('')
    lines.append('  lwSay("layers=" + doc.layers.length + " paths=%d");' % written)
    if export_svg:
        lines.append('  var svgOpts = new ExportOptionsSVG();')
        lines.append('  svgOpts.coordinatePrecision = 3;')
        lines.append('  svgOpts.embedRasterImages = false;')
        lines.append('  // ExportType.SVG, not ExportType.SVGFORMAT: the latter does not exist in 28.5')
        lines.append('  doc.exportFile(new File(%s), %s, svgOpts);'
                     % (json.dumps(export_svg.replace('\\', '/')), DEFAULT_EXPORT_CONSTANT))
        lines.append('  lwSay("svg=" + %s);' % json.dumps(export_svg.replace('\\', '/')))
    if export_ai:
        lines.append('  doc.saveAs(new File(%s));' % json.dumps(export_ai.replace('\\', '/')))
        lines.append('  lwSay("ai=" + %s);' % json.dumps(export_ai.replace('\\', '/')))
    lines.append('  doc.close(SaveOptions.DONOTSAVECHANGES);')
    lines.append('  lwSay("ALL_OK");')
    lines.append('} catch (e) { lwSay("error=" + e.message + " line=" + e.line); }')
    if report:
        lines.append('lwReport.close();')
    if done:
        lines.append('var lwDone = new File(%s);' % json.dumps(done.replace('\\', '/')))
        lines.append('lwDone.open("w"); lwDone.writeln("done"); lwDone.close();')
    out.extend(lines)
    out.append('')
    return '\n'.join(out)
