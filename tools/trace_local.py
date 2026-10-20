"""Trace the edges inside a box, rather than the silhouette of the whole figure.

**Why a second tool.** The silhouette tracer answers "what shape is the figure". It cannot answer "where are the fingers",
because fingers lie against cloth and the outer boundary passes outside them. **A hand is drawn with lines that sit
inside the body**, so a tracer for hands has to look for edges rather than for the boundary of a region.

**What an edge is here.** The place where brightness changes sharply. That is the one definition that works on a flat
coloured illustration: the line around a finger is a dark stroke on a light fill, so the gradient across it is large
while the fill itself is flat.

**And why the result is chained rather than dotted.** Thresholding a gradient gives scattered pixels, which as strokes
become a speckle. So the pixels are grouped by neighbouring direction -- a rough continuity -- and each group becomes one
stroke. **That is not a skeletonisation, and the difference matters**: a skeleton would need thinning, which this project
does not have and which makes a one-pixel line that no pen draws.

    python tools/trace_local.py --src "F:\\素材\\图\\涩涩！\\mmk.jpg" --box 120 480 320 780
"""
import argparse
import math
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project as project_mod

#: An edge pixel is one whose brightness differs from a neighbour by more than this. The illustrations are painted with
#: soft gradients, so 26 was picked by looking at a histogram rather than by taste -- below it the shading of skin
#: qualifies, above it nothing on the hand does.
EDGE = 34


def load_gray(path, blur=2):
    """灰度，然后在小邻域里取平均。

    **模糊不是装饰。** 不做模糊时，一条线上每一个抗锯齿的台阶都算边缘，于是**画出来的一条线会读成两条平行的模糊边界**，
    每一条各自成为一笔 —— 那就是碎点的样子。先平均，就只有「亮度过好几个像素才变」的地方活下来，
    而那些才是有人真正下过笔的位置。
    """
    from PIL import Image, ImageFilter
    im = Image.open(path).convert('L')
    if blur:
        im = im.filter(ImageFilter.BoxBlur(blur))
    w, h = im.size
    return list(im.getdata()), w, h


MIN_CHAIN = 40


def edges(gray, w, h, box):
    """The edge pixels inside a box, as (x, y) in the source's coordinates."""
    x0, y0, x1, y1 = box
    out = []
    for y in range(max(1, y0), min(h - 1, y1)):
        base = y * w
        for x in range(max(1, x0), min(w - 1, x1)):
            v = gray[base + x]
            if (abs(v - gray[base + x + 1]) > EDGE or abs(v - gray[base + x - 1]) > EDGE or
                    abs(v - gray[base - w + x]) > EDGE or abs(v - gray[base + w + x]) > EDGE):
                out.append((x, y))
    return out


def chain(points, gap):
    """Group nearby edge pixels into runs.

    **Greedy nearest-neighbour chaining.** Start from a pixel, then repeatedly hop to the nearest unused pixel within
    `gap`. The runs are what a pen would draw; the pixels a chain leaves behind are the speckle the threshold produced.
    """
    pts = list(points)
    index = {}
    for i, (x, y) in enumerate(pts):
        index.setdefault((x // gap, y // gap), []).append(i)
    used = [False] * len(pts)
    runs = []
    for i in range(len(pts)):
        if used[i]:
            continue
        used[i] = True
        run = [pts[i]]
        cur = i
        while True:
            cx, cy = pts[cur]
            best, best_d = -1, gap * gap + 1
            gx, gy = cx // gap, cy // gap
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for j in index.get((gx + ox, gy + oy), ()):
                        if used[j]:
                            continue
                        dx, dy = pts[j][0] - cx, pts[j][1] - cy
                        d = dx * dx + dy * dy
                        if d < best_d:
                            best, best_d = j, d
            if best < 0:
                break
            used[best] = True
            run.append(pts[best])
            cur = best
        if len(run) >= MIN_CHAIN:            # shorter runs are noise, and a pen does not draw a four-pixel line
            runs.append(run)
    runs.sort(key=len, reverse=True)
    return runs


def douglas_peucker(points, tol):
    if len(points) < 3:
        return points
    ax, ay = points[0]
    bx, by = points[-1]
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy)
    best_i, best_d = 0, -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        d = math.hypot(px - ax, py - ay) if norm == 0 else abs(dy * px - dx * py + bx * ay - by * ax) / norm
        if d > best_d:
            best_i, best_d = i, d
    if best_d <= tol:
        return [points[0], points[-1]]
    return douglas_peucker(points[:best_i + 1], tol)[:-1] + douglas_peucker(points[best_i:], tol)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--box', nargs=4, type=int, required=True, metavar=('X0', 'Y0', 'X1', 'Y1'))
    ap.add_argument('--out', default=r'E:\DaShaoHuo\cache\trace-local.json')
    ap.add_argument('--png', default=r'E:\DaShaoHuo\cache\trace-local.png')
    ap.add_argument('--gap', type=int, default=7)
    ap.add_argument('--tol', type=float, default=1.5)
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    if not src.exists():
        print('  missing: %s' % src)
        return 1
    gray, w, h = load_gray(src)
    x0, y0, x1, y1 = args.box
    print('  source %s  %dx%d  box %s' % (src.name, w, h, tuple(args.box)))
    pts = edges(gray, w, h, (x0, y0, x1, y1))
    print('  edge pixels: %d' % len(pts))
    runs = chain(pts, args.gap)
    print('  chains: %d  (longest %d px)' % (len(runs), len(runs[0]) if runs else 0))

    proj = project_mod.Project(width=800, height=800, title='local trace')
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    s = min(760.0 / bw, 760.0 / bh)
    ox = (800 - bw * s) / 2.0
    oy = (800 - bh * s) / 2.0
    kept = 0
    for n, run in enumerate(runs[:60]):
        simple = douglas_peucker(run, args.tol)
        if len(simple) < 3:
            continue
        pts_page = [(ox + (x - x0) * s, oy + (y - y0) * s) for x, y in simple]
        rec = core.stroke_record(pts_page, 'fine', seed=n, resolution=8,
                                 width_profile=[2.0] * (8 * (len(pts_page) - 1) + 1))
        proj.add_stroke(rec, stage='line', layer='local', note='chain %d of %d' % (n + 1, len(runs)))
        kept += 1
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project_mod.save_project(proj, str(out))
    print('  strokes written: %d  -> %s' % (kept, out))
    if args.render:
        import subprocess
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', args.png],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % args.png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
