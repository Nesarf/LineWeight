"""Read the part vocabulary out of the artist's own PSD working files.

**Why the working files and not a fitted segmenter.** A model that answers "face" to a face-like pattern cannot say what
it looked at, and cannot be corrected by a measurement. These files are different in kind: a PSD from a 3D character pack
is the layer stack somebody actually built, so every name in it is a decision about what a part is -- 顔, 後頭部, チーク,
鼻口, 下瞼, アイライン -- and every bbox is where that part sits.

**What they are not.** These are texture pages for a 3D model, laid out in UV space on a 4096 square. The bboxes are
therefore part boundaries, not picture coordinates, and this file collects them as a vocabulary and a size table rather
than as ground truth for any particular drawing.

    python tools/part_vocabulary.py --root E:\\ANMS --out learn/model-parts.json
"""

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for extra in (ROOT, HERE):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


def walk(group, depth=0):
    """Every leaf layer as `(depth, name, bbox)`, groups marked by their own names."""
    rows = []
    for layer in group:
        if layer.is_group():
            rows.append((depth, '[' + layer.name + ']', None))
            rows.extend(walk(layer, depth + 1))
        else:
            rows.append((depth, layer.name, tuple(int(v) for v in layer.bbox)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=r'E:\ANMS')
    ap.add_argument('--out', default='learn/model-parts.json')
    ap.add_argument('--limit', type=int, default=0, help='stop after this many PSDs; zero reads all')
    args = ap.parse_args()

    from psd_tools import PSDImage
    root = pathlib.Path(args.root)
    pages = sorted(root.rglob('*.psd'))
    if args.limit:
        pages = pages[:args.limit]
    print('  %d PSD pages' % len(pages))
    out = {'pages': {}, 'note': ''}
    names = {}
    for page in pages:
        try:
            psd = PSDImage.open(page)
            rows = walk(psd)
        except Exception as problem:
            print('  %-28s unreadable: %s' % (page.name[:28], problem))
            continue
        leaves = [(depth, name, bbox) for depth, name, bbox in rows if bbox is not None]
        for _depth, name, bbox in leaves:
            names.setdefault(name, []).append([bbox[2] - bbox[0], bbox[3] - bbox[1]])
        out['pages'][page.name] = {'canvas': [psd.width, psd.height],
                                   'layers': [[depth, name, list(bbox) if bbox else None] for depth, name, bbox in rows]}
        print('  %-28s %3d layers, %3d leaves' % (page.name[:28], len(rows), len(leaves)))
    out['vocabulary'] = {name: {'count': len(sizes),
                                'median_wh': [sorted(s[0] for s in sizes)[len(sizes) // 2],
                                              sorted(s[1] for s in sizes)[len(sizes) // 2]]}
                         for name, sizes in names.items()}
    out['note'] = ('Layer names from the artist-built PSDs of a 3D character pack. They are part names and part sizes in '
                   'UV space, not picture coordinates: the value is the vocabulary and the relative sizes, and the '
                   'caution is that a texture page lays parts out side by side rather than where they go on a body.')
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('  %d distinct layer names, written to %s' % (len(names), target))


if __name__ == '__main__':
    raise SystemExit(main())
