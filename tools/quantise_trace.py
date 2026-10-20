"""Trace a figure out of a picture whose background is painted.

**Why `trace.py` stops here.** It assumes the ground is white, so "not near white" is "the figure". With a painted
background that premise fails and the trace comes out as a rectangle. The check added there refuses instead of producing
one, which leaves the picture untraced -- and this tool is the other route.

**What this tool got wrong first, and how.** The opening rule was "the figure is the largest region of the quantised
palette that does not touch the frame". It was tried on three pictures and gave 3.2% / 3.5% / 5.2% of the page, and the
three numbers do not separate the two pictures that trace cleanly from the one that does not. A figure in these pictures
is 30-40% of the page. **A measure that returns the same small number on both sides of the question is not measuring
the question.** The two reasons, both visible in the region tables:

    the figure is not one colour -- skin, hair and cloth are separate labels, so no single region is the figure
    the largest enclosed region is often a background-coloured hole between an arm and the body, not the figure

**What replaced it: topology, and colour only to make "connected" exact.** A painted background and a painted figure
still differ in one respect that no amount of colour variety removes: **the background is what is connected to the
frame.** So the figure is the complement of the frame-connected set. Quantising first is what makes "connected" exact
rather than "colour is close" -- five thousand distinct colours make every threshold wrong, while comparing labels is
exact.

**And the check comes from a picture already traced.** `trace.py` measured 373817 figure pixels out of 1025280 on
`Cache_7cef975685e2f0c2.png`, which is 36.5% of the page. The complement on that picture has to land near it, so the
tool is checked against a known answer rather than against a number invented here.

    python tools/quantise_trace.py --src "F:\\\\素材\\\\图\\\\16+\\\\illust_93258058_20250506_090736.jpg"
"""
import argparse
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project as project_mod

#: How many colours the picture is reduced to. **Twelve is a choice with a reason**: a cel-painted figure is built from
#: a base, one shadow and one highlight per material, so a picture with a figure and a background lands around ten.
PALETTE = 12

#: Long side of the working image. A silhouette needs no more, the product is drawn at 800x1280 anyway, and the full
#: 3485x6239 picture cost 34 s and 21.7 million labels to answer a question an 800-wide copy answers the same way.
MAX_SIDE = 1000

#: Below this share the background reached through the figure, so the two are connected at this palette and the rule
#: cannot apply. Above `MAX_FIGURE` the figure touches the frame -- a crop -- or the background never reaches the border.
MIN_FIGURE = 0.05
MAX_FIGURE = 0.85

#: How much of the complement may sit outside the largest blob before the enclosed set is not one shape.
#: **The two ends are measured, and the gap between them is what makes this a check rather than a wish**: on the three
#: pictures this was tried on the scattered share was 0.004%, 0.7% and 7.3%, and the 7.3% one is the picture whose
#: outline reads as a lump of background. **5% is the midpoint of a gap rather than one of its ends**, so it is a choice
#: and is written down as one.
MAX_SCATTER = 0.05


def load_and_quantise(path, n, max_side):
    from PIL import Image
    im = Image.open(path).convert('RGB')
    w, h = im.size
    s = min(1.0, float(max_side) / max(w, h))
    if s < 1.0:
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)
    q = im.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    w, h = q.size
    return list(q.get_flattened_data() if hasattr(q, 'get_flattened_data') else q.getdata()), w, h


