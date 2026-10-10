"""How wide is a colour boundary, in a picture where the boundary is a colour step rather than a line.

Two things this has to survive, and both are reasons to calibrate before measuring anything:

1. **A shadow boundary is a change of COLOUR, not of brightness.** Two colours can differ a lot in hue and barely in
   luminance, so a luminance-only edge detector misses exactly the boundaries this is looking for.
2. **These images are JPEG.** Compression spreads an edge over a pixel or two whatever it was painted as, so the
   measurement has a floor that is a property of the format and not of the art. The floor is measured, not assumed.

The instrument: walk a line across an edge, find where the colour changes, and count how many pixels it takes to get
from 10% to 90% of the change. Calibrated on synthetic edges of known width first.
"""
import math
from PIL import Image


def _as_float(image, box=None):
    im = image.convert('RGB')
    if box:
        im = im.crop(box)
    return im


def ramp_profile(pixels, i, j):
    """The colour distance between two pixels, in a space where hue counts."""
    a, b = pixels[i], pixels[j]
    # a simple opponent space: luminance plus the two chroma differences. Cheap, and it does not collapse
    # a red/green boundary into nothing the way a pure luma difference does.
    ya = 0.299 * a[0] + 0.587 * a[1] + 0.114 * a[2]
    yb = 0.299 * b[0] + 0.587 * b[1] + 0.114 * b[2]
    return math.sqrt((ya - yb) ** 2 + ((a[0] - a[2]) - (b[0] - b[2])) ** 2 + ((a[1] - (a[0] + a[2]) / 2)
                                                                             - (b[1] - (b[0] + b[2]) / 2)) ** 2)


def transition_width(line, peak, span=40, lo=0.1, hi=0.9):
    """Pixels taken to cross from `lo` to `hi` of the step, measured on the COLOUR and not on its derivative.

    **The first version walked outward from the gradient peak while the per-pixel difference stayed above a fraction
    of the peak, and that is a measurement of the derivative rather than of the step.** On a wide ramp each pixel's
    difference is small, so the walk stopped almost immediately: calibration read a true 1-pixel edge as 2 and a
    painted 20-pixel ramp as 2 as well. The two are not the same thing and the calibrator said so.

    This walks the colour itself from the edge position until it is within `lo` of the plateau on one side and within
    `hi` of the plateau on the other. `span` is how far out the plateaus are sampled, and it must be at least as wide
    as the widest transition being looked for.
    """
    n = len(line)
    left = max(0, peak - span)
    right = min(n - 1, peak + span)
    a, b = line[left], line[right]
    total = ramp_profile(line, left, right)
    if total <= 0:
        return None
    l = peak
    while l > left and ramp_profile(line, l, right) < (1.0 - lo) * total:
        l -= 1
    r = peak
    while r < right and ramp_profile(line, left, r) < hi * total:
        r += 1
    if r <= l:
        return None
    return r - l


def edge_widths(image, stride=3, threshold=24.0):
    """The transition width at every strong edge found on a grid of rows and columns."""
    im = _as_float(image)
    w, h = im.size
    px = im.load()
    widths = []
    for x in range(2, w - 2, stride):
        col = [px[x, y] for y in range(h)]
        d = [ramp_profile(col, i, i + 1) for i in range(h - 1)]
        for i in range(2, len(d) - 2):
            if d[i] >= threshold and d[i] >= d[i - 1] and d[i] >= d[i + 1]:
                # the step across this edge, measured well to either side of the peak
                before = ramp_profile(col, max(0, i - 3), min(h - 1, i + 3))
                if before < threshold:
                    continue
                tw = transition_width(col, i)
                if tw:
                    widths.append(tw)
    for y in range(2, h - 2, stride):
        row = [px[x, y] for x in range(w)]
        d = [ramp_profile(row, i, i + 1) for i in range(w - 1)]
        for i in range(2, len(d) - 2):
            if d[i] >= threshold and d[i] >= d[i - 1] and d[i] >= d[i + 1]:
                before = ramp_profile(row, max(0, i - 3), min(w - 1, i + 3))
                if before < threshold:
                    continue
                tw = transition_width(row, i)
                if tw:
                    widths.append(tw)
    return widths


def calibrate():
    """Synthetic edges of known width, so the measurement has a floor rather than a hope."""
    from PIL import ImageDraw
    out = {}
    for shape, painted in (('step', None), ('2px', 2), ('6px', 6), ('20px', 20)):
        im = Image.new('RGB', (240, 80), (240, 235, 225))
        d = ImageDraw.Draw(im)
        # a colour step, not a brightness step: two colours of similar luminance
        left, right = (235, 120, 110), (110, 150, 235)
        if painted is None:
            d.rectangle([0, 0, 120, 80], fill=left)
            d.rectangle([121, 0, 240, 80], fill=right)
        else:
            d.rectangle([0, 0, 120, 80], fill=left)
            d.rectangle([120 + painted, 0, 240, 80], fill=right)
            for k in range(painted):
                t = (k + 1) / (painted + 1)
                mix = tuple(int(left[c] + (right[c] - left[c]) * t) for c in range(3))
                d.line([(120 + k, 0), (120 + k, 80)], fill=mix)
        ws = edge_widths(im, stride=1, threshold=12.0)
        out[shape] = (len(ws), (sum(ws) / len(ws)) if ws else 0.0, sorted(ws)[len(ws) // 2] if ws else 0)
    return out


if __name__ == '__main__':
    print('=== calibration on synthetic colour steps of known width ===')
    print('%-8s %8s %10s %10s' % ('painted', 'edges', 'mean', 'median'))
    for k, (n, mean, med) in calibrate().items():
        print('%-8s %8d %10.2f %10.1f' % (k, n, mean, med))
