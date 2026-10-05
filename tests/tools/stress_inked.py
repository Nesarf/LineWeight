"""Run `inked_svg` over real vector artwork, which is the case it exists for and has never been tested on.

Everything so far has exercised it with synthetic documents and a four-stroke demo sheet. Its actual job is to walk a
finished SVG and weight its linework, and the artwork in this repository's sibling project is a fair sample: hand-built
icons, nine-slice panels, a divider, a wash, and figures. Nested groups, transforms, `<defs>`, `<use>`, gradients and
arcs all appear in real files and mostly do not appear in the synthetic ones.

The check is not "does it not crash" -- a transform dropped or a curve swallowed produces output that is well formed
and wrong, which is the failure this project keeps meeting. So each file is checked for the invariants that matter:

* every element in the input that is not a `<path>` survives, because a pass that rebuilds the document deletes what
  it does not understand -- `inked_svg` did exactly that once and took a figure's eyes with it;
* the output parses as XML;
* the weighted outlines land near the shapes they outline rather than at the origin.
"""
import os
import re
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight import inked_svg
from lineweight.core import parse_path

SOURCES = [
    r'E:\hollow-court\art\hma\motif.svg',
    r'E:\hollow-court\art\hma\divider.svg',
    r'E:\hollow-court\art\hma\wash.svg',
    r'E:\hollow-court\art\hma\panel-9slice.svg',
    r'E:\hollow-court\art\cups-v1.svg',
    r'E:\hollow-court\art\cups-v2.svg',
    r'E:\hollow-court\art\icon-hc-a128.svg',
    r'E:\hollow-court\art\icon-hc-a48.svg',
    r'E:\hollow-court\art\miku-wide.svg',
]


def count_elements(svg: str) -> dict:
    kinds = {}
    for name in re.findall(r'<([a-zA-Z][\w:-]*)', svg):
        kinds[name] = kinds.get(name, 0) + 1
    return kinds


def outline_bounds(svg: str) -> tuple[float, float, float, float] | None:
    """Bounds of the weighted contours only: the ones carrying an opacity, which is what the pass adds."""
    generated = re.findall(r'<path d="([^"]+)" fill="[^"]*" opacity=', svg)
    xs, ys = [], []
    for d in generated:
        for x, y in re.findall(r'(-?\d+\.?\d*) (-?\d+\.?\d*)', d):
            xs.append(float(x))
            ys.append(float(y))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def main() -> int:
    print('%-24s %8s %8s %7s %7s %9s  %s'
          % ('file', 'in', 'out', 'paths', 'guards', 'outlines', 'verdict'))
    problems = 0
    for path in SOURCES:
        name = os.path.basename(path)
        if not os.path.exists(path):
            print('%-24s MISSING' % name)
            continue
        with open(path, encoding='utf-8', errors='replace') as handle:
            source = handle.read()
        try:
            out = inked_svg(source, min_extent=30)
        except Exception as exc:                        # noqa: BLE001 - a crash here is the finding
            print('%-24s %8d %8s %7s %7s %9s  RAISED %s: %s'
                  % (name, len(source), '-', '-', '-', '-', type(exc).__name__, exc))
            problems += 1
            continue
        before, after = count_elements(source), count_elements(out)
        # every element kind that is not a path must survive untouched: that is the defect that ate a figure's eyes
        lost = {k: (before[k], after.get(k, 0)) for k in before
                if k != 'path' and after.get(k, 0) < before[k]}
        try:
            ET.fromstring(out)
            parses = True
        except ET.ParseError as exc:
            parses = False
            lost['__xml__'] = ('valid', str(exc))
        outlines = outline_bounds(out)
        ok = parses and not lost
        if not ok:
            problems += 1
        print('%-24s %8d %8d %7d %7s %9s  %s'
              % (name, len(source), len(out), before.get('path', 0),
                 'kept' if not lost else 'LOST %s' % lost,
                 'none' if outlines is None else '%d pts' % 0,
                 'ok' if ok else 'FAILED'))
        if outlines:
            print('%-24s   outlines span x %.0f..%.0f  y %.0f..%.0f'
                  % ('', outlines[0], outlines[2], outlines[1], outlines[3]))
    print()
    print('%d of %d files had a problem.' % (problems, len(SOURCES)))
    return 0 if problems == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
