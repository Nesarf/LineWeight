"""Check the learning library against itself.

**What can go wrong in a library like this, and it is nothing dramatic.** An entry is added with a source that nobody
writes down on the shelf; a page is extracted for a book whose name is spelled differently in the two files; a count stops
matching the number of items it claims to count. **Each of those is silent** -- the library still loads, still reads
plausibly, and is wrong in a way that only shows up when somebody tries to use the entry.

**The checks themselves now live in the library**, as `lineweight.aesthetic.verify()`, for two reasons. A caller outside
this repository has no `tools/` and still needs to know whether the data agrees with the code; and two copies of one
checker drift in silence, which is the same failure this file is about, one level up. This script keeps the part that is
about reporting: the counts, and the books that have no extract page.

    python tools/check_learn.py
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lineweight import aesthetic  # noqa: E402


def main() -> int:
    learn = pathlib.Path(aesthetic.learn_dir())
    facts = aesthetic.facts()
    counted = sum(1 for entry in facts.values() if isinstance(entry, dict) and 'count' in entry)
    shelf = (learn / 'sources.md').read_text(encoding='utf-8')
    books = re.findall(r'^\| `([^`]+\.pdf)` \|', shelf, re.M)

    notes = []
    index = aesthetic.extracts()
    if isinstance(index, list):
        extracted = {row.get('book') for row in index if isinstance(row, dict)}
        notes.append('%d extracts, from %d books' % (len(index), len(extracted)))
        for book in books:
            if book not in extracted:
                notes.append('%s has no extract page (may be deliberate)' % book)
    else:
        notes.append('extracts/index.json is not a list')

    print('  facts.json: %d entries, %d countable' % (len(facts), counted))
    print('  sources.md: %d characters, %d books tabulated' % (len(shelf), len(books)))
    print()
    if notes:
        print('  notes:')
        for note in notes:
            print('    - %s' % note)
        print()

    problems = aesthetic.verify()
    if problems:
        print('  PROBLEMS (%d):' % len(problems))
        for problem in problems:
            print('    - %s' % problem)
        return 1
    print('  all checks pass')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
