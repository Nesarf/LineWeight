"""Render the pages that carry a list or a rule into `learn/extracts/`, and name them.

**Why a script rather than a folder of copied images.** Each entry here is a page of somebody else's book that states
something countable or checkable, and the reason to keep it is that it can be looked at again when a drawing is being
judged. **A copied image loses which book and which page it came from**; this keeps that in the file name and in the
index it writes, so an extract can always be traced back.

    python make_extracts.py
"""
import json
import pathlib

import fitz

BOOKS = pathlib.Path(r'E:\DaShaoHuo\downloads\books')
OUT = pathlib.Path(r'E:\lineweight\learn\extracts')

#: book file, page number as printed in the book's own sequence (1-based as `fitz` indexes it), a short name, why.
EXTRACTS = [
    ('hampton-figure-drawing', 9,  'eight-parts-three-lines',  'The eight parts of the body and the three kinds of line.'),
    ('hampton-figure-drawing', 10, 'form-and-balance',         'The side is a large S; the masses counter-balance.'),
    ('hampton-figure-drawing', 20, 'centre-of-gravity',        'Sphere, egg, horizontal egg; balanced against dynamic.'),
    ('hampton-figure-drawing', 25, 'about-to-pose',            'The "about to" pose and the triangle of balance.'),
    ('hampton-figure-drawing', 34, 'landmarks',                'The second stage: the skeleton landmarks.'),
    ('hampton-figure-drawing', 27, 'economy-of-line',          'Render only what is necessary to describe the gesture.'),
    ('comic-inking', 9,   'line-weights-and-light',   'Heavy on the dark side, thin on the light side.'),
    ('comic-inking', 11,  'contour-lines',            'Five jobs of a contour, three styles, weights of a kind agree.'),
    ('comic-inking', 12,  'spotting-blacks',          'Black, gray and white across foreground, middle and background.'),
    ('bishoujo-mastering', 10, 'twelve-types',        'Twelve types as six opposed pairs; eyes, mouth and hair.'),
    ('female-figure-manga', 7,  'four-way-comparison', 'The same figure drawn four ways.'),
    ('clothed-figure-open', 190, 'folds-chapter',      'The seven types of folds with their causes.'),
    ('framed-perspective-2', 10, 'shadows-on-objects', 'Shadows constructed with perspective lines.'),
    ('figure-in-proportion', 42, 'proportion-vocabulary', 'The names of every measurement before any number.'),
    ('anatomy-vol2', 61, 'sphere-device',              'Draw a sphere around the subject: camera, light, point of view.'),
    ('tezuka-how-to-draw', 39, 'combination-table',    'Four face parts by eight variants, combined.'),
    ('manga-quick-study', 6, 'rough-sketch-step',      'Scribble first, then ink; the detail comes from the line.'),
    ('anime-game-characters-vol3', 20, 'sphere-and-stick', 'Cylinders and spheres defining the torso.'),
    ('ishiwatari-way', 2, 'step-one-scribble',         'Draw until the paper is completely black.'),
]


def book_path(stem):
    for f in BOOKS.glob('*.pdf'):
        if stem in f.stem:
            return f
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for stem, page, name, why in EXTRACTS:
        path = book_path(stem)
        if not path:
            print('  missing book: %s' % stem)
            continue
        with fitz.open(path) as doc:
            if page >= doc.page_count:
                print('  %s: no page %d' % (path.name, page + 1))
                continue
            target = OUT / ('%s--%s.png' % (stem, name))
            # **A readable size, not the largest possible.** An extract is for looking at, and 150 dpi keeps a page
            # legible without making the library heavy.
            doc[page].get_pixmap(dpi=150).save(str(target))
            index.append({
                'file': target.name,
                'book': path.name,
                'page': page + 1,
                'name': name,
                'why': why,
            })
            print('  %-52s <- %s p%d' % (target.name, path.stem, page + 1))
    (OUT / 'index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
    print()
    print('  %d extracts indexed in %s' % (len(index), OUT / 'index.json'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
