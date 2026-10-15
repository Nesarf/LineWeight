"""Let --fit and --fit-dir choose which reference they compare against.

**Why there has to be a choice.** `corpus_summary.json` pools 929 records of which 645 are paintings, and its linework
subset was measured at 656x566. It records **no clip fraction** -- how much of each drawing the 2..16 px window drops
-- and that cannot be measured here because the images are not in this repository. `linework_summary.json` is 180
design sheets measured at 2048x1448 and **does** record it, so a taper comparison against it can be checked rather
than taken on faith.

They answer different questions, so neither is a default the other should overrule: the corpus is what the calibration
targets in the README came from, and the design sheets are what linework actually looks like.

    python patch_against.py
"""
import pathlib

P = pathlib.Path(r'E:\lineweight\lineweight\core.py')

EDITS = [
    ('def _library_targets() -> dict:\n'
     '    """The pooled linework distribution, from the checked-in summary when it is there."""',
     'def _library_targets(against: str = "corpus") -> dict:\n'
     '    """The pooled linework distribution, from whichever checked-in summary was asked for.\n'
     '\n'
     '    **Two summaries exist and they are not interchangeable.** `corpus_summary.json` pools 929 records of which\n'
     '    645 are paintings, and its linework subset was measured at 656x566. It records **no clip fraction** -- how\n'
     '    much of each drawing the 2..16 px window drops -- and that cannot be measured here because the images are not\n'
     '    in this repository, so a taper comparison against it has one side unknown and is withheld rather than\n'
     '    printed. `linework_summary.json` is 180 design sheets measured at 2048x1448 and **does** record it.\n'
     '\n'
     '    Choosing is the caller\'s business because the two answer different questions: the corpus is where the\n'
     '    calibration targets came from, and the design sheets are what linework actually looks like.\n'
     '    """'),

    ("    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),\n"
     "                        'tests', 'data', 'corpus_summary.json')",
     "    name = 'linework_summary.json' if against == 'linework' else 'corpus_summary.json'\n"
     "    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests', 'data', name)"),

    ("def fit_report(image_path: str) -> int:",
     "def fit_report(image_path: str, against: str = 'corpus') -> int:"),

    ("def fit_directory(root: str) -> int:",
     "def fit_directory(root: str, against: str = 'corpus') -> int:"),

    # **Both call sites, on purpose.** `fit_report` and `fit_directory` each read the targets and each must take the
    # choice. The first version of this matched once and raised otherwise -- which is right for the other anchors and
    # wrong here, and it raised *before* the write, so the file came out untouched while the CLI flag had already been
    # wired by a later patch. That is a broken call waiting to happen and no test reaches the --fit path.
    ("    targets = _library_targets()\n    ref_w, ref_h = targets.get('ref_width'), targets.get('ref_height')",
     "    targets = _library_targets(against)\n    ref_w, ref_h = targets.get('ref_width'), targets.get('ref_height')",
     'all'),

    ("    where = ('the library\\'s linework corpus, %d images' % targets.get('images', 0))",
     "    which = 'linework_summary (design sheets)' if against == 'linework' else \"the library's corpus\"\n"
     "    where = ('%s, %d images' % (which, targets.get('images', 0)))"),
]


def main():
    s = P.read_text(encoding='utf-8')
    for i, entry in enumerate(EDITS, 1):
        old, new = entry[0], entry[1]
        want = entry[2] if len(entry) > 2 else 'one'
        n = s.count(old)
        if want == 'all':
            if n < 1:
                raise SystemExit('anchor %d matched nothing' % i)
            s = s.replace(old, new)
            print('  anchor %d applied to %d sites' % (i, n))
            continue
        if n != 1:
            raise SystemExit('anchor %d matched %d times, not once:\n%r' % (i, n, old[:90]))
        s = s.replace(old, new)
        print('  anchor %d applied' % i)
    P.write_text(s, encoding='utf-8')
    print('  core.py patched')


if __name__ == '__main__':
    main()
