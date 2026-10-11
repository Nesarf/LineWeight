"""Writing a file without ever leaving half of one behind.

**Why this is a module and not three lines repeated.** Every writer here replaces a file that an *application may
already have open*: the PSD goes to SAI, the XFL to Animate, the SVG to Illustrator. Writing in place means there is a
window -- milliseconds, or seconds for a large document -- during which the file on disk is a prefix of the drawing,
and an application that reads it in that window gets a truncated picture or refuses the file outright. Nothing in this
library can prevent a reader from looking at the wrong moment; what it can do is make the window not exist.

**The method is the one Compositor's format document specifies for the same hazard**, and it states the reason better
than a paraphrase would: *"write any new or changed PNGs first, then write the manifest to a temporary file and rename
it over. A rename is atomic: it sees either the old manifest or the new one, never part of one."*

**Two things are load-bearing and both are easy to get wrong.**

* **The temporary file must be a sibling of the target.** A rename is only atomic within one filesystem, and the
  system temporary directory is usually a different one -- `os.replace` would then be a copy, which is not atomic and
  is slower than writing in place. So the temporary is `.<name>.tmp` beside the target, not in `%TEMP%`.
* **`os.replace`, not `os.rename`.** `rename` fails on Windows when the target exists, which is every time here.

A directory is the case this cannot fully solve, and `write_tree_atomic` says so where it is defined rather than
pretending otherwise.
"""
from __future__ import annotations

import os
import shutil

__all__ = ['atomic_path', 'write_atomic', 'write_bytes_atomic', 'write_tree_atomic']


def atomic_path(path: str) -> str:
    """The sibling a write lands on before it is renamed over the target.

    Beside the target rather than in the system temporary directory, **because a rename is only atomic within one
    filesystem** and `%TEMP%` is normally a different one -- so `os.replace` would silently become a copy, which is
    neither atomic nor any faster than writing in place. The leading dot keeps it out of a directory listing.
    """
    directory, name = os.path.split(os.path.abspath(path))
    return os.path.join(directory, '.%s.tmp' % name)


def write_atomic(path: str, render, binary: bool = False) -> str:
    """Call `render(handle)` and put the result at `path`, or leave `path` untouched.

    `render` writes to the handle it is given. If it raises, the temporary is removed and the target is exactly what
    it was -- **which is the point**: a caller that fails halfway through has not damaged the drawing that is open in
    another program.
    """
    target = os.path.abspath(path)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    temporary = atomic_path(target)
    mode = 'wb' if binary else 'w'
    kwargs = {} if binary else {'encoding': 'utf-8', 'newline': '\n'}
    try:
        with open(temporary, mode, **kwargs) as handle:
            render(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target


def write_bytes_atomic(path: str, data: bytes) -> str:
    """The whole file is already in memory."""
    return write_atomic(path, lambda handle: handle.write(data), binary=True)


def write_tree_atomic(target: str, build) -> str:
    """A directory of files, built beside the target and moved into place.

    `build(root)` writes the whole tree into `root`. The old target is moved aside first and removed only after the
    new one is in place, so **a failure leaves either the old tree or the new one, never a mixture of both.**

    **This is not atomic and cannot be on Windows.** A directory cannot be replaced in one operation the way a file
    can -- `os.replace` onto a non-empty directory fails -- so there is a moment between the old tree moving aside and
    the new one arriving. The order is chosen so that the moment is one in which the target is *missing* rather than
    *wrong*: an application that opens it then gets "not found", which is a fault it will report, instead of a
    half-written document, which is one it may not.
    """
    target = os.path.abspath(target)
    parent = os.path.dirname(target) or '.'
    os.makedirs(parent, exist_ok=True)
    staging = target + '.new'
    retired = target + '.old'
    for stale in (staging, retired):
        if os.path.isdir(stale):
            shutil.rmtree(stale)
        elif os.path.exists(stale):
            os.unlink(stale)
    try:
        os.makedirs(staging)
        build(staging)
        had_old = os.path.exists(target)
        if had_old:
            os.replace(target, retired)
        os.replace(staging, target)
    except BaseException:
        if os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)
        if os.path.isdir(retired) and not os.path.exists(target):
            os.replace(retired, target)          # the old tree goes back if the new one did not arrive
        raise
    if os.path.isdir(retired):
        shutil.rmtree(retired, ignore_errors=True)
    return target
