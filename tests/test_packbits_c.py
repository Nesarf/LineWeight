"""The compiled encoder and the Python encoder have to produce the same bytes, and the same file.

The C version exists because the Python loop measured at about seven megabytes a second, which on a seventeen-layer
drawing is twenty seconds of the PSD write. It is a transliteration of that loop, and a transliteration is exactly the
kind of change that drifts -- so these tests compare the two rather than the docstring in either place claiming they
agree.

**Both implementations are always exercised.** The C one is skipped only when the library has not been built, and the
Python one is reached by setting the loaded library aside for the duration of a call, which is also what a machine
without a compiler does.
"""
from __future__ import annotations

import random

import pytest

from lineweight import fastpack, psd


needs_c = pytest.mark.skipif(not fastpack.available(),
                            reason='the compiled encoder is not built; tools/build_packbits.py makes it')


def both(data, width):
    """The C answer and the Python answer for the same input, in that order."""
    fast = psd.packbits_rows(data, width)
    saved = fastpack._LIB
    fastpack._LIB = None
    try:
        slow = psd.packbits_rows(data, width)
    finally:
        fastpack._LIB = saved
    return fast, slow


@needs_c
def test_the_two_encoders_agree_on_every_kind_of_data():
    rng = random.Random(17)
    for width, height in ((1, 40), (5, 9), (64, 7), (301, 4)):
        for kind in ('empty', 'flat', 'runs', 'noise', 'two values'):
            size = width * height
            if kind == 'empty':
                data = bytes(size)
            elif kind == 'flat':
                data = bytes([200]) * size
            elif kind == 'runs':
                data = bytes((i // 7) % 6 for i in range(size))
            elif kind == 'two values':
                data = bytes(0 if i % 3 else 255 for i in range(size))
            else:
                data = bytes(rng.randrange(256) for _ in range(size))
            fast, slow = both(data, width)
            assert fast is not None, 'the library is loaded, so it has to answer'
            assert bytes(fast[0]) == bytes(slow[0]), '%s %dx%d: the row lengths differ' % (kind, width, height)
            assert bytes(fast[1]) == bytes(slow[1]), '%s %dx%d: the blobs differ' % (kind, width, height)


@needs_c
def test_a_run_longer_than_a_row_stops_at_the_row():
    """The boundary case the whole per-row design exists for. Eight rows of one value is eight runs of `width`, and a
    single long run would be a different file that decodes into the same bytes in the wrong order."""
    width, height = 6, 8
    data = bytes([42]) * (width * height)
    fast, slow = both(data, width)
    assert bytes(fast[1]) == bytes(slow[1])
    assert bytes(fast[1]) == bytes([257 - width, 42]) * height


@needs_c
def test_a_row_full_of_runs_and_literals_agrees():
    """One row that mixes a run of two, a literal of one, a run of exactly 128 and a run of one -- the four branches of
    the encoder inside a single span, which is where an off-by-one in the literal gather would show."""
    data = bytes([1, 1, 2, 3, 3, 4, 5, 5, 6, 7]) + bytes([9] * 128) + bytes([7, 8])
    fast, slow = both(data, len(data))
    assert bytes(fast[1]) == bytes(slow[1])


@needs_c
def test_a_written_psd_is_the_same_file_with_and_without_the_compiled_encoder(tmp_path):
    """The end-to-end version: the thing that actually ships is a file, so the comparison is a file."""
    from lineweight import psd as writer

    width, height = 24, 10
    layer = writer.Layer('INK', width, height)
    rng = random.Random(5)
    for index in range(width * height):
        layer.data[index * 4 + 0] = rng.randrange(256)
        layer.data[index * 4 + 1] = rng.randrange(256)
        layer.data[index * 4 + 2] = rng.randrange(256)
        layer.data[index * 4 + 3] = 255 if index % 3 else 0

    fast_path = str(tmp_path / 'fast.psd')
    writer.save_psd([layer], fast_path, width=width, height=height)
    saved = fastpack._LIB
    fastpack._LIB = None
    try:
        slow_path = str(tmp_path / 'slow.psd')
        writer.save_psd([layer], slow_path, width=width, height=height)
    finally:
        fastpack._LIB = saved
    assert open(fast_path, 'rb').read() == open(slow_path, 'rb').read()


def test_the_python_encoder_answers_when_the_library_is_absent():
    """Not skipped: a machine with no compiler has to keep writing valid PSDs, and that path is the one this test is
    about rather than the fast one."""
    saved = fastpack._LIB
    fastpack._LIB = None
    try:
        counts, blob = psd.packbits_rows(bytes([7]) * 40, 8)
    finally:
        fastpack._LIB = saved
    assert len(counts) == 10, 'five rows of eight'
    assert bytes(blob) == bytes([257 - 8, 7]) * 5
