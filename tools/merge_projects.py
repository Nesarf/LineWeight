"""Two project files into one, from the command line.

**The merge itself lives in the library**, as `project.combine` -- it is a property of the project file, not of this
script, and a test reaches it without going near `tools/`. This wrapper only reads, combines and writes.

    python tools/merge_projects.py --fills shapes.json --lines lines.json --out picture.json
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, r'D:\lineweight')

from lineweight import project


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fills', required=True)
    ap.add_argument('--lines', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    fills = load(args.fills)
    lines = load(args.lines)
    try:
        merged = project.combine(fills, lines)
    except ValueError as problem:
        raise SystemExit('  %s' % problem)

    fills_n = sum(1 for m in fills.get('marks', []) if m.get('kind') == 'fill')
    lines_n = sum(1 for m in lines.get('marks', []) if m.get('kind') == 'stroke')
    other = len(merged['marks']) - fills_n - lines_n
    if other:
        print('  %d marks are neither a fill nor a stroke; they are kept in place' % other)

    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('  %d fills + %d strokes = %d marks on a %dx%d page'
          % (fills_n, lines_n, len(merged['marks']),
             merged['canvas']['width'], merged['canvas']['height']))
    print('  written to %s' % target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
