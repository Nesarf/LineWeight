"""Stage four: the same value, more colour where the drawing needs it.

**What makes this a stage and not a slider.** Stage three puts one hue and one saturation over everything, which is what
"colouring" means at its cheapest. The recording's last stage -- 56 per cent of its length -- keeps the value fixed and
**raises saturation unevenly**: a face stays soft while a skirt deepens. So the difference between these two stages is
not an amount, it is whether the amount is the same everywhere.

**The rule, and why this one.** Saturation rises as the region gets darker, by a fraction of how far below mid grey it
sits. That is the arrangement most cel work uses and it is also the one that survives the guard: a dark region gains
colour without gaining light, because the tint keeps Rec. 709 luminance to the digit.

    python tools/refine.py --src colour.json --out refined.json --gain 0.7
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


def saturation(rgb):
    r, g, b = (c / 255.0 for c in rgb)
    hi, lo = max(r, g, b), min(r, g, b)
    return 0.0 if hi <= 0 else (hi - lo) / hi


def tinted(target, hue, sat):
    """A colour of that hue and saturation whose Rec. 709 luminance is `target` -- the same rule stage three uses."""
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
    ap.add_argument('--gain', type=float, default=0.7, help='how much darker regions gain over lighter ones')
    ap.add_argument('--lift', type=float, default=0.35, help='how much every region gains, the stage\'s climbing')
    ap.add_argument('--limit', type=float, default=0.05)
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.src).read_text(encoding='utf-8'))
    before_sat, after_sat, drifts = [], [], []
    for mark in doc.get('marks', []):
        if mark.get('kind') != 'fill':
            continue
        appearance = mark.get('appearance') or {}
        colour = appearance.get('fill')
        if not colour:
            continue
        rgb = parse_hex(colour)
        L = luminance(rgb)
        hue, sat, _v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))
        # **Darker gets more colour, lighter gets less -- and everything gains something.** Without the lift the rule
        # moved the mean saturation *down* (0.3156 to 0.2968) because the pale regions are the majority and losing a
        # share of a small number beats gaining a share of a large one. The procedure's own acceptance is that the
        # saturation keeps climbing through this stage, so the lift is what makes the stage a refinement rather than a
        # redistribution.
        target = sat * (1.0 + args.lift + args.gain * (0.5 - L) * 2.0)
        target = max(0.0, min(1.0, target))
        new_rgb = tinted(L, hue, target)
        appearance['fill'] = to_hex(new_rgb)
        after = luminance(parse_hex(appearance['fill']))
        before_sat.append(sat)
        after_sat.append(saturation(new_rgb))
        if L > 0:
            drifts.append(abs(after - L) / L)

    pathlib.Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    if not drifts:
        print('  no filled marks')
        return 1
    worst = max(drifts)
    print('  %d regions refined' % len(drifts))
    print('  saturation: mean %.4f -> %.4f' % (sum(before_sat) / len(before_sat), sum(after_sat) / len(after_sat)))
    print('  value drift: mean %.5f   worst %.5f   limit %.4f' % (sum(drifts) / len(drifts), worst, args.limit))
    if worst <= args.limit:
        print('  within the limit: colour was redistributed, the light was not')
        return 0
    print('  over the limit: this stage moved the light')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
