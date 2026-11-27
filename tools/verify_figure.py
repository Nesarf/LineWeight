"""Read back what `paint_figure.py` wrote, with parsers that owe this library nothing.

The figure has three exits: a PNG, a layered PSD, and the project file. Each of the three can be wrong in a way the
other two do not show -- a PSD whose layer order is right and whose pixels are empty reads as fine from the document
side, and a project file with the right marks says nothing about whether the renderer put them anywhere.

So the two machine-readable exits are opened here by code that was not written by this project: `psd-tools` for the
PSD, `json` for the glTF. When `psd-tools` is absent the PSD side reports itself unchecked rather than passing, which
is the distinction `tests/tools/verify_all.py` already argues for -- a check that silently degrades into a shrug is
worse than no check, because it still prints a line.

This file was rescued from `cache/tmp` after the move from `E:` to `D:`; only the paths changed.

    python tools/verify_figure.py [folder]        default: ./figure
"""
import json
import os
import sys

FOLDER = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), 'figure')
PSD_PATH = os.path.join(FOLDER, 'figure.psd')
GLTF_PATH = os.path.join(FOLDER, 'figure.gltf')


def check_psd() -> None:
    if not os.path.exists(PSD_PATH):
        print('psd   missing: %s' % PSD_PATH)
        return
    try:
        from psd_tools import PSDImage
    except ImportError:
        print('psd   UNCHECKED: psd-tools is not installed, so no parser outside this project has read it')
        return
    psd = PSDImage.open(PSD_PATH)
    names = [layer.name for layer in psd]
    print('psd   %d layers' % len(names))
    for name in names:
        print('        %s' % name)
    layer = psd[1] if len(psd) > 1 else psd[0]
    box = (layer.bbox[2] - layer.bbox[0], layer.bbox[3] - layer.bbox[1])
    print('      layer 1 size %s  opacity %s  visible %s' % (box, layer.opacity, layer.visible))


def check_gltf() -> None:
    if not os.path.exists(GLTF_PATH):
        print('gltf  missing: %s' % GLTF_PATH)
        return
    with open(GLTF_PATH, encoding='utf-8') as handle:
        doc = json.load(handle)
    print('gltf  asset %r  generator %r'
          % (doc['asset'].get('version'), doc['asset'].get('generator')))
    print('      nodes %d  %s' % (len(doc.get('nodes', [])), [n.get('name') for n in doc.get('nodes', [])]))
    print('      meshes %d      materials %d      buffers %d embedded %s'
          % (len(doc.get('meshes', [])), len(doc.get('materials', [])), len(doc.get('buffers', [])),
             all(str(b.get('uri', '')).startswith('data:') for b in doc.get('buffers', []))))


def main() -> int:
    print('reading %s' % FOLDER)
    check_psd()
    check_gltf()
    return 0


if __name__ == '__main__':
    sys.exit(main())
