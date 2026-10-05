"""Work out how a real PSD lays out its layer channel data, by trying the plausible layouts and checking which decodes.

Guessing at this container has cost more than every other approach combined, and the guesses were not random -- each was
reasonable and each was wrong. So instead of proposing a fifth, this reads the declared channel lengths and tests the
arrangements the format could have, keeping only the ones whose decoded size matches the image exactly. A layout that is
wrong produces the wrong number of pixels or an invalid compression tag, and both are checkable without knowing the
answer in advance.
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight.psd import unpackbits                      # noqa: E402


def sections(data: bytes) -> tuple[int, int, int, int]:
    """(layer records offset, records end, layer info end, width, height)."""
    width = struct.unpack('>I', data[18:22])[0]
    height = struct.unpack('>I', data[14:18])[0]
    at = 26
    at += 4 + struct.unpack('>I', data[at:at + 4])[0]
    at += 4 + struct.unpack('>I', data[at:at + 4])[0]
    at += 4                                                # layer and mask length
    info_len = struct.unpack('>I', data[at:at + 4])[0]
    at += 4
    return at, width, height, at + info_len


def records(data: bytes) -> tuple[list, int]:
    at, width, height, info_end = sections(data)
    count = struct.unpack('>h', data[at:at + 2])[0]
    at += 2
    layers = []
    for _ in range(abs(count)):
        top, left, bottom, right = struct.unpack('>iiii', data[at:at + 16])  # PSD: top, left, bottom, right
        at += 16
        nch = struct.unpack('>H', data[at:at + 2])[0]
        at += 2
        channels = []
        for _c in range(nch):
            cid, clen = struct.unpack('>hI', data[at:at + 6])
            at += 6
            channels.append([cid, clen])
        at += 8
        at += 4
        extra = struct.unpack('>I', data[at:at + 4])[0]
        at += 4 + extra
        layers.append({'rect': (top, left, bottom, right), 'channels': channels})
    return layers, at, width, height, info_end


def try_layout(data: bytes, name: str) -> None:
    layers, records_end, width, height, info_end = records(data)
    print('=' * 76)
    print(name)
    print('  %dx%d, %d layer(s), records end %d, layer info ends %d (%d bytes of channel data)'
          % (width, height, len(layers), records_end, info_end, info_end - records_end))
    for i, layer in enumerate(layers):
        print('  [%d] rect %s, channels %s' % (i, layer['rect'], [(c[0], c[1]) for c in layer['channels']]))

    flat = [(i, cid, clen) for i, layer in enumerate(layers) for cid, clen in layer['channels']]
    print('  %d channel blobs in record order: %s' % (len(flat), [(c, l) for _, c, l in flat]))

    # Candidate A: one blob per channel, in record order, each beginning with a two-byte compression tag.
    print()
    print('  candidate A -- blobs consecutive, in record order, each with a 2-byte tag')
    at = records_end
    ok = True
    for i, cid, clen in flat:
        if at + 2 > info_end:
            print('     ran past the end of the layer info'); ok = False; break
        tag = struct.unpack('>H', data[at:at + 2])[0]
        if tag not in (0, 1):
            print('     blob %+d: tag %d is not a compression value -- this layout is wrong' % (cid, tag))
            ok = False
            break
        at += clen
    print('     %s (consumed %d of %d)' % ('consistent' if ok else 'inconsistent', at - records_end,
                                            info_end - records_end))

    # Candidate B: the declared length is the tag plus the body, i.e. the blob is length-prefixed rather than tagged.
    print()
    print('  candidate B -- each record channel length counts its own 2-byte tag')
    at = records_end
    ok = True
    for i, cid, clen in flat:
        tag = struct.unpack('>H', data[at:at + 2])[0]
        if tag not in (0, 1):
            print('     blob %+d: tag %d invalid' % (cid, tag)); ok = False; break
        at += clen
    print('     %s' % ('consistent' if ok else 'inconsistent'))


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        try_layout(open(argument, 'rb').read(), argument)