def regions(labels, w, h):
    """Connected components of equal label, with whether each one touches the frame."""
    seen = bytearray(w * h)
    out = []
    for start in range(w * h):
        if seen[start]:
            continue
        lab = labels[start]
        stack = [start]
        seen[start] = 1
        px = []
        touches = False
        while stack:
            i = stack.pop()
            px.append(i)
            y, x = divmod(i, w)
            if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                touches = True
            if y > 0 and not seen[i - w] and labels[i - w] == lab:
                seen[i - w] = 1
                stack.append(i - w)
            if y < h - 1 and not seen[i + w] and labels[i + w] == lab:
                seen[i + w] = 1
                stack.append(i + w)
            if x > 0 and not seen[i - 1] and labels[i - 1] == lab:
                seen[i - 1] = 1
                stack.append(i - 1)
            if x < w - 1 and not seen[i + 1] and labels[i + 1] == lab:
                seen[i + 1] = 1
                stack.append(i + 1)
        out.append({'label': lab, 'pixels': px, 'touches': touches})
    out.sort(key=lambda r: -len(r['pixels']))
    return out


def figure_mask(regs, w, h):
    """The figure is whatever the frame cannot reach.

    **Interior holes come along for free, and that is correct**: the gap between an arm and the body is enclosed by the
    figure, so it belongs inside the silhouette. A gap that opens to the frame is not enclosed and is background.
    """
    bg = bytearray(w * h)
    for r in regs:
        if r['touches']:
            for i in r['pixels']:
                bg[i] = 1
    return [bytearray(1 if not bg[y * w + x] else 0 for x in range(w)) for y in range(h)]


