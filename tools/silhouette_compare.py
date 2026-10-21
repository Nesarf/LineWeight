"""Compare a rendering's own silhouette against a measured model profile, height by height.

**What this is for.** `model/shape/<name>.json` says how wide a real character actually is at every height. A rendering
can be measured the same way -- from the background to the background, row by row -- and then the two columns of
numbers can be read side by side. **That turns "it does not look like a bishoujo" into a row where the drawing is
seven points narrower than the reference**, which is a thing a change can be pointed at.

**The comparison is of widths, not of depth.** A rendering has no depth to measure; the profile supplies the depth the
picture would have if it were the model, and the depth of a drawing is a consequence of what the drawing chooses to
show, not a quantity in its file.

    python tools/silhouette_compare.py --png E:\\DaShaoHuo\\cache\\cel-face.png --profile model/shape/Zome.json
"""
import argparse
import json
import pathlib


def load_png_rows(path):
    """(height fraction, width over height) from a saved rendering, against its own background colour."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    w, h = im.size
    px = im.load()
    # **The background is whatever the top left corner is**, which is true of every image this project renders and is
    # stated rather than assumed: a picture with a drawn background would need a different rule.
    bg = px[0, 0]
    rows = []
    for y in range(h):
        lo = hi = None
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > 40:
                if lo is None:
                    lo = x
                hi = x
        if lo is not None:
            rows.append((y, lo, hi))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--png', required=True)
    ap.add_argument('--profile', required=True)
    ap.add_argument('--steps', type=int, default=20)
    args = ap.parse_args()

    rows = load_png_rows(args.png)
    if len(rows) < 10:
        print('  nothing found against the background colour')
        return 1
    top, bottom = rows[0][0], rows[-1][0]
    height = float(bottom - top + 1)

    profile = json.loads(pathlib.Path(args.profile).read_text(encoding='utf-8'))
    ref = {(round(r['y'], 2)): r for r in profile['rows']}

    print('  %s   figure %d px tall' % (pathlib.Path(args.png).name, int(height)))
    print('  %s   %d bands' % (pathlib.Path(args.profile).name, profile['bands']))
    print()
    print('    %-7s %8s %8s %8s' % ('height', 'drawn', 'model', 'difference'))
    worst = (0.0, 0.0)
    for i in range(args.steps + 1):
        frac = i / float(args.steps)
        # **The reference profile counts from the feet and an image counts from its top row**, so the walk is upward
        # from the bottom. Comparing the two without turning one around produced a table where the hips were compared
        # with the head and every number was wrong in a way that still looked like a table.
        y = bottom - frac * (height - 1)
        near = min(rows, key=lambda r: abs(r[0] - y))
        drawn = (near[2] - near[1] + 1) / height
        key = min(ref, key=lambda k: abs(k - frac))
        model = ref[key]['w']
        diff = drawn - model
        if abs(diff) > abs(worst[1]):
            worst = (frac, diff)
        bar = '#' * int(min(30, abs(diff) * 120))
        print('    %-7.2f %8.3f %8.3f %+8.3f %s' % (frac, drawn, model, diff, bar))
    print()
    print('  the widest disagreement is %+.3f of the height, at %.2f up' % (worst[1], worst[0]))
    print('  a positive number means the drawing is wider than the model there')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
