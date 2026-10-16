"""How many separate pieces is a drawing made of, mine against real linework?

**The gap this fills, and why it was the last one open.** Every quantity tried on this drawing was designed for a
picture that is one connected whole. `taper_ratio` is the thinnest fifth of the runs over their mean, and on this
drawing that fifth turns out to be six finger bones -- so it reports how thin the fingers were drawn. `p90/median`
draws from the same window. **What is actually wrong here is continuity**, and the number that speaks to it is the
count of pieces: thirty-three strokes before the chaining change and thirteen now.

**But thirteen is only meaningful against something.** The material on this machine is 180 design-sheet pages that
turn out to hold illustrations mixed with linework, and 332 pixiv works tagged for cel shading -- **neither is
linework.** `線画` is a real pixiv tag with 122,434 works under it, and this fetches a sample of them and measures the
same thing.

**Normalised by the ink, not by the canvas.** A drawing twice as large has roughly twice the ink and roughly twice the
count, so the count against the square root of the ink area is what compares across sizes.

    python linework_reference.py --pages 3
"""
import argparse
import json
import math
import pathlib
import re
import subprocess
import urllib.parse

import numpy as np
from PIL import Image
from scipy import ndimage

PROXY = 'http://127.0.0.1:10090'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/131.0 Safari/537.36')
OUT = pathlib.Path(r'E:\DaShaoHuo\downloads\pixiv-senga')
TMP = pathlib.Path(r'E:\DaShaoHuo\cache\tmp')
MINE = pathlib.Path(r'E:\DaShaoHuo\cache\chained.png')
THRESHOLD = 200          # ink is anything darker than this; the reference's own threshold is 128 and this is looser
MIN_BLOB = 8             # a blob smaller than this is a speck of anti-aliasing, not a line


def search(tag, page):
    q = urllib.parse.quote(tag)
    url = ('https://www.pixiv.net/ajax/search/artworks/%s?word=%s&order=date_d&mode=all&p=%d'
           '&s_mode=s_tag&type=all&lang=ja' % (q, q, page))
    path = TMP / ('senga-%s-%d.json' % (re.sub(r'\W+', '_', tag), page))
    if not path.exists() or path.stat().st_size < 1000:
        subprocess.run(['curl', '-s', '-x', PROXY, '--max-time', '45',
                        '-H', 'User-Agent: ' + UA, '-H', 'Referer: https://www.pixiv.net/',
                        '-H', 'Accept: application/json', url, '-o', str(path)], check=False)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def pieces(path):
    """The count of separate ink blobs, the ink area, and the height.

    **Connected components, which is the same statistic as "how many ends" up to a factor of two** -- a line has two
    ends and one piece, a fork has three ends and still one piece. Components are the cheaper and steadier of the two
    because they need no skeletonisation, and a skeleton has its own opinion about where a line stops.
    """
    with Image.open(path) as im:
        g = np.array(im.convert('L'))
    ink = g < THRESHOLD
    lab, n = ndimage.label(ink, structure=np.ones((3, 3), dtype=int))
    if n == 0:
        return 0, 0, g.shape[0]
    sizes = ndimage.sum(ink, lab, range(1, n + 1))
    keep = int((sizes >= MIN_BLOB).sum())
    return keep, int(ink.sum()), g.shape[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pages', type=int, default=3)
    ap.add_argument('--tag', default='線画')
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    seen = {}
    for page in range(1, args.pages + 1):
        d = search(args.tag, page)
        if not d or d.get('error'):
            continue
        for it in d['body']['illustManga']['data']:
            if not it.get('id') or not it.get('url'):
                continue
            if it.get('illustType') not in (0, None) or it.get('xRestrict'):
                continue
            seen[it['id']] = it['url']
    print('  %d works tagged %s' % (len(seen), args.tag))

    rows = []
    for wid, url in sorted(seen.items()):
        master = re.sub(r'/c/[\d]+x[\d]+(_\d+)?(_a\d+)?/', '/', url)
        master = re.sub(r'_(square|custom|master)1200\.', '_master1200.', master)
        target = OUT / ('%s.jpg' % wid)
        if not target.exists() or target.stat().st_size == 0:
            r = subprocess.run(['curl', '-s', '-x', PROXY, '--max-time', '60',
                                '-H', 'Referer: https://www.pixiv.net/', '-H', 'User-Agent: ' + UA,
                                master, '-o', str(target), '-w', '%{http_code}|%{content_type}'],
                               capture_output=True, text=True)
            code, _, ctype = r.stdout.partition('|')
            if code != '200' or 'image' not in ctype:
                target.unlink(missing_ok=True)
                continue
        try:
            b = target.read_bytes()
            if b[-2:] != b'\xff\xd9':
                target.unlink(missing_ok=True)
                continue
            rows.append((wid,) + pieces(str(target)))
        except Exception:
            continue
    print('  %d downloaded and measurable' % len(rows))
    if not rows:
        return 1

    mine = pieces(str(MINE))
    print()
    print('  %-14s %8s %10s %10s %12s' % ('', 'blobs', 'ink px', 'height', 'blobs/sqrt(ink)'))
    print('  %-14s %8d %10d %10d %12.4f' % ('this drawing', mine[0], mine[1], mine[2],
                                            mine[0] / math.sqrt(max(1, mine[1]))))
    vals = sorted(r[1] / math.sqrt(max(1, r[2])) for r in rows)
    n = len(vals)
    print('  %-14s %8s %10s %10s %12.4f' % ('linework p05', '', '', '', vals[int(0.05 * (n - 1))]))
    print('  %-14s %8s %10s %10s %12.4f' % ('linework p25', '', '', '', vals[int(0.25 * (n - 1))]))
    print('  %-14s %8s %10s %10s %12.4f' % ('linework median', '', '', '', vals[n // 2]))
    print('  %-14s %8s %10s %10s %12.4f' % ('linework p75', '', '', '', vals[int(0.75 * (n - 1))]))
    print('  %-14s %8s %10s %10s %12.4f' % ('linework p95', '', '', '', vals[int(0.95 * (n - 1))]))
    print()
    below = sum(1 for v in vals if v < mine[0] / math.sqrt(max(1, mine[1])))
    print('  %.0f%% of the linework sample has fewer pieces per unit of ink than this drawing' % (100.0 * below / n))
    print()
    print('  ** where the drawing sits in that distribution is the answer to "how many pieces is right", and it is')
    print('     the first number in this whole stretch that can be read against real linework rather than against')
    print('     an illustration corpus or a mixture of the two. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
