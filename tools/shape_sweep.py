"""Try the colour-shape cut at several settings and show the fills beside the reference.

**The tuning needs its own loop.** Every setting used to be judged by rendering the whole picture -- four thousand strokes
plus the fills, half a minute a run -- when the only thing being tuned is where the colour boundaries fall. So this cuts
and renders the fills alone at the reference's own size, which is a second a run, and pastes the crops side by side.
"""
import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent


def mini_project(reference, out):
    """A project the size of the reference with no marks, so the cut is made where the reference actually has pixels."""
    image = Image.open(reference)
    doc = {
        'version': 2,
        'canvas': {'width': image.size[0], 'height': image.size[1]},
        'title': 'fills only',
        'stages': [],
        'log': [],
        'counter': 0,
        'incremental': False,
        'turn': 0,
        'figure': None,
        'marks': [],
    }
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    return out


def render_fills(src, out):
    doc = json.loads(pathlib.Path(src).read_text(encoding='utf-8'))
    doc['marks'] = [m for m in doc.get('marks', []) if m.get('kind') == 'fill']
    project = pathlib.Path(out).with_suffix('.json')
    project.write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    png = pathlib.Path(out).with_suffix('.png')
    proc = subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(project), '--out', str(png)],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print(proc.stderr[-300:])
        raise SystemExit('render failed')
    return png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--settings', required=True,
                    help='semicolon separated levels,blur,min-area triples, e.g. "10,2,400;14,1,150"')
    ap.add_argument('--crop', default='0.28,0.04,0.54,0.24', help='x0,y0,x1,y1 as fractions of the reference')
    ap.add_argument('--zoom', type=int, default=2)
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    project = mini_project(args.reference, out / 'mini.json')
    reference = Image.open(args.reference).convert('RGB')
    x0, y0, x1, y1 = (float(v) for v in args.crop.split(','))
    box = (int(x0 * reference.size[0]), int(y0 * reference.size[1]),
           int(x1 * reference.size[0]), int(y1 * reference.size[1]))
    tiles = [('reference', reference.crop(box))]

    for setting in args.settings.split(';'):
        levels, blur, area = (float(v) for v in setting.split(','))
        shapes = out / ('shapes-%g-%g-%d.json' % (levels, blur, area))
        proc = subprocess.run([sys.executable, str(HERE / 'shape_pass.py'), '--project', str(project),
                               '--reference', args.reference, '--out', str(shapes),
                               '--levels', str(int(levels)), '--blur', str(blur), '--min-area', str(int(area))],
                              capture_output=True, text=True, cwd=str(ROOT))
        head = [l.strip() for l in (proc.stdout or '').splitlines() if l.strip()]
        if proc.returncode != 0:
            print('%s failed: %s' % (setting, (proc.stderr or '').strip().splitlines()[-1:]))
            continue
        png = render_fills(shapes, out / ('fills-%g-%g-%d' % (levels, blur, area)))
        image = Image.open(png).convert('RGB').crop(box)
        if args.zoom != 1:
            image = image.resize((image.size[0] * args.zoom, image.size[1] * args.zoom), Image.LANCZOS)
        tiles.append((setting, image))
        print('  %-12s %s' % (setting, head[0] if head else ''))

    pad = 8
    width = sum(t.size[0] for _, t in tiles) + pad * (len(tiles) - 1)
    height = max(t.size[1] for _, t in tiles)
    sheet = Image.new('RGB', (width, height), (250, 250, 250))
    x = 0
    for name, tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.size[0] + pad
    target = out / 'sheet.png'
    sheet.save(target)
    print('  wrote %s' % target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
