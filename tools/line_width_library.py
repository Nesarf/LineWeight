"""What width does a drawing's ink actually occupy, in units of the figure rather than of the page?

**Why not pixels.** A width in pixels says nothing about a drawing: the same artist's line at 2000 pixels tall and at
4000 is the same line, and the number doubles. The only scale-free quote is against something in the picture, and the
figure's own height is the obvious one -- the corpus already uses head heights for proportion.

**Why the figure's height and not the page's.** A page is a rectangle the artist chose for layout; a figure is what the
drawing is of. The bounding box of the ink is the figure's extent, so `figure height` is read off the ink itself and needs
no other input.

**The measurement is a distance transform, not a stroke model.** Every skeleton pixel is half a width from the nearest
background, so twice the transform is the line's width there, and the median over a whole drawing's skeleton is the
drawing's typical width. That is a property of the ink and nothing else -- no brush, no spacing, no pressure model.

    python tools/line_width_library.py --glob "E:\\DaShaoHuo\\downloads\\pixiv-senga\\*.jpg" --limit 12
"""
import argparse
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import copy_linework as cl
from scipy import ndimage

#: Ink is anything darker than this, as 0..255. A line drawing on paper has pale paper and a scanned pencil around 120 to
#: 180, so the threshold sits well above both and below the paper.
INK = 205

#: The head-to-height ratio the corpus uses, so a width can be quoted in head heights as well as in figure heights.
#: **It is an assumption, not a measurement for any particular picture.**
HEADS = 6.5


def ink_mask(gray):
    """The ink, with the page around it removed.

    **The paper is not always white.** A scanned drawing has a grey cast and a photographed one has a shadow, so the
    threshold is relative to the page's own brightness rather than absolute.
    """
    page = float(np.percentile(gray, 90))
    limit = min(INK, page - 25.0)
    return gray < limit


def figure_stats(mask):
    """The figure's extent **and the numbers that decide whether it is a character drawing at all**.

    **The bounding box of every ink pixel is not the figure.** A drawing with a decorative border or a dense background has
    ink at every edge of the page, so its box is the page, and every width divided by that box comes out too small. A
    corpus gathered by a search tag contains many such drawings: the one that exposed this had a small character in a white
    oval surrounded by cross-and-dot ornament.

    **The largest single mass of ink is the figure** in a character drawing, because head, body and hair are one connected
    shape while ornament is separate. Three numbers say whether that held:

    - `mass_share`, the largest mass over all the ink. A character drawing puts most of its ink in one shape.
    - `mass_height`, the largest mass's height over the picture's. A full figure, not a vignette.
    - `components`, how many separate masses of ink there are. An ornamented page has dozens.

    They are returned rather than enforced, so the caller can report why a drawing was refused instead of dropping it in
    silence.
    """
    labelled, count = ndimage.label(mask)
    stats = {'components': int(count), 'mass_share': 0.0, 'mass_height': 0.0, 'box': None}
    if count == 0:
        return stats
    sizes = np.bincount(labelled.ravel())
    sizes[0] = 0
    biggest = int(sizes.argmax())
    total = float(sizes.sum()) or 1.0
    mass = labelled == biggest
    rows = np.flatnonzero(mass.any(axis=1))
    cols = np.flatnonzero(mass.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return stats
    stats['mass_share'] = float(sizes[biggest]) / total
    stats['mass_height'] = float(rows[-1] - rows[0] + 1) / float(mask.shape[0])
    stats['box'] = (int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1]))
    return stats


