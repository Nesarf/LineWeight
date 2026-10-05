"""Handing a drawing to Animate, through the one door it actually opens.

**Why this file exists at all.** Animate is the hardest of the three destinations, and the difficulty is not in the
drawing -- it is that Animate offers no way in. Measured on this machine, all of these fail:

* `Animate.exe script.jsfl` opens the script as a **document** rather than running it.
* `FlashFactory.FlashFactory` is registered in the registry and refuses to be created from another process.
* A JSFL placed in `Configuration/Commands` does **not** run when a document opens. Tried with no document open and
  with one, because the first attempt proved nothing about the second.
* Animate's window exposes an **empty UI Automation tree**, so its menus cannot be driven, and a background process
  cannot take its focus, so keystrokes do not reach it either.
* `Animate.exe drawing.svg` opens the **home screen**, not the file.
* After Effects 2024 ships no XFL exporter, and Illustrator's scripting dictionary has no XFL.

What does work is a file: `Animate.exe drawing.xfl` opens a hand-written XFL as a document, confirmed by watching the
window title become the file's name. So the drawing is written as XFL -- Animate's own uncompressed project format.

**Everything below the shape encoding was wrong until a reference existed.** Nine hand-written skeletons opened as
documents and none of them imported a scene: the timeline stayed empty and the status bar read "unable to import
scene contents, the document may be corrupt". The message was accurate and unhelpful, and an orthogonal sweep of
sixteen combinations (frame shape crossed with version attribute) found only that `xflVersion` is required for the
file to open at all -- which is not the same as importing.

An XFL saved by Animate itself settled it in one reading. What the reference has that a hand-written file does not:

* the document is a **folder** whose name matches a marker file inside it, `drawing.xfl` containing the text
  `PROXY-CS5`, alongside `LIBRARY/`, `META-INF/`, `bin/` and `publishtemplates/`;
* `xflVersion="23.0"`, not a number inferred from a string in the binary;
* `creatorInfo="Adobe Animate"`, `platform="Windows"`, `majorVersion`, `buildNumber`, `nextSceneIdentifier`,
  `frameRate`, `currentTimeline`, `filetypeGUID` and `fileGUID` on the root;
* `<scripts/>`, `<PrinterSettings/>` and `<publishHistory/>` as root children;
* `layerDepthEnabled="true"` on the timeline, and a frame written as `<DOMFrame index="0" keyMode="9728">` with
  `<elements/>` inside and **no `duration` attribute**.

The lesson is worth keeping: a format guessed at from one third-party example and a few strings in a binary is a
format guessed at. The one artifact that ends the guessing is the application's own output, and it had to come from a
person because the application cannot be asked for it programmatically.
"""
from __future__ import annotations

import os

from .doc import Document, Path, parse_colour

XFL_NAMESPACE = 'http://ns.adobe.com/xfl/2008/'
# Read off a document Animate 2024 saved itself. The earlier value was inferred from a property name found in the
# binary and was wrong in a way that produced no error message at all -- the file opened and imported nothing.
XFL_VERSION = '23.0'
ANIMATE_CREATOR = 'Adobe Animate'
ANIMATE_VERSION_INFO = 'Saved by Animate Windows 24.0 build 19'
MAJOR_VERSION = '24'
BUILD_NUMBER = '19'
MARKER_FILE_TEXT = 'PROXY-CS5'
MIMETYPE = 'application/vnd.adobe.xfl'

# Layer colours Animate uses for new layers, cycled so a generated document is readable in its timeline.
LAYER_COLOURS = ['#00FFFF', '#4FFF4F', '#4F4FFF', '#FF4F4F', '#FFFF4F', '#FF4FFF']


def _num(value: float) -> str:
    return ('%.4f' % float(value)).rstrip('0').rstrip('.') or '0'


def _hex(rgb: tuple[int, int, int]) -> str:
    return '#%02X%02X%02X' % rgb


def encode_edges(points: list[tuple[float, float]]) -> str:
    """A closed contour in the compact notation that the `edges` attribute actually holds.

    **This is the representation a shape is drawn from**, and writing only the verbose `cubics` form produces a shape
    that opens, imports, and draws nothing -- which is exactly what nine hand-written skeletons did. Animate writes
    both; the compact one is short and the verbose one spells the same path out.

    Read off fifty shapes in Animate's own template documents: `!x y` moves, `|x y` draws a line, `[cx cy x y` draws a
    quadratic, and each anchor is followed by either a line or a curve to the *next* anchor. Animate's writer emits
    whole numbers throughout, so these are rounded -- a coordinate the format is never fed in practice is a coordinate
    whose reader has never been exercised.
    """
    if len(points) < 2:
        return ''
    out = ['!%d %d' % (round(points[0][0]), round(points[0][1]))]
    body = list(points[1:])
    if points[0] != points[-1]:
        body.append(points[0])
    for x, y in body:
        out.append('|%d %d' % (round(x), round(y)))
    return ''.join(out)


def cubics_for(points: list[tuple[float, float]]) -> str:
    """The same contour as the verbose `cubics` form: six numbers per edge, control point on the line.

    Redundant with `encode_edges`, and emitted anyway because Animate emits both. A reader that trusts one of the two
    finds the other consistent; a writer that omits one has written half a shape.
    """
    parts = []
    count = len(points)
    for i in range(count):
        a = points[i]
        b = points[(i + 1) % count]
        parts.append('<Edge cubics="%s %s %s %s %s %s"/>'
                     % (_num(a[0]), _num(a[1]), _num(a[0]), _num(a[1]), _num(b[0]), _num(b[1])))
    return '\n'.join(parts)


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
    # **Both representations, in the order Animate writes them.** The compact `edges` attribute is what the shape is
    # drawn from; the `cubics` elements spell the same path out. Emitting only the second is what produced shapes that
    # opened and drew nothing.
    lines.append('%s       <Edge fillStyle1="1" edges="%s"/>' % (indent, encode_edges(path.points)))
    lines.append(cubics_for(path.points))
    lines.append(indent + '  </edges>')
    lines.append(indent + '</DOMShape>')
    return '\n'.join(lines) + '\n'


