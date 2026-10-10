"""Classify the corpus on both criteria, and build the contact sheets that check the classification.

**A classifier has to be looked at.** Counting how many pages land in each bucket says nothing about whether the
buckets mean anything; the only check is the pages themselves, so this writes a contact sheet per class and the
numbers are reported next to it rather than instead of it.
"""
import json, pathlib, sys, statistics, collections
sys.path.insert(0, r'E:\lineweight')
from PIL import Image, ImageDraw

SRC = pathlib.Path(r'F:\素材\图\碧蓝档案官方设定资料')
OUT = pathlib.Path(r'E:\DaShaoHuo\cache\corpus')

#: Below this median chroma the ink is one hue. Measured: the design sheets sit at 0.0 and the illustrations at 6.0
#: and up, with nothing in the 60-page probe in between -- so the cut is in an empty band rather than on a slope.
MONOCHROME = 3.0
#: A picture needs this many line-like runs before a width distribution means anything. `ref.MIN_LINE_RUNS`.
MIN_LINES = 200


def classify(r):
    if 'error' in r or 'ink_chroma_median' not in r:
        return 'unreadable'
    if r['ink_chroma_median'] < MONOCHROME and r['line_runs'] >= MIN_LINES:
        return 'linework'
    if r['ink_chroma_median'] >= MONOCHROME:
        return 'colour'
    return 'monochrome but few lines'


def contact(rows, name, cols=6, cell=220):
    if not rows:
        return None
    rows = rows[:36]
    rws = (len(rows) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rws * (cell + 16)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(rows):
        p = SRC / r['volume'] / r['file']
        try:
            im = Image.open(p).convert('RGB')
        except Exception:
            continue
        im.thumbnail((cell - 6, cell - 6))
        x, y = (i % cols) * cell, (i // cols) * (cell + 16)
        sheet.paste(im, (x + 3, y + 3))
        d.text((x + 4, y + cell - 12), '%s ch%.0f l%d' % (r['file'][:14], r['ink_chroma_median'],
                                                          r['line_runs']), fill=(0, 0, 0))
    path = OUT / ('sheet_%s.png' % name)
    sheet.save(path)
    return path


def main():
    rows = json.loads((OUT / 'records.json').read_text(encoding='utf-8'))
    groups = collections.defaultdict(list)
    for r in rows:
        r['class'] = classify(r)
        groups[r['class']].append(r)
    print('records: %d' % len(rows))
    for k in sorted(groups):
        print('   %-24s %4d' % (k, len(groups[k])))
    print()
    lw = groups['linework']
    if lw:
        for key in ('ink_ratio', 'line_runs', 'width_median', 'width_p90', 'taper_ratio', 'ink_chroma_median'):
            vals = sorted(r[key] for r in lw if key in r)
            if vals:
                print('   linework %-18s median %8.2f   p10 %8.2f   p90 %8.2f'
                      % (key, statistics.median(vals), vals[int(0.1 * len(vals))], vals[int(0.9 * len(vals))]))
    print()
    print('=== the old rule, for comparison ===')
    old = [r for r in rows if 'line_runs' in r and r['line_runs'] >= 200 and r['ink_ratio'] < 0.30]
    print('   old classifier would call %d pages linework; the new one calls %d' % (len(old), len(lw)))
    oldset = {(r['volume'], r['file']) for r in old}
    newset = {(r['volume'], r['file']) for r in lw}
    print('   agreed %d, only new %d, only old %d'
          % (len(oldset & newset), len(newset - oldset), len(oldset - newset)))
    for name in ('linework', 'colour', 'monochrome but few lines'):
        p = contact(groups[name], name.replace(' ', '_'))
        if p:
            print('   contact sheet: %s' % p)


if __name__ == '__main__':
    main()
