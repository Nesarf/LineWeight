"""Run the whole acceptance on a folder of pictures, so a change to the defaults is judged on more than two.

**Why this exists.** Every default in `reference_lines` was settled against one or two drawings, and the drawings
disagree: `150673997` came out wide and `150721001` narrow from the same settings. A change that fixes one and breaks
the other looks identical to a change that fixes both, so the only honest test is a spread of drawings with the
verdicts side by side. That test was run by hand for a while -- trace eleven pictures, accept eleven pictures, read
eleven logs -- and it cost an afternoon each time, which is why it was run once.

`tools/accept.py` answers "is this copy within the band" for one project. This answers "which of these drawings does
the current default not serve", which is a different question and needs the table rather than the verdict.

    python tools/corpus_accept.py --dir refs --work cache/regress --jobs 2

Nothing here measures anything new: every number is copied out of the log `accept.py` printed, so the table cannot
disagree with the acceptance itself. The two places it can be wrong are the two places it is simple -- the pattern
that reads the rows, and the assumption that a run which printed no rows failed.
"""

import argparse
import concurrent.futures
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE = os.path.join(HERE, 'reference_lines.py')
ACCEPT = os.path.join(HERE, 'accept.py')

# The six rows, in the order `accept.py` prints them. `ink reached` is listed with the rest even though it is judged
# from one side: its number is still needed to see what the width did.
KEYS = ('width share', 'p90 / median', 'ink reached', 'edge', 'ink depth', 'depth spread')

ROW = re.compile(r'^\s{2}(%s)\s+(\S+)\s+(\S+)\s+(\S+)\s+(inside|OUTSIDE)\s*$'
                 % '|'.join(re.escape(key) for key in KEYS))
PAGE = re.compile(r'at a fifth coverage\s+\(ratio\s+([0-9.]+)\)')


def read_log(text):
    """The six ratios and the page-ink ratio out of one acceptance log."""
    rows = {}
    for line in text.splitlines():
        found = ROW.match(line)
        if found:
            rows[found.group(1)] = (float(found.group(4)), found.group(5) == 'OUTSIDE')
    page = PAGE.search(text)
    return rows, (float(page.group(1)) if page else float('nan'))


def run(picture, work, reuse=False):
    """Trace one picture, accept it, and return what the log said.

    A project is reused only when asked, because the point of a regression is to re-run the numbers: a stale project
    sitting beside a fresh log is exactly the mistake that produced §4.43 -- an old json read against a new render.
    """
    name = os.path.splitext(os.path.basename(picture))[0]
    project = os.path.join(work, name + '.json')
    if not (reuse and os.path.exists(project)):
        if os.path.exists(project):
            os.remove(project)  # a half-written project from an interrupted run would be accepted as a real one
        traced = subprocess.run([sys.executable, TRACE, '--picture', picture, '--out', project],
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        if traced.returncode != 0 or not os.path.exists(project):
            return name, None, None, (traced.stderr or traced.stdout).strip()[-400:]
    accepted = subprocess.run([sys.executable, ACCEPT, '--project', project, '--reference', picture],
                              capture_output=True, text=True, encoding='utf-8', errors='replace')
    rows, page = read_log(accepted.stdout)
    if not rows:
        return name, None, None, (accepted.stderr or accepted.stdout).strip()[-400:]
    return name, rows, page, None


def report(results):
    """One table, ordered by how far the drawing's worst two-sided row sits from one.

    **`ink reached` is left out of that ordering.** It is judged from one side -- a copy that covers more of the
    artist's ink than its skeleton walked is width doing work, not a fault -- so its 1.9 is not "far off" and using it
    to sort would put the best-covered drawing last for being well covered.
    """
    clean = [r for r in results if r[1]]
    clean.sort(key=lambda r: max(abs(r[1][k][0] - 1.0) for k in KEYS if k in r[1] and k != 'ink reached'))
    header = '%-11s' % 'picture' + ''.join('%13s' % k for k in KEYS) + '%12s  %s' % ('ink at 1/5', 'worst')
    print(header)
    print('-' * 100)
    for name, rows, page, _error in clean:
        cells = ''.join('%13.3f' % rows[k][0] if k in rows else '%13s' % '-' for k in KEYS)
        worst = max((abs(rows[k][0] - 1.0), k) for k in KEYS if k in rows and k != 'ink reached')
        outside = [k for k in KEYS if k in rows and rows[k][1]]
        print('%-11s%s%12.3f  %-13s %s' % (name, cells, page, worst[1],
                                           ', '.join(outside) if outside else 'inside'))
    if len(clean) > 1:
        mid = '%-11s' % 'median' + ''.join(
            '%13.3f' % sorted(r[1][k][0] for r in clean if k in r[1])[len(clean) // 2] if all(k in r[1] for r in clean)
            else '%13s' % '-' for k in KEYS)
        pages = sorted(r[2] for r in clean)
        print('-' * 100)
        print('%s%12.3f' % (mid, pages[len(pages) // 2]))

    passing = [r for r in clean if not any(rows[k][1] for k in KEYS if k in rows)]
    print()
    print('%d of %d drawings pass all six rows.' % (len(passing), len(results)))
    for name, rows, page, _error in clean:
        outside = [k for k in KEYS if k in rows and rows[k][1]]
        if outside:
            print('  %-11s outside: %s' % (name, ', '.join('%s at %.3f' % (k, rows[k][0]) for k in outside)))
    broken = [r for r in results if not r[1]]
    if broken:
        print()
        print('%d did not produce a log:' % len(broken))
        for name, _rows, _page, error in broken:
            print('  %-11s %s' % (name, (error or 'no message').replace('\n', ' ')))
    return len(broken)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dir', required=True, help='a folder of reference pictures')
    parser.add_argument('--work', required=True, help='where the projects and logs go')
    parser.add_argument('--only', default='', help='comma-separated names to run, for a rerun of one drawing')
    parser.add_argument('--jobs', type=int, default=1,
                        help='how many pictures at once; each acceptance holds a whole project in memory')
    parser.add_argument('--reuse', action='store_true', help='accept the projects already in --work without tracing')
    args = parser.parse_args(argv)

    pictures = sorted(glob.glob(os.path.join(args.dir, '*.jpg')) + glob.glob(os.path.join(args.dir, '*.png')))
    if args.only:
        wanted = {name.strip() for name in args.only.split(',') if name.strip()}
        pictures = [p for p in pictures if os.path.splitext(os.path.basename(p))[0] in wanted]
    if not pictures:
        print('no pictures in %s' % args.dir)
        return 2
    os.makedirs(args.work, exist_ok=True)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        future = {pool.submit(run, picture, args.work, args.reuse): picture for picture in pictures}
        for done in concurrent.futures.as_completed(future):
            name, rows, page, error = done.result()
            if rows:
                print('  %s done' % name, flush=True)
            else:
                print('  %s failed: %s' % (name, (error or 'no message').replace('\n', ' ')), flush=True)
            results.append((name, rows, page, error))

    print()
    return 0 if report(results) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
