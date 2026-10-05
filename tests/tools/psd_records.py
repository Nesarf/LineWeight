"""Dump the raw bytes of a PSD's layer records, for diffing against a file SAI wrote itself.

Written after three attempts to parse those records programmatically produced three different wrong answers -- layers
with 0x0 rectangles, names made of binary, a global mask length of 65544 -- none of which were true. The records are
short: a rectangle, a channel list, and an eight-byte signature plus blend mode. Printing the bytes beside the
interpretation is the only part of that which did not mislead, and it is what found the missing `8BIM`.

The interpretation here is deliberately minimal. It reads what it can justify from the bytes and prints the rest, on the
principle that a wrong field is worse than an absent one -- a parse that invents a value sends the search somewhere.
"""
import struct
import sys


def dump(path: str) -> None:
    data = open(path, 'rb').read()
    print('=' * 78)
    print(path)
    print('  %d bytes, header %dx%d, %d channels, depth %d, mode %d'
          % (len(data), struct.unpack('>I', data[18:22])[0], struct.unpack('>I', data[14:18])[0],
             struct.unpack('>H', data[12:14])[0], struct.unpack('>H', data[22:24])[0],
             struct.unpack('>H', data[24:26])[0]))

    at = 26
    colour_mode = struct.unpack('>I', data[at:at + 4])[0]
    at += 4 + colour_mode
    resources = struct.unpack('>I', data[at:at + 4])[0]
    print('  colour mode %d bytes, image resources %d bytes' % (colour_mode, resources))
    at += 4 + resources
    layer_mask = struct.unpack('>I', data[at:at + 4])[0]
    at += 4
    layer_info = struct.unpack('>I', data[at:at + 4])[0]
    print('  layer+mask %d bytes, layer info %d bytes' % (layer_mask, layer_info))
    at += 4
    info_end = at + layer_info
    count = struct.unpack('>h', data[at:at + 2])[0]
    print('  layer count %+d  (records begin at %d)' % (count, at + 2))
    at += 2

    for index in range(abs(count)):
        start = at
        top, bottom, left, right = struct.unpack('>iiii', data[at:at + 16])
        at += 16
        channels = struct.unpack('>H', data[at:at + 2])[0]
        at += 2
        channel_list = []
        for _ in range(channels):
            cid, clen = struct.unpack('>hI', data[at:at + 6])
            at += 6
            channel_list.append((cid, clen))
        print('  [%d] record starts at %d' % (index, start))
        print('      rectangle  top=%d bottom=%d left=%d right=%d  -> %dx%d'
              % (top, bottom, left, right, right - left, bottom - top))
        print('      %d channels: %s' % (channels, channel_list))
        signature = data[at:at + 4]
        blend = data[at + 4:at + 8]
        at += 8
        opacity, clipping, flags, filler = data[at], data[at + 1], data[at + 2], data[at + 3]
        at += 4
        print('      signature %r blend %r  opacity %d clipping %d flags %#04x filler %d'
              % (signature, blend, opacity, clipping, flags, filler))
        extra_len = struct.unpack('>I', data[at:at + 4])[0]
        at += 4
        extra = data[at:at + extra_len]
        at += extra_len
        print('      extra data: 0x%X bytes' % extra_len)
        print('        raw: %s' % extra.hex(' '))
        if extra:
            nulls = 4                                  # layer mask data, four zero bytes for "no mask"
            if extra_len >= 8:
                blending = struct.unpack('>I', extra[nulls:nulls + 4])[0]
                print('        layer mask %d bytes, blending ranges %d bytes' % (
                    struct.unpack('>I', extra[0:4])[0], blending))
            tail = extra[8:]
            if tail and 0 < tail[0] < 64:
                name = tail[1:1 + tail[0]]
                print('        name looks like %r (pascal, padded)' % name)
        print('      record ends at %d' % at)

    print('  records end at %d, layer info ends at %d (%d bytes of channel data)'
          % (at, info_end, info_end - at))
    global_mask = struct.unpack('>I', data[info_end:info_end + 4])[0]
    print('  global layer mask %d bytes; merged image begins at %d' % (global_mask, info_end + 4 + global_mask))
    print()


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        dump(argument)