def dom_document(document: Document, guid: str = '') -> str:
    """The whole drawing as `DOMDocument.xml`, Animate's main scene.

    The root attributes and the three trailing empty elements are not decoration: they are what a document Animate
    saved itself contains, and the version that omitted them opened as a document while importing nothing. A file can
    be well-formed, accepted, and still empty, which is the failure this whole module was built around.
    """
    layers: list[str] = []
    for i, layer in enumerate(document.layers):
        if not layer.paths:
            continue
        shapes = ''.join(shape_xml(path, '                          ') for path in layer.paths)
        layers.append(
            '          <DOMLayer name="%s" color="%s" current="%s" isSelected="%s">\n'
            '               <frames>\n'
            '                    <DOMFrame index="0" keyMode="9728">\n'
            '                         <elements>\n'
            '%s'
            '                         </elements>\n'
            '                    </DOMFrame>\n'
            '               </frames>\n'
            '          </DOMLayer>\n'
            % (layer.name, LAYER_COLOURS[i % len(LAYER_COLOURS)],
               'true' if i == 0 else 'false', 'true' if i == 0 else 'false', shapes))
    file_guid = guid or _guid()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DOMDocument xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="%s" '
        'width="%s" height="%s" frameRate="60" currentTimeline="1" xflVersion="%s" '
        'creatorInfo="%s" platform="Windows" versionInfo="%s" majorVersion="%s" buildNumber="%s" '
        'nextSceneIdentifier="2" playOptionsPlayLoop="false" playOptionsPlayPages="false" '
        'playOptionsPlayFrameActions="false" filetypeGUID="DD0DDBBF-5BEF-45B2-9F24-A3048D2A676F" '
        'fileGUID="%s">\n'
        '     <timelines>\n'
        '          <DOMTimeline name="Scene 1" layerDepthEnabled="true">\n'
        '               <layers>\n'
        '%s'
        '               </layers>\n'
        '          </DOMTimeline>\n'
        '     </timelines>\n'
        '     <scripts/>\n'
        '     <PrinterSettings/>\n'
        '     <publishHistory/>\n'
        '</DOMDocument>\n'
        % (XFL_NAMESPACE, _num(document.width), _num(document.height), XFL_VERSION, ANIMATE_CREATOR,
           ANIMATE_VERSION_INFO, MAJOR_VERSION, BUILD_NUMBER, file_guid, ''.join(layers))
    )


def _guid() -> str:
    """A 32-hex-digit identifier, which is the shape `fileGUID` has in a saved document."""
    import uuid
    return uuid.uuid4().hex.upper()


def write_xfl(document: Document, path: str | os.PathLike) -> str:
    """Write the drawing as an XFL **folder**, which is what Animate opens and what Animate itself saves.

    **The folder needs its own furniture, and without it the scene does not import.** A document saved by Animate is a
    directory holding `DOMDocument.xml` next to a marker file named after the project and containing `PROXY-CS5`, plus
    `LIBRARY/`, `META-INF/`, `bin/` and `publishtemplates/`. Nine hand-written skeletons that had only the XML opened
    as documents and imported nothing; this is the shape that works.

    A folder rather than a zip because it is inspectable: when Animate refuses a generated document, the XML that
    caused the refusal is right there to read.
    """
    target = str(path)
    name = os.path.basename(target.rstrip('/\\'))
    # the folder is usually named `drawing.xfl` and the marker inside it `drawing.xfl`, so a name that already ends in
    # the extension must not have it doubled -- `drawing.xfl.xfl` is what that looks like when it goes wrong
    marker_name = name if name.lower().endswith('.xfl') else name + '.xfl'
    os.makedirs(os.path.join(target, 'LIBRARY'), exist_ok=True)
    os.makedirs(os.path.join(target, 'META-INF'), exist_ok=True)
    os.makedirs(os.path.join(target, 'bin'), exist_ok=True)
    os.makedirs(os.path.join(target, 'publishtemplates'), exist_ok=True)
    # the marker file is named after the project and says what kind of proxy this is
    with open(os.path.join(target, marker_name), 'w', encoding='ascii', newline='\n') as handle:
        handle.write(MARKER_FILE_TEXT)
    with open(os.path.join(target, 'mimetype'), 'w', encoding='ascii', newline='\n') as handle:
        handle.write(MIMETYPE)
    with open(os.path.join(target, 'DOMDocument.xml'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(dom_document(document))
    # empty files Animate also writes; absent, they are the difference between a folder it recognises and one it does not
    with open(os.path.join(target, 'META-INF', 'metadata.xml'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('')
    with open(os.path.join(target, 'MobileSettings.xml'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('')
    # a symbol-dependency cache: a one-byte version marker followed by an empty table
    with open(os.path.join(target, 'bin', 'SymDepend.cache'), 'wb') as handle:
        handle.write(bytes([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))
    return target


def zip_xfl(folder: str | os.PathLike, archive: str | os.PathLike) -> str:
    """Not used by the Animate path, and kept only for packaging an XFL to hand to something else.

    `Animate.exe` opens the folder directly, so this is not part of getting a drawing in -- and it is worth saying so,
    because zipping was tried extensively before the folder was understood and every zip opened as a document that
    imported nothing.
    """
    import zipfile
    folder = str(folder)
    archive = str(archive)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, folder).replace('\\', '/')
                z.write(full, rel)
    return archive
