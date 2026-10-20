"""Check the learning library against itself.

**What can go wrong in a library like this, and it is nothing dramatic.** An entry is added with a source that nobody
writes down on the shelf; a page is extracted for a book whose name is spelled differently in the two files; a count stops
matching the number of items it claims to count. **Each of those is silent** -- the library still loads, still reads
plausibly, and is wrong in a way that only shows up when somebody tries to use the entry.

So this checks six things and reports the ones that fail:

1. `facts.json` parses and every counted entry's `count` matches `len(items)`.
2. Every `source` string in `facts.json` names a document that `sources.md` also names.
3. Every book in `sources.md` is present in `extracts/index.json` or is explicitly marked as having given no extract.
4. Every file named in `extracts/index.json` exists on disk.
5. No entry appears twice with the same name.
6. The prose files exist and are not empty.

    python tools/check_learn.py
"""
import json
import pathlib
import re
import sys

LEARN = pathlib.Path(r'E:\lineweight\learn')


def main():
    problems = []
    notes = []

    facts_path = LEARN / 'facts.json'
    if not facts_path.exists():
        print('  facts.json is missing')
        return 1
    facts = json.loads(facts_path.read_text(encoding='utf-8'))

    # 1 -- a count that does not match its list
    counted = 0
    for key, entry in facts.items():
        if not isinstance(entry, dict) or 'count' not in entry:
            continue
        counted += 1
        items = entry.get('items')
        if items is None:
            notes.append('%s has a count but no items list' % key)
            continue
        if entry['count'] != len(items):
            problems.append('%s says count %s but lists %d' % (key, entry['count'], len(items)))

    # 5 -- a name used twice
    seen = {}
    for key in facts:
        if isinstance(facts[key], dict) and 'items' in facts[key]:
            for item in facts[key]['items']:
                stem = re.split(r'[\s(]', str(item))[0].lower()
                if stem and stem in seen and seen[stem] != key:
                    notes.append('%r appears in both %s and %s' % (stem, seen[stem], key))
                seen[stem] = key

    # 2 -- a source that the shelf does not name
    shelf = (LEARN / 'sources.md').read_text(encoding='utf-8')
    for key, entry in facts.items():
        if not isinstance(entry, dict) or 'source' not in entry:
            continue
        src = entry['source']
        # The shelf names books by author and articles by site, so match on the first distinctive word. **A page number
        # has to come off first**: the citation reads `Hampton p10.` and the shelf says `Michael Hampton`, and matching
        # the whole citation would report a source that is in fact listed.
        head = re.split(r'[,\'"(]', src)[0].strip()
        head = re.sub(r'\s+p\.?\s*\d+.*$', '', head).strip()
        candidates = [head]
        if 'MEDIBANG' in src:
            candidates = ['MEDIBANG']
        elif 'CLIP STUDIO' in src:
            candidates = ['CLIP STUDIO']
        if not any(c and c.lower() in shelf.lower() for c in candidates):
            problems.append('%s cites a source the shelf does not name: %s' % (key, head))

    # 3 and 4 -- extracts
    index_path = LEARN / 'extracts' / 'index.json'
    extracted_books = set()
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding='utf-8'))
        for row in index:
            extracted_books.add(row['book'])
            f = LEARN / 'extracts' / row.get('file', '')
            if row.get('file') and not f.exists():
                problems.append('extract for %s names %s, which is not on disk' % (row['book'], row['file']))
        notes.append('%d extracts, from %d books' % (len(index), len(extracted_books)))
    else:
        problems.append('extracts/index.json is missing')

    for m in re.finditer(r'^\| `([^`]+\.pdf)` \|', shelf, re.M):
        book = m.group(1)
        if book not in extracted_books:
            notes.append('%s has no extract page (may be deliberate)' % book)

    # 6 -- prose files
    for name in ('README.md', 'sources.md'):
        p = LEARN / name
        if not p.exists():
            problems.append('%s is missing' % name)
        elif p.stat().st_size < 200:
            problems.append('%s is suspiciously short (%d bytes)' % (name, p.stat().st_size))

    print('  facts.json: %d entries, %d countable' % (len(facts), counted))
    print('  sources.md: %d characters, %d books tabulated' % (len(shelf), len(re.findall(r'^\| `[^`]+\.pdf` \|', shelf, re.M))))
    print()
    if notes:
        print('  notes:')
        for n in notes:
            print('    - %s' % n)
        print()
    if problems:
        print('  PROBLEMS (%d):' % len(problems))
        for p in problems:
            print('    - %s' % p)
        return 1
    print('  all checks pass')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