def largest_component(mask, w, h):
    """Keep the biggest 4-connected blob, and say how much was left behind.

    **The complement collects every pixel the background could not reach**, and quantisation noise puts thousands of
    isolated ones in it. `boundary()` starts at the topmost-leftmost set pixel, so on a noisy mask it starts on a stray
    dot, walks four steps and stops -- 5 boundary pixels for a mask covering 41% of the page. **The walk was never the
    problem; what it was pointed at was.**
    """
    seen = bytearray(w * h)
    best = None
    for start in range(w * h):
        if seen[start] or not mask[start // w][start % w]:
            continue
        stack = [start]
        seen[start] = 1
        comp = []
        while stack:
            i = stack.pop()
            comp.append(i)
            y, x = divmod(i, w)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w:
                    j = ny * w + nx
                    if not seen[j] and mask[ny][nx]:
                        seen[j] = 1
                        stack.append(j)
        if best is None or len(comp) > len(best):
            best = comp
    if not best:
        return None, 0, 0
    kept = [bytearray(w) for _ in range(h)]
    for i in best:
        kept[i // w][i % w] = 1
    return kept, len(best), sum(len(row) and sum(row) for row in mask)


def print_widths(mask, w, h):
    """How wide the figure is at a set of heights, in units of its own height.

    **This is the measurement the drawing needs and the silhouette can give.** A rig gives bone positions, and a bone is
    a point; how wide the trunk is at the shoulder came out of the drawing as a fault -- a clavicle standing in for a
    chest, thick enough to read as a spike. A silhouette is a width at every height by construction.
    """
    rows = [y for y in range(h) if any(mask[y])]
    if not rows:
        return
    top, bottom = rows[0], rows[-1]
    span = float(bottom - top + 1)
    print()
    print('  width of the figure at each height, in units of its own height:')
    print('    %-8s %8s %8s  %s' % ('height', 'width', 'px', ''))
    for frac in (0.11, 0.16, 0.19, 0.22, 0.26, 0.29, 0.33, 0.36, 0.40, 0.45, 0.51, 0.57, 0.65, 0.78, 0.90):
        y = top + int(frac * span)
        if y > bottom:
            continue
        row = mask[y]
        try:
            lo = row.index(1)
            hi = w - 1 - row[::-1].index(1)
        except ValueError:
            print('    %-8.2f %8s %8s  empty' % (frac, '-', '-'))
            continue
        print('    %-8.2f %8.3f %8d  %s' % (frac, (hi - lo + 1) / span, hi - lo + 1,
                                           '#' * max(1, int(40 * (hi - lo + 1) / float(w)))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', default=r'E:\DaShaoHuo\cache\trace-quant.json')
    ap.add_argument('--png', default=r'E:\DaShaoHuo\cache\trace-quant.png')
    ap.add_argument('--colours', type=int, default=PALETTE)
    ap.add_argument('--max-side', type=int, default=MAX_SIDE)
    ap.add_argument('--render', action='store_true')
    ap.add_argument('--widths', action='store_true')
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    if not src.exists():
        print('  missing: %s' % src)
        return 1
    labels, w, h, = load_and_quantise(src, args.colours, args.max_side)
    total = w * h
    print('  %s  %dx%d  reduced to %d colours' % (src.name, w, h, args.colours))

    regs = regions(labels, w, h)
    print('  %d regions; the ten largest:' % len(regs))
    print('    %-7s %-10s %8s  %s' % ('label', 'share', 'pixels', 'touches frame'))
    for r in regs[:10]:
        print('    %-7d %-10.3f %8d  %s' % (r['label'], len(r['pixels']) / float(total), len(r['pixels']),
                                            'yes' if r['touches'] else 'no'))

    mask = figure_mask(regs, w, h)
    n = sum(sum(row) for row in mask)
    share = n / float(total)
    print()
    print('  figure = the complement of what the frame reaches: %d px, %.1f%% of the page' % (n, 100 * share))
    if share < MIN_FIGURE:
        print('  the background reached through the figure, so the two are connected at this palette.')
        print('  topological separation cannot apply -- refusing rather than guessing.')
        return 2
    if share > MAX_FIGURE:
        print('  almost the whole page is enclosed, so the figure touches the frame or the background does not.')
        print('  that is a crop, not a figure -- refusing rather than guessing.')
        return 2

    mask, kept, before = largest_component(mask, w, h)
    if mask is None:
        print('  the complement is empty')
        return 1
    bx0, by0, bx1, by1 = w, h, 0, 0
    for y in range(h):
        row = mask[y]
        if any(row):
            bx0 = min(bx0, row.index(1))
            by0 = min(by0, y)
            by1 = y
            bx1 = max(bx1, w - 1 - row[::-1].index(1))
    print('  largest blob: %d px, %.1f%% of the page, box (%d, %d, %d, %d)'
          % (kept, 100.0 * kept / total, bx0, by0, bx1, by1))
    scatter = (before - kept) / float(before) if before else 0.0
    print('  scattered outside it: %d px, %.1f%% of the complement' % (before - kept, 100.0 * scatter))
    if scatter > MAX_SCATTER:
        print('  the enclosed set is not one shape at this palette: too much of it is scattered.')
        print('  the palette merged the figure with the background, so an outline from it would be a lump.')
        print('  refusing rather than guessing.')
        return 2

    # The mask's boundary -- the same Moore walk `trace.py` uses, on a mask from a different source.
    import trace as silhouette
    if args.widths:
        print_widths(mask, w, h)
    ring = silhouette.boundary(mask, w, h)
    print('  boundary pixels: %d' % len(ring))
    if not ring:
        print('  no boundary found')
        return 1
    half = len(ring) // 2
    simple = silhouette.douglas_peucker(ring[:half + 1], 2.2) + silhouette.douglas_peucker(ring[half:], 2.2)[1:]
    print('  after simplification: %d points' % len(simple))

    proj = project_mod.Project(width=800, height=1280, title='quantised trace')
    s = min(720.0 / w, 1200.0 / h)
    ox = (800 - w * s) / 2.0
    oy = (1280 - h * s) / 2.0
    pts = [(ox + x * s, oy + y * s) for x, y in simple]
    pts.append(pts[0])
    rec = core.stroke_record(pts, 'fine', seed=11, resolution=10,
                            width_profile=[3.0] * (10 * (len(pts) - 1) + 1))
    proj.add_stroke(rec, stage='line', layer='figure', note='quantised region boundary')
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project_mod.save_project(proj, str(out))
    print('  written to %s' % out)
    if args.render:
        import subprocess
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', args.png],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % args.png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
