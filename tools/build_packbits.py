"""Build the compiled PackBits encoder that `lineweight/fastpack.py` loads.

    python tools/build_packbits.py

**Nothing here is required.** `psd.packbits_rows` asks for the library and falls back to the Python encoder, which
produces identical bytes at about a seventh of the speed. This script exists so the fast path is one command away
rather than an undocumented build step, and so a machine without a compiler gets a sentence saying why instead of a
traceback from somewhere else.

The library is not in version control; the source beside it is. `_packbits.c` is a transliteration of the Python
encoder and `tests/test_packbits_c.py` compares the two byte for byte, including a written PSD.
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, 'lineweight', '_packbits.c')
TARGET = {'win32': '_packbits.dll', 'darwin': '_packbits.dylib'}


def compiler():
    for name in ('gcc', 'cc', 'clang'):
        found = shutil.which(name)
        if found:
            return found
    return ''


def main() -> int:
    if not os.path.exists(SOURCE):
        print('%s is missing' % SOURCE)
        return 1
    found = compiler()
    if not found:
        print('no C compiler on PATH (looked for gcc, cc, clang)')
        print('the Python encoder stays in use; nothing is broken, it is about seven times slower')
        return 1
    name = TARGET.get(sys.platform, '_packbits.so')
    out = os.path.join(ROOT, 'lineweight', name)
    command = [found, '-shared', '-O2', '-o', out, SOURCE]
    print(' '.join(command))
    code = subprocess.call(command)
    if code == 0:
        sys.path.insert(0, ROOT)
        from lineweight import fastpack
        print('%s  %.1f KB  loaded: %s'
              % (out, os.path.getsize(out) / 1024.0, 'yes' if fastpack.available() else 'no'))
    return code


if __name__ == '__main__':
    sys.exit(main())