def widths_of(path, long_side=1600, subpixel=True, regions=None):
    image = Image.open(path).convert('L')
    scale = min(1.0, long_side / float(max(image.size)))
    if scale < 1.0:
        image = image.resize((max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale))), Image.LANCZOS)
    gray = np.asarray(image, dtype=np.float32)
    mask = ink_mask(gray)
    stats = figure_stats(mask)
    if stats['box'] is None:
        return None
    height = stats['box'][1] - stats['box'][0] + 1

    # **The skeleton, so the width is sampled on the line rather than in the ink's interior.** Sampled anywhere in the
    # mask, a thick patch would contribute its middle and a hairline its own -- the two would not be comparable.
    skeleton = cl.thin(mask.astype(np.uint8)).astype(bool)
    ys, xs = np.nonzero(skeleton)
    if subpixel:
        widths = subpixel_widths(gray, mask, skeleton)
    else:
        distance = ndimage.distance_transform_edt(mask)
        widths = 2.0 * distance[skeleton]
    keep = widths > 0
    ys, xs, widths = ys[keep], xs[keep], widths[keep]
    if widths.size < 20:
        return None
    normalised = widths / height
    result = {
        'name': pathlib.Path(path).name,
        'size': image.size,
        'figure_height': height,
        'skeleton_px': int(widths.size),
        'median': float(np.median(normalised)),
        'p10': float(np.percentile(normalised, 10)),
        'p90': float(np.percentile(normalised, 90)),
        # **The three numbers that decide whether this is a character drawing**, carried out of the measurement so a
        # refusal can be reported with its reason rather than as a missing row.
        'mass_share': stats['mass_share'],
        'mass_height': stats['mass_height'],
        'components': stats['components'],
    }
    if regions:
        result['by_part'] = {part: assign(ys, xs, normalised, spans, image.size)
                             for part, spans in regions.items()}
    return result


def assign(ys, xs, widths, spans, size):
    """The widths of the skeleton points that fall inside one part's boxes.

    **A box, not a traced part.** Labelling which stroke is an eyelash would need a human or a model per stroke; a box
    says "this region of the picture is the eye" and lets every skeleton point inside answer for it. It is coarser than the
    convention's vocabulary and precise enough for the only question being asked -- whether two parts have different
    typical widths.
    """
    width_px, height_px = size
    inside = np.zeros(ys.shape, dtype=bool)
    for box in spans:
        x0, y0, x1, y1 = box
        inside |= ((xs >= x0 * width_px) & (xs <= x1 * width_px)
                   & (ys >= y0 * height_px) & (ys <= y1 * height_px))
    chosen = widths[inside]
    if chosen.size == 0:
        return None
    return {'count': int(chosen.size),
            'median': float(np.median(chosen)),
            'p10': float(np.percentile(chosen, 10)),
            'p90': float(np.percentile(chosen, 90))}


