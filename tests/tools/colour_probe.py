"""The classifier the corpus needs, designed from the pages rather than from a threshold.

The old rule -- `line_runs >= 200 and ink_ratio < 0.30` -- was a proxy for "this page is a drawing" and it fails on a
page that is mostly a **pale** drawing, which is what these design sheets are: line art in a single blue on a pale
blue panel. A colour illustration with light values passes the same test, which is how 276 "line art pages" turned out
to be "276 pages with little ink".

The property that actually separates them is **how many hues the drawing is made of**. A design sheet is one hue --
blue, or black -- plus paper. An illustration is many. So: find the ink, and measure the spread of its chroma.
"""
import pathlib, statistics, sys, json, random
sys.path.insert(0, r'E:\lineweight')
from lineweight import ref

D = pathlib.Path(r'F:\素材\图\碧蓝档案官方设定资料')


def probe(path):
    """Ink fraction, and how spread the ink's colour is."""
    rgb = ref.load_rgb(str(path))
    n = rgb.width * rgb.height
    lums = []
    chroma = []
    saturated = 0
    step = max(1, n // 120000)          # a sample of the page, not every pixel of a 150-megapixel scan
    for i in range(0, n, step):
        j = i * 3
        r, g, b = rgb.pixels[j], rgb.pixels[j + 1], rgb.pixels[j + 2]
        y = 0.299 * r + 0.587 * g + 0.114 * b
        mx, mn = max(r, g, b), min(r, g, b)
        lums.append(y)
        chroma.append(mx - mn)
        if mx - mn > 40:
            saturated += 1
    lums.sort()
    paper = lums[int(len(lums) * 0.95)]
    ink_cut = paper - 0.25 * (paper - lums[0]) if paper > lums[0] else paper - 1
    ink_chroma = [c for y, c in zip(lums, chroma) if y < ink_cut]
    return {
        'width': rgb.width, 'height': rgb.height,
        'ink_ratio': sum(1 for y in lums if y < ink_cut) / len(lums),
        'saturated_ratio': saturated / len(lums),
        'ink_chroma_median': statistics.median(ink_chroma) if ink_chroma else 0.0,
        'ink_chroma_p90': (sorted(ink_chroma)[int(0.9 * len(ink_chroma))] if ink_chroma else 0.0),
        'paper': paper,
    }


def main():
    random.seed(5)
    rows = []
    for v in ('1', '2', '3'):
        files = sorted((D / v).iterdir())
        pick = random.sample(files, min(20, len(files)))
        for f in pick:
            try:
                r = probe(f)
            except Exception as e:
                r = {'error': '%s: %s' % (type(e).__name__, str(e)[:50])}
            r['volume'] = v
            r['file'] = f.name
            rows.append(r)
    good = [r for r in rows if 'error' not in r]
    print('probed %d pages (%d unreadable)' % (len(good), len(rows) - len(good)))
    print()
    print('%-14s %9s %9s %9s %9s %6s' % ('file', 'ink', 'saturated', 'chroma_med', 'chroma_p90', 'paper'))
    for r in sorted(good, key=lambda r: r['ink_chroma_median']):
        print('%-14s %9.4f %9.4f %9.1f %9.1f %6.0f'
              % (r['file'], r['ink_ratio'], r['saturated_ratio'],
                 r['ink_chroma_median'], r['ink_chroma_p90'], r['paper']))
    json.dump(rows, open(r'E:\DaShaoHuo\cache\corpus\colour_probe.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
