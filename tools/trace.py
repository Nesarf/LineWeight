"""Trace a silhouette out of a picture and turn it into strokes.

**Why a silhouette first and not the line art.** The reference is a coloured illustration, so what it contains is flat
colour regions rather than ink on paper. A line extraction on it finds the hair mass and the clothing, and skeletonising
those gives the spine of a dark blob -- which is not a drawing of anything. **The silhouette is the one structure the
picture genuinely has**: the boundary between the figure and the paper behind her. Every reference book in `learn/` says
the same order, initial shape then detail, and the chibi article makes the silhouette itself the test.

**How the boundary is found.** The picture has a white ground. So "figure" is "not near-white", and the boundary is the
outer edge of that set. That is not a general solution to segmentation -- it works here because the ground is genuinely
white, and the code says so rather than pretending otherwise.

**And why the outline is simplified rather than followed.** A pixel boundary has a step on every pixel, and a stroke made
of those is a staircase. Douglas-Peucker removes every point whose absence changes the shape by less than a tolerance,
which is exactly the operation that turns a boundary into a line somebody would draw.

    python tools/trace.py                    # trace, write the project, report
    python tools/trace.py --render           # and render it
"""
import argparse
import math
import pathlib
import subprocess
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project as project_mod

SRC = pathlib.Path(r'F:\素材\图\16+\Cache_7cef975685e2f0c2.png')
OUT = pathlib.Path(r'E:\DaShaoHuo\cache\trace-silhouette.json')
PNG = pathlib.Path(r'E:\DaShaoHuo\cache\trace-silhouette.png')
#: A pixel counts as ground when all three channels are this close to white. The reference is drawn on pure white, so the
#: gap between paper and figure is large -- 236 was chosen by looking at the histogram, not by taste.
GROUND = 236


def load_mask(path):
    """The figure as a boolean mask, and the picture's own size."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    w, h = im.size
    px = im.load()
    mask = [[False] * w for _ in range(h)]
    for y in range(h):
        row = mask[y]
        for x in range(w):
            r, g, b = px[x, y]
            row[x] = not (r > GROUND and g > GROUND and b > GROUND)
    return mask, w, h


def largest_component(mask, w, h):
    """Keep the biggest connected blob. **Scattered marks and an antialiased fringe are not the figure**, and a trace
    that follows them produces hundreds of specks."""
    seen = [[False] * w for _ in range(h)]
    best, best_n = None, 0
    for sy in range(h):
        for sx in range(w):
            if not mask[sy][sx] or seen[sy][sx]:
                continue
            stack = [(sx, sy)]
            seen[sy][sx] = True
            comp = []
            while stack:
                x, y = stack.pop()
                comp.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(comp) > best_n:
                best, best_n = comp, len(comp)
    keep = [[False] * w for _ in range(h)]
    if best:
        for x, y in best:
            keep[y][x] = True
    return keep, best_n


def boundary(mask, w, h):
    """The outer boundary of a blob, as a closed clockwise walk.

    **Moore-neighbour tracing.** Walk the edge keeping the blob on one hand; the walk is closed when it returns to the
    first pixel facing the first direction. That gives one ordered ring rather than four unordered edges, which is what
    makes it usable as a stroke.
    """
    start = None
    for y in range(h):
        for x in range(w):
            if mask[y][x]:
                start = (x, y)
                break
        if start:
            break
    if not start:
        return []
    # the eight neighbours, clockwise from east
    dirs = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    ring = [start]
    prev_dir = 6           # came from the north, so start looking north-west
    cur = start
    for _ in range(w * h * 4):
        found = False
        for k in range(8):
            d = (prev_dir + 6 + k) % 8      # turn left first: keeps the blob on the right
            dx, dy = dirs[d]
            nx, ny = cur[0] + dx, cur[1] + dy
            if 0 <= nx < w and 0 <= ny < h and mask[ny][nx]:
                ring.append((nx, ny))
                cur = (nx, ny)
                prev_dir = d
                found = True
                break
        if not found:
            break
        if cur == start and len(ring) > 4:
            break
    return ring


def douglas_peucker(points, tol):
    """Keep the points that carry the shape."""
    if len(points) < 3:
        return points
    ax, ay = points[0]
    bx, by = points[-1]
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy)
    best_i, best_d = 0, -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if norm == 0:
            d = math.hypot(px - ax, py - ay)
        else:
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
        if d > best_d:
            best_i, best_d = i, d
    if best_d <= tol:
        return [points[0], points[-1]]
    left = douglas_peucker(points[:best_i + 1], tol)
    right = douglas_peucker(points[best_i:], tol)
    return left[:-1] + right


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=str(SRC), help='the picture to trace')
    ap.add_argument('--out', default=str(OUT), help='where to write the project')
    ap.add_argument('--png', default=str(PNG), help='where to render, with --render')
    ap.add_argument('--render', action='store_true')
    ap.add_argument('--tol', type=float, default=2.2, help='simplification tolerance in source pixels')
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    if not src.exists():
        print('  missing: %s' % src)
        return 1
    mask, w, h = load_mask(src)
    keep, area = largest_component(mask, w, h)
    print('  source %s  %dx%d' % (src.name, w, h))
    print('  figure pixels: %d  (%.1f%% of the page)' % (area, 100.0 * area / (w * h)))
    ring = boundary(keep, w, h)
    print('  boundary pixels: %d' % len(ring))
    if not ring:
        print('  no boundary found')
        return 1

    # **The ring is closed, so it is simplified in two halves** -- Douglas-Peucker works on an open polyline, and
    # feeding it a closed ring would keep the first and last points only because they are the same point.
    half = len(ring) // 2
    a = douglas_peucker(ring[:half + 1], args.tol)
    b = douglas_peucker(ring[half:], args.tol)
    simple = a + b[1:]
    print('  after simplification: %d points' % len(simple))

    # Scale into the page, leaving a margin, and flip nothing -- both are screen coordinates already.
    proj = project_mod.Project(width=800, height=1280, title='traced silhouette')
    sx = 720.0 / w
    sy = 1200.0 / h
    s = min(sx, sy)
    ox = (800 - w * s) / 2.0
    oy = (1280 - h * s) / 2.0
    pts = [(ox + x * s, oy + y * s) for x, y in simple]
    pts.append(pts[0])
    rec = core.stroke_record(pts, 'fine', seed=7, resolution=10,
                             width_profile=[3.0] * (10 * (len(pts) - 1) + 1))
    proj.add_stroke(rec, stage='line', layer='silhouette', note='traced outer boundary')

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project_mod.save_project(proj, str(out))
    print('  written to %s' % out)

    if args.render:
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', str(args.png)],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % args.png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