def subpixel_widths(gray, mask, skeleton, half=7):
    """The width at each skeleton pixel, **measured in ink rather than in whole pixels**.

    **Why the distance transform could not answer this.** On a two-pixel line it can only report a half pixel, so the
    measured widths of a drawing's strokes take a handful of values and `p90/median` comes out as 1.00 or 2.00 rather than
    as a number that could be compared with anything. The anti-aliased edge is where the information that was thrown away
    lives: a column that is forty per cent covered is four tenths of a pixel, and JPEG's soft edge carries exactly that.

    **Two directions, and the smaller one wins.** A stroke's true width is what a line drawn across it measures; measuring
    along a stroke instead gives its length. Taking the smaller of the row and column integrals is the cheap way to always
    land on the crossing direction without computing a normal -- wrong only at a junction, where both directions run along
    ink, and a junction is a small share of any drawing's skeleton.
    """
    page = float(np.percentile(gray, 90))
    ink_level = float(np.percentile(gray[mask], 10)) if mask.any() else 0.0
    span = max(page - ink_level, 1.0)
    coverage = np.clip((page - gray) / span, 0.0, 1.0)

    rows = np.cumsum(coverage, axis=0)
    rows = np.vstack([np.zeros((1, coverage.shape[1]), dtype=np.float64), rows])
    cols = np.cumsum(coverage, axis=1)
    cols = np.hstack([np.zeros((coverage.shape[0], 1), dtype=np.float64), cols])

    ys, xs = np.nonzero(skeleton)
    y0 = np.clip(ys - half, 0, coverage.shape[0])
    y1 = np.clip(ys + half + 1, 0, coverage.shape[0])
    x0 = np.clip(xs - half, 0, coverage.shape[1])
    x1 = np.clip(xs + half + 1, 0, coverage.shape[1])
    vertical = rows[y1, xs] - rows[y0, xs]
    horizontal = cols[ys, x1] - cols[ys, x0]
    return np.minimum(vertical, horizontal)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glob', required=True)
    ap.add_argument('--limit', type=int, default=12)
    ap.add_argument('--long-side', type=int, default=1600)
    ap.add_argument('--max-median', type=float, default=0.005,
                    help='reject a drawing whose typical width is this much of the figure height; half a per cent of a '
                         'figure is two hundred pixels of a two-thousand-pixel drawing, which is a filled area and not a '
                         'line. Needed because the corpus is a search result, not a curated set')
    ap.add_argument('--max-ratio', type=float, default=6.0,
                    help='reject a drawing whose p90 is this many times its median; a line drawing stays inside the '
                         'range the corpus measured, while a dark garment fills a whole region')
    ap.add_argument('--regions', default='',
                    help='a JSON file of {part: [[x0,y0,x1,y1], ...]} with the boxes as fractions of the image, so the '
                         'widths can be reported by part of the body rather than as one pooled number')
    # **The three tests for "is this a character drawing".** Without them the corpus is "the twenty-two I happened to
    # keep", which nobody else can reproduce; with them it is a rule anyone can run on the same folder and get the same
    # list, disagreements and all.
    ap.add_argument('--min-mass-share', type=float, default=0.40,
                    help='the largest connected mass of ink must be at least this share of all the ink')
    ap.add_argument('--min-mass-height', type=float, default=0.50,
                    help='and must span at least this share of the picture height, which excludes a vignette')
    ap.add_argument('--max-components', type=int, default=0,
                    help='**off by default, because the test was measured and it is wrong.** It was meant to exclude an '
                         'ornamented page, on the assumption that a character is one connected mass and ornament is not. '
                         'Running it on the corpus rejected 151 of 152 drawings as having 28 to 2212 separate masses: a '
                         'scanned pencil line is broken by the scan, by JPEG and by the artist lifting the pen, while a '
                         'decorative border is often one continuous field. Set it above zero only to see that for yourself')
    ap.add_argument('--manifest', default='',
                    help='write the accepted drawings and their numbers to this JSON file, so the set can be reproduced')
    args = ap.parse_args()

    regions = None
    if args.regions:
        regions = json.loads(pathlib.Path(args.regions).read_text(encoding='utf-8'))
        print('  parts: %s' % ', '.join(sorted(regions)))

    folder = pathlib.Path(args.glob).parent
    files = sorted(folder.glob(pathlib.Path(args.glob).name))[:args.limit]
    print('  %-26s %9s %9s %9s %9s' % ('file', 'median', 'p10', 'p90', 'p90/median'))
    rows = []
    rejected = []
    for path in files:
        try:
            result = widths_of(path, args.long_side, regions=regions)
        except Exception as problem:  # a corrupt or unusual file must not stop the survey
            print('  %-26s %s' % (path.name[:26], problem))
            continue
        if result is None:
            print('  %-26s (too little ink)' % path.name[:26])
            continue
        ratio = result['p90'] / max(result['median'], 1e-9)
        reason = None
        if result['mass_share'] < args.min_mass_share:
            reason = 'largest mass is only %.0f%% of the ink' % (100 * result['mass_share'])
        elif result['mass_height'] < args.min_mass_height:
            reason = 'largest mass spans only %.0f%% of the height' % (100 * result['mass_height'])
        elif args.max_components and result['components'] > args.max_components:
            reason = '%d separate masses of ink' % result['components']
        elif result['median'] > args.max_median:
            reason = 'typical width %.2f%% of the figure is a filled area' % (100 * result['median'])
        elif ratio > args.max_ratio:
            reason = 'p90/median is %.1f, which a line drawing does not reach' % ratio
        if reason:
            rejected.append((path.name, reason))
            continue
        rows.append(result)
        print('  %-26s %8.4f%% %8.4f%% %8.4f%% %9.2f'
              % (path.name[:26], 100 * result['median'], 100 * result['p10'],
                 100 * result['p90'], ratio))

    if rejected:
        print()
        print('  rejected %d of %d:' % (len(rejected), len(rejected) + len(rows)))
        for name, reason in rejected[:10]:
            print('    %-26s %s' % (name[:26], reason))
        if len(rejected) > 10:
            print('    ... %d more' % (len(rejected) - 10))

    # **One drawing is enough to report on.** The summary used to need two, which meant a single labelled drawing printed
    # its overall width and then silently skipped the by-part table -- the one output an experiment with one drawing is
    # for. Spread over a single sample is 1.0x and says so rather than being hidden.
    if rows:
        medians = np.array([r['median'] for r in rows])
        ratios = np.array([r['p90'] / max(r['median'], 1e-9) for r in rows])
        print()
        print('  %d drawings' % len(rows))
        print('  median width / figure height: median of medians %.4f%%   range %.4f%% .. %.4f%%   spread %.2fx'
              % (100 * np.median(medians), 100 * medians.min(), 100 * medians.max(),
                 medians.max() / max(medians.min(), 1e-9)))
        print('  p90/median within one drawing: median %.2f   range %.2f .. %.2f'
              % (np.median(ratios), ratios.min(), ratios.max()))
        print('  in head heights (assuming %s heads): typical line is %.3f%% of a head'
              % (HEADS, 100 * np.median(medians) * HEADS))

        if regions:
            # **The only question this table has to answer.** If two parts of a body do not have different typical widths,
            # then "what line for what part" is not a table at all and the whole exercise is a way of writing down a
            # number that carries no information. The threshold is a ratio of medians, so it does not depend on how large
            # the drawings are or on the units.
            pooled = {}
            for row in rows:
                for part, stats in (row.get('by_part') or {}).items():
                    if stats:
                        # **The sample size is the number of skeleton points, not the number of drawings.** A first
                        # version printed the drawing count under the heading `n`, where a single labelled drawing
                        # showed `n = 1` beside a median and read as one sample instead of ten thousand.
                        pooled.setdefault(part, []).append((stats['median'], stats['count']))
            print()
            print('  %-16s %9s %9s %11s' % ('part', 'drawings', 'points', 'median'))
            summary = {}
            for part in sorted(pooled):
                pairs = pooled[part]
                values = np.array([value for value, _count in pairs])
                points = sum(count for _value, count in pairs)
                summary[part] = float(np.median(values))
                print('  %-16s %9d %9d %10.4f%%' % (part, values.size, points, 100 * np.median(values)))
            if len(summary) >= 2:
                low = min(summary.values())
                high = max(summary.values())
                print()
                print('  widest part is %.2f x the narrowest (%s over %s)'
                      % (high / max(low, 1e-9),
                         ', '.join(p for p, v in summary.items() if v == high),
                         ', '.join(p for p, v in summary.items() if v == low)))
                print('  %s the 1.5x threshold that would make a part table worth having'
                      % ('PASSES' if high / max(low, 1e-9) >= 1.5 else 'FAILS'))
    # **The set is written down, not just printed.** A survey that exists only as console output cannot be reproduced or
    # argued with: the next person runs it on the same folder and gets a different list because the thresholds lived in
    # their memory. The manifest carries the tests as well as the results, so a disagreement is about a number.
    if args.manifest:
        manifest = {
            'source': str(folder),
            'pattern': pathlib.Path(args.glob).name,
            'tests': {'min_mass_share': args.min_mass_share, 'min_mass_height': args.min_mass_height,
                      'max_components': args.max_components, 'max_median': args.max_median,
                      'max_ratio': args.max_ratio},
            'accepted': [{'file': row['name'], 'median': row['median'], 'p10': row['p10'], 'p90': row['p90'],
                          'figure_height_px': row['figure_height'], 'mass_share': row['mass_share'],
                          'mass_height': row['mass_height'], 'components': row['components']} for row in rows],
            'rejected': [{'file': name, 'reason': why} for name, why in rejected],
        }
        target = pathlib.Path(args.manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print('  manifest: %d accepted, %d rejected, written to %s' % (len(rows), len(rejected), target))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
