"""Which references are linework on paper, and which are illustrations: a survey of a folder.

**The question this answers.** A folder of downloaded images is not a folder of linework. Of 152 files under a `線画` tag,
37 are a pencil line on white and the rest include filled pictures, comic pages, blank drafts and heraldic patterns --
**the tag is the uploader's, the ink ratio is the file's**. So a survey is what turns a collection into a working set.

**Three numbers, and each says a different thing:**

    ink    the fraction of the page darker than 200 out of 255 -- a drawing on paper sits near 0.01, a filled picture 0.3
    white  the fraction brighter than 235 -- how much of the page is paper, which a line drawing leaves alone
    size   the long side, because a reference smaller than the working size cannot supply the line's own shape

**A JPEG is decoded at a draft size rather than in full**, which is what makes a survey of 900 pages take a minute
instead of ten. The statistics do not need the full page; only the trace does.

    python tools/linework_survey.py --root "E:\\DaShaoHuo\\downloads\\pixiv-senga"
"""
import argparse
import os
import pathlib

import numpy as np
from PIL import Image

#: The decode size for the statistics. **Only for measuring a file, never for tracing it.**
DRAFT = 512

#: What counts as linework on paper: a page that is mostly paper, a little ink, and big enough to trace.
WHITE_MIN = 0.85
INK_MIN = 0.001
INK_MAX = 0.06
LONG_MIN = 1000


def measure(path, draft):
    im = Image.open(path)
    if draft:
        im.draft('L', (draft, draft))
    w, h = im.size
    a = np.asarray(im.convert('L'), dtype=np.uint8)
    total = float(a.size or 1)
    return w, h, float((a < 200).sum()) / total, float((a > 235).sum()) / total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--draft', type=int, default=DRAFT)
    ap.add_argument('--show', type=int, default=0, help='print this many rows; 0 prints only the ones that qualify')
    ap.add_argument('--top', type=int, default=40)
    args = ap.parse_args()

    files = []
    for dirpath, _dirnames, filenames in os.walk(args.root):
        files.extend(os.path.join(dirpath, f) for f in filenames)
    files.sort()

    rows = []
    failed = 0
    for path in files:
        try:
            w, h, ink, white = measure(path, args.draft)
        except Exception:
            failed += 1
            continue
        if max(w, h) < 4:
            continue
        rows.append((path, w, h, ink, white))

    good = [r for r in rows if r[4] >= WHITE_MIN and INK_MIN < r[3] < INK_MAX
            and max(r[1], r[2]) >= LONG_MIN]
    good.sort(key=lambda r: r[3])

    print('  %d files, %d measured, %d unreadable' % (len(files), len(rows), failed))
    print('  linework on paper: %d' % len(good))
    print()
    print('    %-22s %6s %6s %8s %8s' % ('file', 'w', 'h', 'ink', 'white'))
    for path, w, h, ink, white in good[:args.show or args.top]:
        print('    %-22s %6d %6d %8.4f %8.3f' % (pathlib.Path(path).name[:22], w, h, ink, white))
    if args.show:
        print()
        print('  every file:')
        for path, w, h, ink, white in sorted(rows, key=lambda r: r[3])[:args.show]:
            print('    %-22s %6d %6d %8.4f %8.3f' % (pathlib.Path(path).name[:22], w, h, ink, white))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
