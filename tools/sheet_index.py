"""Turn the design-sheet pages into contact sheets, so they can be looked at rather than measured.

**Why this exists.** The collection is 929 images with numeric file names and no index, and every number this project
has taken from it was taken by sampling -- which mixed character sheets with illustrations, comic pages and props, and
averaged them. **Looking is the thing that was missing, so this makes looking possible in slices**: thirty pages per
sheet, in file order, with each page numbered on the tile.

    python sheet_index.py --volume 1 --from 0 --to 30
    python sheet_index.py --volume 1 --all
"""
import argparse
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(r'F:\素材\图\碧蓝档案官方设定资料')
OUT = pathlib.Path(r'E:\DaShaoHuo\cache\tmp\sheets')


def volume_pages(vol):
    d = ROOT / vol
    return sorted(d.glob('*.jpg')) + sorted(d.glob('*.png'))


def sheet(files, out_dir, cols=6, cell=260, pad=4):
    """One image holding `len(files)` pages, each labelled with its file name along the bottom edge."""
    rows = (len(files) + cols - 1) // cols
    w = cols * (cell + pad) + pad
    h = rows * (cell + pad) + pad
    im = Image.new('RGB', (w, h), (250, 248, 244))
    draw = ImageDraw.Draw(im)
    for i, f in enumerate(files):
        try:
            with Image.open(f) as p:
                p = p.convert('RGB')
                p.thumbnail((cell, cell - 14))
        except Exception:
            continue
        x = pad + (i % cols) * (cell + pad)
        y = pad + (i // cols) * (cell + pad)
        im.paste(p, (x, y))
        # **The name goes on the tile**, because a page that turns out to matter has to be findable again by name and
        # not by counting positions in a picture of a hundred pictures.
        draw.text((x + 2, y + cell - 13), f.stem, fill=(110, 100, 96))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ('%s-%03d-%03d.png' % (files[0].parent.name, int(files[0].stem.split('-')[-1]) if files[0].stem.split('-')[-1].isdigit() else 0, len(files)))
    im.save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--volume', default='1')
    ap.add_argument('--from', dest='start', type=int, default=0)
    ap.add_argument('--to', dest='stop', type=int, default=30)
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()

    fs = volume_pages(args.volume)
    print('  volume %s holds %d pages' % (args.volume, len(fs)))
    if args.all:
        made = 0
        for i in range(0, len(fs), 30):
            p = sheet(fs[i:i + 30], OUT)
            print('    %s' % p.name)
            made += 1
        print('  %d sheets in %s' % (made, OUT))
    else:
        p = sheet(fs[args.start:args.stop], OUT)
        print('  -> %s  (pages %d to %d)' % (p, args.start, min(args.stop, len(fs)) - 1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
