"""Decode a layer channel from a PSD SAI wrote, and draw it as text so the shape can be recognised.

Comparing byte layouts has gone as far as it can. What is needed now is to see whether a channel decodes into the
*stroke that was drawn*, and the cheapest way to see a picture without an image library is to print it small: a
character per block of pixels, dark where there is ink. If the decoder is right, a hand-drawn diagonal appears; if the
row format is wrong, it appears as noise or as nothing.
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight.psd import unpackbits                      # noqa: E402


def layer_info(path: str):
    data = open(path, 'rb').read()
    width = struct.unpack('>I', data[18:22])[0]
    height = struct.unpack('>I', data[14:18])[0]
    at = 26
    at += 4 + struct.unpack('>I', data[at:at + 4])[0]
    at += 4 + struct.unpack('>I', data[at:at + 4])[0]
    at += 4                                                # layer and mask section length
    info_len = struct.unpack('>I', data[at:at + 4])[0]
    at += 4
    info_end = at + info_len
    count = struct.unpack('>h', data[at:at + 2])[0]
    at += 2
    layers = []
    for _ in range(abs(count)):
        top, left, bottom, right = struct.unpack('>iiii', data[at:at + 16])
        at += 16
        nch = struct.unpack('>H', data[at:at + 2])[0]
        at += 2
        channels = []
        for _c in range(nch):
            cid, clen = struct.unpack('>hI', data[at:at + 6])
            at += 6
            channels.append((cid, clen))
        at += 8 + 4
        extra = struct.unpack('>I', data[at:at + 4])[0]
        at += 4 + extra
        layers.append({'rect': (top, left, bottom, right), 'channels': channels})
    return data, width, height, layers, at, info_end


def decode_channel(data: bytes, at: int, clen: int, width: int, height: int) -> bytes:
    """One channel: a two-byte compression tag, then per-row lengths, then the rows."""
    tag = struct.unpack('>H', data[at:at + 2])[0]
    body = data[at + 2:at + clen]
    rows = []
    if tag == 1:
        position = 0
        while len(rows) < height and position < len(body):
            length = body[position]
            position += 1
            rows.append(unpackbits(body[position:position + length], width))
            position += length
    elif tag == 0:
        rows = [body[y * width:(y + 1) * width] for y in range(height)]
    return b''.join(rows)


def show(flat: bytes, width: int, height: int, rows: int = 30, cols: int = 64, invert: bool = False) -> None:
    if not flat:
        print('      (nothing decoded)')
        return
    block_h = max(1, height // rows)
    block_w = max(1, width // cols)
    for r in range(rows):
        line = []
        for c in range(cols):
            total = 0
            n = 0
            for y in range(r * block_h, min(height, (r + 1) * block_h), max(1, block_h // 4)):
                base = y * width
                for x in range(c * block_w, min(width, (c + 1) * block_w), max(1, block_w // 4)):
                    if base + x < len(flat):
                        total += flat[base + x]
                        n += 1
            average = (total / n) if n else 0
            if invert:
                average = 255 - average
            line.append('#' if average > 200 else ('+' if average > 120 else ('.' if average > 40 else ' ')))
        print('      |%s|' % ''.join(line))


def main() -> None:
    path = sys.argv[1]
    data, width, height, layers, records_end, info_end = layer_info(path)
    print('%s' % path)
    print('  banner %dx%d, %d layer(s)' % (width, height, len(layers)))
    at = records_end
    for index, layer in enumerate(layers):
        top, left, bottom, right = layer['rect']
        lw, lh = right - left, bottom - top
        print('  [%d] rect %d,%d..%d,%d  -> %dx%d' % (index, left, top, right, bottom, lw, lh))
        for cid, clen in layer['channels']:
            flat = decode_channel(data, at, clen, lw, lh)
            expected = lw * lh
            ink = sum(1 for v in flat if v > 32) if cid == -1 else sum(1 for v in flat if v < 200)
            print('      channel %+d: declared %d, decoded %d pixels (expected %d) %s, ink %d'
                  % (cid, clen, len(flat), expected, 'EXACT' if len(flat) == expected else 'MISMATCH', ink))
            if cid == -1:
                show(flat, lw, lh, rows=26, cols=66)
            at += clen


if __name__ == '__main__':
    main()
