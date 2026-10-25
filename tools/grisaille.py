"""Stage two: the value pass. Every colour collapses to one grey per region, and nothing else may move afterwards.

**Why this is a separate stage and not a step inside shading.** The procedure this project follows was measured off a
recording: the artist laid a desaturated grey over the whole figure, and from that moment **the value was fixed and only
hue and saturation changed for the other 133 seconds**. Measured on that recording, mean lightness went 184.3 to 175.3
while saturation went 17.8 to 40.1 -- **lightness moved 4.85 per cent, saturation 126 per cent**. A tool that lets a
colour change move lightness cannot reproduce that, so this stage writes the value down as the only thing a region has,
and the stage after it is only allowed to read it.

**What "value" means here.** Rec. 709 luminance of the region's colour -- the same weighting a monitor's greyscale
uses. The number is kept, the colour is thrown away, and a colour cannot come back without going through it.

    python tools/grisaille.py --src in.json --out grey.json
"""
import argparse
import json
import pathlib

#: Rec. 709 weights. **Not an average**, because the eye does not see the channels equally and a face is mostly the
#: green channel's business.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.src).read_text(encoding='utf-8'))
    values = []
    filled = 0
    for mark in doc.get('marks', []):
        if mark.get('kind') != 'fill':
            continue
        # **A fill's colour lives under `fill`, not `colour`** -- a stroke's colour is `appearance.colour`, and the two
        # kinds of mark keep the field under different names. Reading the wrong one found nothing at all rather than
        # finding the wrong value, which is the good kind of mistake.
        appearance = mark.get('appearance') or {}
        colour = appearance.get('fill')
        if not colour:
            continue
        rgb = parse_hex(colour)
        L = luminance(rgb)
        # **The grey is the value, and it is the whole of what this region now says.** Two regions that had different
        # colours but the same value become the same patch of grey, which is the point: the pass is about what is light
        # and what is dark, and about nothing else.
        grey = int(round(L * 255))
        appearance['fill'] = to_hex((grey, grey, grey))
        values.append(L)
        filled += 1

    pathlib.Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    if not values:
        print('  no filled marks: nothing to put a value on')
        return 1
    mean = sum(values) / len(values)
    lo, hi = min(values), max(values)
    print('  %d filled regions collapsed to one value each' % filled)
    print('  light: mean %.4f   min %.4f   max %.4f' % (mean, lo, hi))
    print('  saturation: 0.0000 by construction -- every colour here is r = g = b')
    print('  written to %s' % args.out)
    print()
    print('  this file is the value the rest of the drawing is not allowed to move.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
