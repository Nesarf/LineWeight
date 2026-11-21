"""The C encoder, loaded when it is beside this module and skipped when it is not.

**Why this file is separate from `psd.py`.** The library's promise is that it draws with the standard library, and a
compiled extension is the one thing that could break that promise for somebody who just wants a PSD. So the C part is
optional in the same way numpy is: `psd.packbits_rows` asks here first, and if the answer is None it runs the Python
encoder, which is correct on every machine and about seven times slower.

**The library is not in version control.** `_packbits.dll` is a build product -- the source beside it is what belongs
in the repository, and `tools/build_packbits.py` is what turns one into the other. A checkout without the build gets
the Python path and identical files.

`lw_packbits_rows` returns 0 for "not enough room" and also writes 0 bytes for an empty input; those are the same
value, so an empty channel is answered here rather than asked about.
"""
from __future__ import annotations

import ctypes
import os
import struct

_LIBRARY_NAMES = ('_packbits.dll', '_packbits.so', '_packbits.dylib')


def _load():
    here = os.path.dirname(os.path.abspath(__file__))
    for name in _LIBRARY_NAMES:
        path = os.path.join(here, name)
        if not os.path.exists(path):
            continue
        try:
            library = ctypes.CDLL(path)
        except OSError:          # a wrong architecture, a missing runtime -- either way, use Python
            continue
        library.lw_packbits_rows.restype = ctypes.c_size_t
        library.lw_packbits_rows.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_size_t,
                                             ctypes.c_char_p, ctypes.c_size_t,
                                             ctypes.POINTER(ctypes.c_uint16)]
        library.lw_packbits_capacity.restype = ctypes.c_size_t
        library.lw_packbits_capacity.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
        library.lw_packbits_rows_for.restype = ctypes.c_size_t
        library.lw_packbits_rows_for.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
        return library
    return None


_LIB = _load()


def available() -> bool:
    """Whether the compiled encoder is loaded. The tests use this to skip rather than to pass quietly."""
    return _LIB is not None


def path():
    """Where the library would be, whether or not it is there -- for a message that says how to build it."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, _LIBRARY_NAMES[0])


def packbits_rows(data: bytes, width: int):
    """`(row lengths, blob)` with each length as two big-endian bytes, or None when there is no library.

    **The counts come back as a uint16 array in the machine's order and leave as big-endian bytes**, because that is
    what the format says and the two must not be confused: a byte-swapped length table is a file whose first row
    decodes and whose remaining rows do not, which is the fault this module's docstring spends four paragraphs on.
    """
    if _LIB is None:
        return None
    length = len(data)
    if length == 0:
        return b'', b''
    span = max(1, int(width))
    rows = _LIB.lw_packbits_rows_for(length, span)
    if not rows:
        return None
    capacity = _LIB.lw_packbits_capacity(length, span)
    out = ctypes.create_string_buffer(capacity)
    counts = (ctypes.c_uint16 * rows)()
    written = _LIB.lw_packbits_rows(data, length, span, out, capacity, counts)
    if not written:
        return None
    lengths = b''.join(struct.pack('>H', counts[row]) for row in range(rows))
    return lengths, out.raw[:written]
