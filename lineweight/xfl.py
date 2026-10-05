"""Handing a drawing to Animate, through the one door it actually opens.

**Why this file exists at all.** Animate is the hardest of the three destinations, and the difficulty is not in the
drawing -- it is that Animate offers no way in. Measured on this machine, all of these fail:

* `Animate.exe script.jsfl` opens the script as a **document** rather than running it.
* `FlashFactory.FlashFactory` is registered in the registry and refuses to be created from another process
  (`Automation server can't create object`).
* A JSFL placed in the user's `Configuration/Commands` does **not** run when a document opens, nor at startup.
* Animate's window exposes an **empty UI Automation tree** (`descendants=0`), so its menus cannot be driven as
  controls, and `SetForegroundWindow` from a background process does not take focus -- so keystrokes do not reach it
  either. A hand-driven menu is not automation.

What does work is a **file**: `Animate.exe drawing.xfl` opens a hand-written XFL and shows it as a document, which
was confirmed by watching the window title become the file's name. So the drawing is written as XFL -- Animate's own
uncompressed project format, a folder of XML -- and Animate opens it. No click, no script, no version-specific API.

**The skeleton is the part that has to be exactly right**, and getting it wrong produces Animate's most misleading
error: `unable to import scene contents, the document may be corrupt`, with an empty stage. That message appeared for
a document containing **no shapes at all**, which is how the fault was located in the skeleton rather than in the
geometry. Two details came out of Animate's own binaries rather than from documentation: the exporter names its
property `xflversion2_1`, so **2.1** is the version this build writes -- declaring a higher one is refused with
`Can't read a newer version of XFL` -- and an unrecognised element is reported as `Unknown XFL tag`.
"""
from __future__ import annotations

import os
import zipfile

from .doc import Document, Path, parse_colour

XFL_NAMESPACE = 'http://ns.adobe.com/xfl/2008/'
XFL_VERSION = '2.1'
MIMETYPE = 'application/vnd.adobe.xfl'

# Layer colours Animate uses for new layers, cycled so a generated document is readable in its timeline.
LAYER_COLOURS = ['#4FFF4F', '#4F4FFF', '#FF4F4F', '#FFFF4F', '#FF4FFF', '#4FFFFF']


def _num(value: float) -> str:
    return ('%.4f' % float(value)).rstrip('0').rstrip('.') or '0'


def _hex(rgb: tuple[int, int, int]) -> str:
    return '#%02X%02X%02X' % rgb


def edge_xml(start: tuple[float, float], end: tuple[float, float],
             control: tuple[float, float] | None = None) -> str:
    """One edge of a shape.

    Animate does not describe a shape as a polygon. It describes a **chain of quadratic segments**, each carrying an
    anchor, a control point and the next anchor, so a straight side is a quadratic whose control point lies on the
    line. Writing a list of vertices as if it were a polygon is the obvious thing to do and produces a shape Animate
    silently refuses to import.
    """
    cx, cy = control if control else start
    return ('            <Edge cubics="%s %s %s %s %s %s"/>\n'
            % (_num(start[0]), _num(start[1]), _num(cx), _num(cy), _num(end[0]), _num(end[1])))


def contour_edges(points: list[tuple[float, float]]) -> str:
    """A closed contour as quadratics, which is what a filled outline is once it reaches Animate."""
    out = []
    count = len(points)
    for i in range(count):
        out.append(edge_xml(points[i], points[(i + 1) % count]))
    return ''.join(out)


