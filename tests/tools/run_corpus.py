"""Measure a corpus into a resumable library, without the two mistakes the first version made.

The first version was resumable on paper and not in practice:

* it rebuilt the "already done" set by re-reading the whole output file **for every image**, which is quadratic and
  meant a run that had measured 650 images spent its time re-reading 650 lines before each of the next ones;
* it appended without checking, so the run that followed an interrupted run re-measured everything the interrupted
  one had written -- 1305 lines for 662 images, and no way to tell a duplicate from a second sample.

Both are fixed the boring way: read the output **once** at the start into a set of paths, and never append a path that
is already in it. The output is still JSON Lines and still flushed per image, because an hour-long job that loses
everything to one crash is an hour spent twice.

**And a third mistake, found by the duplicate count.** Fixing the resume left 1097 lines for 813 images: two runs
overlapped, each having read the output before the other had written, and both appended. A file that is appended to by
whoever starts is not a queue, so the run now takes a lock file and refuses to start twice. "Resumable" and "safe to
start twice" are different properties and only the first was implemented.
"""
import json
import os
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight.ref import measure

def _sources():
    """The corpora come from the environment: they are private collections of artwork, so the measurements are
    portable and the material, and the paths it lives at, are not."""
    raw = os.environ.get('LW_CORPUS', '')
    if not raw:
        return []
    out = []
    for index, path in enumerate(p for p in raw.split(os.pathsep) if p.strip()):
        tag = os.path.basename(path.rstrip('/' + os.sep)) or 'corpus%d' % index
        out.append((tag, path))
    return out
EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
OUT = os.environ.get('LW_CORPUS_OUT',
                     os.path.join(os.environ.get('TEMP', '.'), 'lineweight-corpus.jsonl'))
LOCK = OUT + '.lock'


def take_lock() -> bool:
    """One writer at a time. Two runs appending the same file measured everything twice."""
    if os.path.exists(LOCK):
        # **A lock is stale when its process is gone, not when it is old.** Age was the first rule and it was wrong in
        # both directions: a killed run left a lock that blocked the next slice for an hour, and a slow run would have
        # had its lock taken out from under it. The pid in the file is the fact.
        holder = None
        try:
            with open(LOCK, encoding='ascii') as handle:
                holder = int((handle.read() or '0').strip() or 0)
        except (OSError, ValueError):
            holder = None
        alive = False
        if holder:
            try:
                os.kill(holder, 0)          # signal 0 asks whether the process exists, and does nothing else
                alive = True
            except OSError:
                alive = False
        if alive:
            print('another run holds the lock (pid %d); refusing to start' % holder)
            return False
        print('stale lock from pid %s, which is gone; taking it' % holder)
    with open(LOCK, 'w', encoding='ascii') as handle:
        handle.write(str(os.getpid()))
    return True


def release_lock() -> None:
    try:
        os.remove(LOCK)
    except OSError:
        pass


def images_in(root: str) -> list[str]:
    found = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            if os.path.splitext(name)[1].lower() in EXTS:
                found.append(os.path.join(base, name))
    return sorted(found)


def load_done(path: str) -> set[str]:
    """Read the output once. Doing it per image is what made the first version quadratic."""
    done: set[str] = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get('path'):
                done.add(record['path'])
    return done


def main() -> int:
    limit = int(os.environ.get('CORPUS_LIMIT', '0'))     # 0 = all; a bound keeps a run inside a shell's patience
    if not take_lock():
        return 2
    todo: list[tuple[str, str]] = []
    for tag, root in _sources():
        if not os.path.isdir(root):
            print('missing source: %s' % root)
            continue
        for path in images_in(root):
            todo.append((tag, path))
    print('corpus: %d images' % len(todo), flush=True)

    done = load_done(OUT)
    print('already measured: %d' % len(done), flush=True)
    remaining = [(tag, p) for tag, p in todo if p not in done]
    if limit:
        remaining = remaining[:limit]
    print('to measure: %d%s' % (len(remaining), ' (sliced)' if limit else ''), flush=True)
    if not remaining:
        print('nothing to do')
        release_lock()
        return 0

    started = time.time()
    written = 0
    with open(OUT, 'a', encoding='utf-8', newline='\n') as handle:
        for index, (tag, path) in enumerate(remaining, 1):
            try:
                m = measure(path)
                record = {
                    'source': tag, 'path': path, 'width': m.width, 'height': m.height,
                    'line_runs': m.line_runs, 'area_runs': m.area_runs, 'runs': m.runs,
                    'ink_ratio': m.ink_ratio, 'darkness': m.darkness,
                    'width_mean': m.width_mean, 'width_median': m.width_median,
                    'width_p90': m.width_p90, 'width_max': m.width_max,
                    'taper_ratio': m.taper_ratio, 'note': m.note,
                }
            except Exception as exc:                    # noqa: BLE001 - an unreadable image is a record too
                record = {'source': tag, 'path': path, 'error': '%s: %s' % (type(exc).__name__, exc)}
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
            handle.flush()
            written += 1
            if index % 25 == 0 or index == len(remaining):
                elapsed = time.time() - started
                rate = elapsed / index
                print('%5d/%d  %.1fs each  eta %.0f min  last: %s'
                      % (index, len(remaining), rate, rate * (len(remaining) - index) / 60,
                         os.path.basename(path)[:36]), flush=True)
    print('wrote %d new records in %.0f minutes' % (written, (time.time() - started) / 60), flush=True)
    release_lock()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
