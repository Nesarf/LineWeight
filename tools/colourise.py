"""Stage three: put hue and saturation back, and prove the value did not move.

**This is the stage the whole procedure is guarded by.** The recording puts the colour back over a finished grey pass,
and the measurement that separates "colouring" from "redrawing the light" is that mean lightness holds while
saturation climbs. So this tool has one job and one number: **apply a hue and a saturation, keep every region's
Rec. 709 luminance to the digit, and report the drift.**

**Why the drift is not zero by construction.** A hue and a saturation chosen in the usual way, with the value taken as
the top of the cone, gives a colour whose luminance is not the one asked for -- the channels weigh differently. So the
result is scaled, or mixed toward white, until its luminance equals the target. **The residual is what the report
prints**, and it is the reason the report exists rather than the tool simply trusting itself.

    python tools/colourise.py --src grey.json --out colour.json --hue 0.06 --sat 0.35
"""
import argparse
import colorsys
import json
import pathlib

WR = 0.2126
WG = 0.7152
WB = 0.0722


def parse_hex(text):
    text = text.lstrip('#')
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def to_hex(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def luminance(rgb):
    r, g, b = (c / 255.0 for c in rgb)
    return WR * r + WG * g + WB * b


def tinted(target, hue, sat):
    """A colour of the given hue and saturation **whose Rec. 709 luminance is `target`**.

    **Scaled down, or mixed toward white, never clipped.** Clipping changes the luminance, which is the one thing this
    stage is not allowed to touch; a scale or a mix is linear in the channels, so the luminance lands exactly where it
    was asked to.
    """
    r, g, b = colorsys.hsv_to_rgb(hue, sat, 1.0)
    cur = WR * r + WG * g + WB * b
    if cur <= 1e-9:
        return (target * 255.0,) * 3
    if target <= cur:
        k = target / cur
        return (r * k * 255.0, g * k * 255.0, b * k * 255.0)
    t = (target - cur) / (1.0 - cur)
    return ((r + (1.0 - r) * t) * 255.0, (g + (1.0 - g) * t) * 255.0, (b + (1.0 - b) * t) * 255.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--hue', type=float, default=0.05, help='0 to 1 around the colour wheel')
    ap.add_argument('--sat', type=float, default=0.30, help='0 to 1; the recording goes from 0.00 to about 0.16')
    ap.add_argument('--limit', type=float, default=0.05, help='the drift the stage allows, as a fraction')
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.src).read_text(encoding='utf-8'))
    drifts = []
    for mark in doc.get('marks', []):
        if mark.get('kind') != 'fill':
            continue
        appearance = mark.get('appearance') or {}
        colour = appearance.get('fill')
        if not colour:
            continue
        before = luminance(parse_hex(colour))
        rgb = tinted(before, args.hue, args.sat)
        appearance['fill'] = to_hex(rgb)
        after = luminance(parse_hex(appearance['fill']))
        if before > 0:
            drifts.append(abs(after - before) / before)

    pathlib.Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    if not drifts:
        print('  no filled marks')
        return 1
    worst = max(drifts)
    mean = sum(drifts) / len(drifts)
    print('  hue %.3f   saturation %.3f' % (args.hue, args.sat))
    print('  value drift: mean %.4f   worst %.4f   limit %.4f' % (mean, worst, args.limit))
    if worst <= args.limit:
        print('  within the limit: the colour went on and the light stayed where it was')
        return 0
    print('  over the limit: this stage moved the light, which is the stage before it to fix')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