def shape_xml(path: Path, indent: str = '        ') -> str:
    """A `DOMShape`: the fill styles, then the edges.

    A filled outline carries its colour here rather than being stroked, because by the time a drawing reaches this
    writer the weight is already geometry -- that is the whole point of expanding a stroke before exporting it, since
    Animate has no variable-width stroke to carry it.
    """
    r, g, b = parse_colour(path.appearance.fill)
    lines = [indent + '<DOMShape isDrawingObject="true">',
             indent + '  <matrix>',
             indent + '    <Matrix a="1" b="0" c="0" d="1" tx="0" ty="0"/>',
             indent + '  </matrix>']
    if path.appearance.filled:
        lines += [indent + '  <fills>',
                  indent + '    <FillStyle index="1">',
                  indent + '      <SolidColor color="%s" alpha="%s"/>' % (_hex((r, g, b)), _num(path.appearance.opacity)),
                  indent + '    </FillStyle>',
                  indent + '  </fills>']
    if not path.appearance.filled:
        sr, sg, sb = parse_colour(path.appearance.stroke or path.appearance.fill)
        lines += [indent + '  <strokes>',
                  indent + '    <StrokeStyle index="1">',
                  indent + '      <SolidStroke weight="%s" scaleMode="normal">' % _num(path.appearance.stroke_width),
                  indent + '        <fill>',
                  indent + '          <SolidColor color="%s" alpha="%s"/>' % (_hex((sr, sg, sb)), _num(path.appearance.opacity)),
                  indent + '        </fill>',
                  indent + '      </SolidStroke>',
                  indent + '    </StrokeStyle>',
                  indent + '  </strokes>']
    lines.append(indent + '  <edges>')
    lines.append(contour_edges(path.points))
    lines.append(indent + '  </edges>')
    lines.append(indent + '</DOMShape>')
    return '\n'.join(lines) + '\n'


def dom_document(document: Document) -> str:
    """The whole drawing as `DOMDocument.xml`, Animate's main scene."""
    layers: list[str] = []
    for i, layer in enumerate(document.layers):
        if not layer.paths:
            continue
        shapes = ''.join(shape_xml(path, '                ') for path in layer.paths)
        layers.append(
            '      <DOMLayer name="%s" color="%s" current="%s" isSelected="%s">\n'
            '        <frames>\n'
            '          <DOMFrame index="0" keyMode="9728" duration="1">\n'
            '            <elements>\n'
            '%s'
            '            </elements>\n'
            '          </DOMFrame>\n'
            '        </frames>\n'
            '      </DOMLayer>\n'
            % (layer.name, LAYER_COLOURS[i % len(LAYER_COLOURS)],
               'true' if i == 0 else 'false', 'true' if i == 0 else 'false', shapes))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DOMDocument xmlns="%s" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'width="%s" height="%s" xflVersion="%s" versionInfo="lineweight" creatorInfo="lineweight">\n'
        '  <folders/>\n'
        '  <timelines>\n'
        '    <DOMTimeline name="Scene 1">\n'
        '      <layers>\n'
        '%s'
        '      </layers>\n'
        '    </DOMTimeline>\n'
        '  </timelines>\n'
        '</DOMDocument>\n'
        % (XFL_NAMESPACE, _num(document.width), _num(document.height), XFL_VERSION, ''.join(layers))
    )


def write_xfl(document: Document, path: str | os.PathLike) -> str:
    """Write the drawing as an XFL **folder**, which is the uncompressed form Animate opens directly.

    A folder rather than a zip because it is inspectable: when Animate refuses a generated document, the XML that
    caused the refusal is right there to read. Zipping it is a packaging step, not part of getting the drawing in.
    """
    target = str(path)
    os.makedirs(os.path.join(target, 'LIBRARY'), exist_ok=True)
    with open(os.path.join(target, 'mimetype'), 'w', encoding='ascii', newline='\n') as handle:
        handle.write(MIMETYPE)
    with open(os.path.join(target, 'DOMDocument.xml'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(dom_document(document))
    return target


def zip_xfl(folder: str | os.PathLike, archive: str | os.PathLike) -> str:
    """The folder as a `.xfl` file, which is what the format usually is: a zip with the mimetype stored first."""
    folder = str(folder)
    archive = str(archive)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(folder, 'mimetype'), 'mimetype')
        for root, _dirs, files in os.walk(folder):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, folder).replace('\\', '/')
                if rel == 'mimetype':
                    continue
                z.write(full, rel)
    return archive
