"""Wire `--fit` to the bands, and let the drawing's own ink decide which band it is compared against.

**Why the band is chosen by the drawing rather than by the caller.** The linework summary holds three groups of pages
whose taper medians are twenty-nine per cent apart -- 0.4543 for the pale ones, 0.3987 for the middle, 0.3521 for the
dark -- and the drawing is a line drawing with an ink fraction of 0.036, which puts it in the pale band. **Picking a
band by hand would be one more thing to get wrong and one more thing to remember**; letting the drawing's own ink
fraction choose makes the comparison self-consistent and, more usefully, **visible**: the output says which band it
used, what the others are, and therefore what was not compared.

    python patch_bands.py
"""
import pathlib

P = pathlib.Path(r'E:\lineweight\lineweight\core.py')

EDITS = [
    # 1. carry the bands through from the summary
    ("""    exc = data.get('linework_excluded') or {}
    if isinstance(exc.get('median'), (int, float)):
        targets['excluded'] = exc['median']
    return targets""",
     """    exc = data.get('linework_excluded') or {}
    if isinstance(exc.get('median'), (int, float)):
        targets['excluded'] = exc['median']
    # **And the bands, because the top-level medians are a mixture.** The collection this summary was built from
    # holds illustrations as well as design sheets -- two pages opened at random are both painted scenes -- and
    # `taper_ratio` is not the same quantity on the two. Grouped by how little of a page is ink, the medians run
    # 0.4543 / 0.3987 / 0.3521, twenty-nine per cent apart, so the headline figure describes neither kind. A caller
    # that compares against it is comparing against an average of two drawings it is not.
    bands = data.get('linework_bands') or {}
    if isinstance(bands, dict) and bands:
        targets['bands'] = bands
    return targets"""),

    # 2. choose the band by the drawing's own ink, and say so
    ("""    print('  this drawing: %dx%d' % (result.width, result.height))
    print('  against %s' % where)""",
     """    print('  this drawing: %dx%d' % (result.width, result.height))
    print('  against %s' % where)

    # **Which band, decided by the drawing's own ink fraction and printed rather than applied quietly.** A band
    # picked behind the caller's back would be the same fault as a threshold with no provenance: correct, and
    # impossible to check. The other bands are named beside it so that what was *not* compared is visible too.
    bands = targets.get('bands') or {}
    band = None
    if bands:
        for name, b in bands.items():
            lo, hi = b.get('ink_from', 0.0), b.get('ink_to', 1.0)
            if lo <= result.ink_ratio < hi:
                band = (name, b)
                break
        if band:
            name, b = band
            others = ', '.join('%s %.4f' % (k, v.get('taper_ratio', 0)) for k, v in bands.items() if k != name)
            print('  the reference is a mixture, so one band of it is used: the drawing\\'s ink of %.4f falls in')
            print('  ** %s (n %d, ink %.2f-%.2f) **, whose taper sits at %.4f. The other bands: %s.'
                  % (name, b.get('n', 0), b.get('ink_from', 0), b.get('ink_to', 1),
                     b.get('taper_ratio', 0), others))
            targets = dict(targets)
            targets['taper_ratio'] = b.get('taper_ratio', targets.get('taper_ratio'))
            targets['ink_ratio'] = b.get('ink_ratio', targets.get('ink_ratio'))
        else:
            print('  ** the drawing\\'s ink of %.4f falls in no band of the reference, so the top-level medians are')
            print('     used -- and those are the medians of a mixture. **' % result.ink_ratio)"""),
]


def main():
    s = P.read_text(encoding='utf-8')
    for i, (old, new) in enumerate(EDITS, 1):
        n = s.count(old)
        if n != 1:
            raise SystemExit('anchor %d matched %d times:\n%r' % (i, n, old[:90]))
        s = s.replace(old, new)
        print('  anchor %d applied' % i)
    P.write_text(s, encoding='utf-8')
    print('  core.py patched')


if __name__ == '__main__':
    main()
