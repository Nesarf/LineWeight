"""Add a set of images to the measured corpus and re-derive the pooled summary.

The corpus is two private collections so far, measured once into a JSON Lines file. Material keeps arriving, and the
value of the pool is that it can be added to without re-measuring what is already there -- so this appends only what is
missing, using the same measure function and the same resumability rules as the original run.

**What belongs in a linework corpus is a real question, and the answer is not "images".** A UI kit is mostly filled
rectangles and gradients: measuring its line-width distribution measures the widths of nothing, and mixing it into the
pool would move the targets the brushes are calibrated against in a direction that has nothing to do with drawing.
This script therefore takes an explicit `--kind` and refuses to guess: `linework` for character art and design sheets,
and nothing else for now.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight.ref import measure

EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')


def images_in(root: str) -> list[str]:
    return sorted(os.path.join(base, name) for base, _d, files in os.walk(root)
                  for name in files if os.path.splitext(name)[1].lower() in EXTS)


def load_records(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print('usage: add_corpus.py LIBRARY.jsonl TAG DIR [DIR ...]')
        return 2
    library = sys.argv[1]
    tag = sys.argv[2]
    roots = sys.argv[3:]
    if not roots:
        print('nothing to add: no directories given')
        return 2

    records = load_records(library)
    known = {r.get('path') for r in records}
    print('library has %d records' % len(records))
    todo = []
    for root in roots:
        if not os.path.isdir(root):
            print('missing: %s' % root)
            continue
        for path in images_in(root):
            if path not in known:
                todo.append(path)
    print('to measure: %d' % len(todo))
    if not todo:
        print('nothing to do')
        return 0

    started = time.time()
    added = 0
    with open(library, 'a', encoding='utf-8', newline='\n') as handle:
        for index, path in enumerate(todo, 1):
            try:
                m = measure(path)
                record = {'source': tag, 'path': path, 'width': m.width, 'height': m.height,
                          'line_runs': m.line_runs, 'area_runs': m.area_runs, 'runs': m.runs,
                          'ink_ratio': m.ink_ratio, 'darkness': m.darkness, 'width_mean': m.width_mean,
                          'width_median': m.width_median, 'width_p90': m.width_p90, 'width_max': m.width_max,
                          'taper_ratio': m.taper_ratio, 'note': m.note}
            except Exception as exc:                    # noqa: BLE001 - an unreadable image is a record too
                record = {'source': tag, 'path': path, 'error': '%s: %s' % (type(exc).__name__, exc)}
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
            handle.flush()
            added += 1
            if index % 5 == 0 or index == len(todo):
                print('  %d/%d  %s' % (index, len(todo), os.path.basename(path)[:40]), flush=True)
    print('added %d records in %.0fs' % (added, time.time() - started))

    # re-derive the pooled summary from everything now in the library
    all_records = load_records(library)
    good = [r for r in all_records if 'error' not in r]
    linework = [r for r in good if r['note'] == '' and r['line_runs'] >= 200 and r['ink_ratio'] < 0.30]
    paintings = [r for r in good if r['note'] == '' and r['ink_ratio'] >= 0.30]
    print()
    print('pooled: %d records, %d linework, %d paintings' % (len(good), len(linework), len(paintings)))
    by_source = {}
    for r in good:
        by_source.setdefault(r['source'], 0)
        by_source[r['source']] += 1
    print('by source:', by_source)

    import statistics as st

    def dist(rows, key):
        values = sorted(r[key] for r in rows)
        return {'median': round(st.median(values), 4),
                'p10': round(values[int(0.10 * len(values))], 4),
                'p90': round(values[int(0.90 * len(values))], 4)}

    summary = {
        'note': ('Pooled measurement of private corpora, kept so the calibration targets in the README can be '
                 'checked against the material they came from rather than taken on trust. The images themselves are '
                 'not part of this repository and neither are their paths: what is shared is the distribution, which '
                 'is a set of lengths and ratios, and the code that produced it.'),
        'corpora': [{'tag': k, 'images': v, 'shared': False,
                     'description': 'a private collection of artwork'} for k, v in sorted(by_source.items())],
        'totals': {'records': len(good), 'linework': len(linework), 'paintings': len(paintings)},
        'linework_width_median': dist(linework, 'width_median'),
        'linework_width_p90': dist(linework, 'width_p90'),
        'linework_ink_ratio': dist(linework, 'ink_ratio'),
        'linework_taper_ratio': dist(linework, 'taper_ratio'),
        'linework_p90_over_median': {
            'median': round(st.median([r['width_p90'] / r['width_median'] for r in linework if r['width_median']]), 4),
            'note': 'scale-free; the number a brush has to be able to reach inside one drawing',
        },
        'linework_resolution': {'median_width': int(st.median([r['width'] for r in linework])),
                                'median_height': int(st.median([r['height'] for r in linework]))},
    }
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       'tests', 'data', 'corpus_summary.json')
    with open(out, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write('\n')
    print('summary written to %s' % out)
    for key in ('linework_p90_over_median',):
        print('  %s = %s' % (key, summary[key]['median']))
    for key in ('linework_taper_ratio', 'linework_width_median', 'linework_ink_ratio'):
        print('  %s = %s' % (key, summary[key]['median']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
