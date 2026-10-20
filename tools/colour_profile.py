"""Where the colour changes down a vertical line, which is what "where does the skirt end" actually asks.

**Why a scan line and not a region.** The last attempt to find a boundary ran into five thousand colours and gave up. A
scan line asks a much smaller question: **at this one x, at what heights does the colour jump?** A jump is where one
material gives way to another -- skin to cloth, cloth to legwear -- and that is the question, not "segment the picture".

**And why the jump is measured on a smoothed colour, not the raw one.** A painted surface changes by a little at every
pixel, so the raw difference never drops to zero and every height looks like a boundary. Smoothing over a few pixels
first means only the places where the colour moves far and stays moved survive.

    python tools/colour_profile.py --src "F:\\素材\\图\\涩涩！\\mmk.jpg" --x 500
"""
import argparse
import pathlib
import sys


def load_rgb(path):
    from PIL import Image, ImageFilter
    im = Image.open(path).convert('RGB')
    im = im.filter(ImageFilter.BoxBlur(2))
    w, h = im.size
    px = im.load()
    return px, w, h


def scan(px, w, h, x, band=3):
    """The mean colour in a narrow vertical band, one row at a time."""
    rows = []
    x0 = max(0, x - band)
    x1 = min(w, x + band + 1)
    for y in range(h):
        r = g = b = 0
        n = 0
        for xx in range(x0, x1):
            pr, pg, pb = px[xx, y]
            r += pr; g += pg; b += pb; n += 1
        rows.append((r / n, g / n, b / n))
    return rows


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--x', type=int, required=True, help='the column to scan, in the source picture')
    ap.add_argument('--gap', type=int, default=6, help='rows between the two colours being compared')
    ap.add_argument('--jump', type=float, default=18.0, help='colour distance that counts as a change')
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    if not src.exists():
        print('  missing: %s' % src)
        return 1
    px, w, h = load_rgb(src)
    if not (0 <= args.x < w):
        print('  x %d is outside 0..%d' % (args.x, w - 1))
        return 1
    rows = scan(px, w, h, args.x)

    print('  %s  column x=%d  height %d' % (src.name, args.x, h))
    print('  comparing each row with the row %d below it; a jump above %.0f counts as a material change' % (args.gap, args.jump))
    print()
    found = []
    for y in range(0, h - args.gap):
        d = dist(rows[y], rows[y + args.gap])
        if d > args.jump:
            found.append((y, d, rows[y], rows[y + args.gap]))
    if not found:
        print('  no jumps at this column')
        return 0
    # **Runs of adjacent jumps are one change.** A boundary that takes several rows to cross produces a jump at every
    # one of them, and reporting each would bury the boundary in its own detail.
    runs = []
    for y, d, a, b in found:
        if runs and y - runs[-1][-1][0] <= 3:
            runs[-1].append((y, d, a, b))
        else:
            runs.append([(y, d, a, b)])
    print('  %d jump runs, each a place where the material changes:' % len(runs))
    print('    %-7s %-7s %-6s %s' % ('row', 'frac', 'peak', 'colour above -> below'))
    for run in runs:
        y, d, a, b = max(run, key=lambda t: t[1])
        print('    %-7d %-7.3f %-6.0f (%3.0f,%3.0f,%3.0f) -> (%3.0f,%3.0f,%3.0f)'
              % (y, y / float(h), d, a[0], a[1], a[2], b[0], b[1], b[2]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
