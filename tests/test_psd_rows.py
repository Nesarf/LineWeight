"""One pass per channel must produce the same bytes as one pass per scanline.

`_packed_channel` used to call `packbits` once per row -- 6300 calls on a 1400x900 page -- because PSD stores one
PackBits stream per scanline and the obvious way to get that is to compress each row separately. `packbits_rows` does
the same work in one call and returns the per-row lengths the format's table needs.

The equivalence is not obvious from the code, so it is stated here as a test: **a run or a literal must not cross a row
boundary.** An encoder that let one continue would decode into the right bytes arranged the wrong way, and it would
only do so on pictures with flat regions taller than a single row -- which is most real drawings and almost no fixture.
"""
from __future__ import annotations

import struct

import pytest

from lineweight import psd


def one_row_at_a_time(data, width):
    counts = bytearray()
    rows = bytearray()
    for start in range(0, len(data), width):
        packed = psd.packbits(bytes(data[start:start + width]))
        counts += struct.pack('>H', len(packed))
        rows += packed
    return bytes(counts), bytes(rows)


def test_one_pass_agrees_with_one_pass_per_row():
    rng = __import__('random').Random(3)
    for width, height in ((1, 40), (7, 13), (64, 9), (300, 5)):
        for kind in ('empty', 'runs', 'noise'):
            if kind == 'empty':
                data = bytes(width * height)
            elif kind == 'runs':
                data = bytes((i // 3) % 5 for i in range(width * height))
            else:
                data = bytes(rng.randrange(256) for _ in range(width * height))
            counts, rows = psd.packbits_rows(data, width)
            expect_counts, expect_rows = one_row_at_a_time(data, width)
            assert bytes(counts) == expect_counts, '%s %dx%d: the row lengths differ' % (kind, width, height)
            assert bytes(rows) == expect_rows, '%s %dx%d: the blobs differ' % (kind, width, height)


def test_a_flat_region_taller_than_a_row_does_not_compress_across_it():
    """The failure this split exists to prevent. Eight rows of the same colour: a run that crossed rows would emit one
    long run and the row length table would describe a single row instead of eight."""
    width, height = 4, 8
    data = bytes([9]) * (width * height)
    counts, rows = psd.packbits_rows(data, width)
    lengths = struct.unpack('>%dH' % height, bytes(counts))
    assert len(lengths) == height
    assert all(length == 2 for length in lengths), 'each row is one run of four: a header byte and a value'
    assert bytes(rows) == bytes([257 - width, 9]) * height


def test_the_channel_written_round_trips_through_the_reader():
    width, height = 12, 6
    data = bytes((x * 7 + y) % 256 for y in range(height) for x in range(width))
    blob = psd._packed_channel(data, width, height)
    tag, rest = blob[:2], blob[2:]
    assert struct.unpack('>H', tag)[0] == 1, 'compression 1 is PackBits'
    lengths = struct.unpack('>%dH' % height, rest[:height * 2])
    body = rest[height * 2:]
    assert sum(lengths) == len(body)
    offset = 0
    recovered = bytearray()
    for length in lengths:
        recovered += psd.unpackbits(body[offset:offset + length], width)
        offset += length
    assert bytes(recovered) == data


def test_a_channel_that_is_not_whole_rows_is_refused():
    with pytest.raises(Exception) as err:
        psd._packed_channel(b'\x00' * 10, 4, 2)
    assert 'not 2 rows of 4' in str(err.value)
