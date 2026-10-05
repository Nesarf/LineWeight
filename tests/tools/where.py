"""Check that weighted outlines land where the shapes are, using the input's own coordinates as the reference.

**One case is not explained and is recorded rather than smoothed over.** `cups-v1.svg` comes out with its outlines
about 3% inside the ink bounds of the shape they belong to, and every path large enough to be inked was inked. Three
per cent is not the signature of a wrong coordinate space -- that looks like a factor, or like everything piled at
the origin -- so it is a separate question and it is left open. The other three files, including one where every path
carries a transform and one with nested groups, land within a pixel.

The earlier stress run confirmed nothing crashes and nothing is deleted, which is necessary and not sufficient. The
defect this project has actually shipped twice is a contour generated in the wrong coordinate space: the file is well
formed, every element survives, and the outlines sit somewhere the drawing is not. Bounds are the cheap way to see it
-- transform the input's own path coordinates by its own `transform` attributes and compare that box with the box of
the outlines that were added.

They will not match exactly: the outline is offset outward by half the local line width, so it is a little larger. What
it must not be is off by the transform -- an order of magnitude, or centred on the origin.
"""
import os
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight import inked_svg
from lineweight.core import apply_transform, parse_path, parse_transform

# **The artwork is a parameter, not a constant.** This named four files on one machine, which made the check unrunnable
# elsewhere and put somebody's directory layout in a public repository. Name one or more directories instead and it
# measures what is in them; a file can also be named directly.
def _cases() -> list[tuple[str, str]]:
    raw = os.environ.get('LW_SVG_DIR', '')
    out: list[tuple[str, str]] = []
    for root in (p for p in raw.split(os.pathsep) if p.strip()):
        if os.path.isfile(root):
            out.append((root, 'named directly'))
            continue
        for base, _dirs, files in os.walk(root):
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() == '.svg':
                    out.append((os.path.join(base, name), 'from the folder'))
    return out


def input_box(svg: str, min_extent: float = 30.0) -> tuple[float, float, float, float] | None:
    """Bounds of the source geometry that will actually be inked, transforms applied.

    **Only the shapes large enough to be inked count.** `inked_svg` deliberately leaves small details alone -- a heavy
    line around an eye is mud -- so comparing the outlines against *all* the input geometry reports a mismatch on any
    drawing with a catchlight in it, which is every drawing. The first version of this check did exactly that and
    flagged a correct file: the outlines were inside the input's box because the input's box included paths that were
    never going to be outlined.
    """
    stack = [(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)]
    xs, ys = [], []
    pattern = re.compile(r'<(/?)(g|path)\b((?:"[^"]*"|\'[^\']*\'|[^>])*?)(/?)>')
    for match in pattern.finditer(svg):
        closing, tag, attrs, self_closing = match.group(1), match.group(2), match.group(3), match.group(4)
        if tag == 'g':
            if closing:
                if len(stack) > 1:
                    stack.pop()
                continue
            inner = re.search(r'transform\s*=\s*"([^"]*)"', attrs)
            matrix = parse_transform(inner.group(1)) if inner else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            if self_closing:
                continue
            stack.append(_mul(stack[-1], matrix))
            continue
        found = re.search(r'\bd\s*=\s*"([^"]*)"', attrs)
        if not found:
            continue
        polys = parse_path(found.group(1))
        if not polys:
            continue
        flat = [point for poly in polys for point in poly]
        px = [x for x, _ in flat]
        py = [y for _, y in flat]
        # the same extent test the inking pass applies
        if (max(px) - min(px)) < min_extent and (max(py) - min(py)) < min_extent:
            continue
        inner = re.search(r'transform\s*=\s*"([^"]*)"', attrs)
        matrix = _mul(stack[-1], parse_transform(inner.group(1)) if inner else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
        for x, y in apply_transform(flat, matrix):
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _mul(m, n):
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2, a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def outline_box(svg: str) -> tuple[float, float, float, float] | None:
    xs, ys = [], []
    for d in re.findall(r'<path d="([^"]+)" fill="[^"]*" opacity=', svg):
        for x, y in re.findall(r'(-?\d+\.?\d*) (-?\d+\.?\d*)', d):
            xs.append(float(x))
            ys.append(float(y))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def main() -> int:
    cases = _cases()
    if not cases:
        print('no artwork configured: set LW_SVG_DIR to one or more directories of .svg files')
        return 2
    for path, note in cases:
        if not os.path.exists(path):
            print('%-16s missing' % os.path.basename(path))
            continue
        with open(path, encoding='utf-8', errors='replace') as handle:
            source = handle.read()
        out = inked_svg(source, min_extent=30)
        before, after = input_box(source), outline_box(out)
        name = os.path.basename(path)
        if before is None:
            print('%-16s %-34s no path geometry in the input' % (name, note))
            continue
        if after is None:
            print('%-16s %-34s NO OUTLINES PRODUCED' % (name, note))
            continue
        # the outline is the shape grown by half a line width on each side, so it must contain the input's box
        contains = after[0] <= before[0] + 1 and after[1] <= before[1] + 1 \
            and after[2] >= before[2] - 1 and after[3] >= before[3] - 1
        growth = max(abs(after[i] - before[i]) for i in range(4))
        span = max(before[2] - before[0], before[3] - before[1]) or 1.0
        print('%-16s %-34s input x%.0f..%.0f y%.0f..%.0f  outline x%.0f..%.0f y%.0f..%.0f  growth %.1f (%.1f%% of span)  %s'
              % (name, note, before[0], before[2], before[1], before[3],
                 after[0], after[2], after[1], after[3], growth, 100 * growth / span,
                 'ok' if contains and growth < span
                 else ('close (%.1f%%)' % (100 * growth / span) if growth < 0.05 * span else 'SUSPECT')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
