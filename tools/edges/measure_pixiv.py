"""The shadow boundary in 332 cel-tagged illustrations.

The instrument is calibrated (see `edge_width.calibrate`) and its floor on JPEG is measured, not assumed: a synthetic
hard edge reads 1.0 px as a PNG and 5.0 after JPEG at quality 95. **So on these files "hard" means "at the floor".**

Caveat that has to be said before the numbers: **this measures every strong colour boundary, not shadow boundaries.**
Line art, highlights, a character against a background and a frame are all in the distribution. Separating them needs
a classifier this project does not have.
"""
import pathlib, statistics, sys, json, collections
sys.path.insert(0, r'E:\DaShaoHuo\tools\edges')
from edge_width import edge_widths
from PIL import Image

D = pathlib.Path(r'E:\DaShaoHuo\downloads\pixiv-cel')
rows = []
sizes = collections.Counter()
for f in sorted(D.glob('*.jpg')):
    try:
        im = Image.open(f); im.load()
    except Exception:
        continue
    sizes['%dx%d' % im.size] += 1
    work = im
    if max(im.size) > 1200:
        k = 1200 / max(im.size)
        work = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    ws = edge_widths(work, stride=5, threshold=24.0)
    if len(ws) < 50:
        continue
    ws.sort()
    rows.append({'file': f.name, 'size': '%dx%d' % im.size, 'edges': len(ws),
                 'median': statistics.median(ws), 'p25': ws[len(ws) // 4], 'p90': ws[int(len(ws) * 0.9)],
                 'at_floor': sum(1 for x in ws if x <= 5) / len(ws)})
print('illustrations measured: %d' % len(rows))
allw = [r['median'] for r in rows]
allf = [r['at_floor'] for r in rows]
print('per-image median transition width:  min %.1f  p25 %.1f  median %.1f  p75 %.1f  max %.1f px'
      % (min(allw), sorted(allw)[len(allw) // 4], statistics.median(allw),
         sorted(allw)[3 * len(allw) // 4], max(allw)))
print('fraction of edges at or below the 5 px JPEG floor: median %.2f  range %.2f-%.2f'
      % (statistics.median(allf), min(allf), max(allf)))
print()
buckets = collections.Counter()
for m in allw:
    buckets['<= 5 px (at the floor)' if m <= 5 else
            '6-8 px' if m <= 8 else
            '9-12 px' if m <= 12 else
            '> 12 px'] += 1
print('images by their median width:')
for k in ('<= 5 px (at the floor)', '6-8 px', '9-12 px', '> 12 px'):
    print('   %-26s %3d  (%.0f%%)' % (k, buckets[k], 100.0 * buckets[k] / len(rows)))
print()
print('most common image sizes: %s' % ', '.join('%s x%d' % (k, v) for k, v in sizes.most_common(4)))
json.dump(rows, open(r'E:\DaShaoHuo\cache\pixiv_edges.json', 'w'), indent=1)
