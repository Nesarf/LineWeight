"""Find the row format of a PSD layer channel by testing arrangements against the pixel count the banner implies.

Four attempts at this container were wrong in four different ways, so this states the candidates and checks them rather
than proposing a fifth. The check is arithmetic and needs no knowledge of the answer: a channel for an WxH layer must
decode to W*H pixels, and an arrangement that does not produce that is not the arrangement.

The rectangle is read both ways because this project has already published one wrong conclusion from reading it the
wrong way round, and the two interpretations give different cell counts -- so the search covers both instead of
betting on one.
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight.psd import unpackbits                      # noqa: E402


def layer_channel_blobs(path: str):
    data = open(path, 'rb').read()
    banner_w = struct.unpack('>I', data[18:22])[0]
    banner_h = struct.unpack('>I', data[14:18])[0]
    at = 26
    at += 4 + struct.unpack('>I', data[at:at + 4])[0]
    at += 4 + struct.unpack('>I', data[at:at + 4])[0]
    at += 4
    info_len = struct.unpack('>I', data[at:at + 4])[0]
    at += 4
    count = struct.unpack('>h', data[at:at + 2])[0]
    at += 2
    out = []
    for _ in range(abs(count)):
        raw = struct.unpack('>iiii', data[at:at + 16])
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
        for cid, clen in channels:
            tag = struct.unpack('>H', data[at:at + 2])[0]
            out.append((raw, cid, clen, tag, data[at + 2:at + clen]))
            at += clen
    return banner_w, banner_h, out


def candidate_sizes(raw):
    """Every cell count the rectangle could imply, under both readings."""
    a, b, c, d = raw
    return {
        'top,left,bottom,right': (c - b) * (d - a),
        'left,top,right,bottom': (d - c) * (b - a),
        'top,bottom,left,right': (d - c) * (b - a),
    }


def try_decode(body: bytes, width: int, height: int, prefix: int) -> tuple[int, int]:
    """Decode assuming a per-row length prefix of `prefix` bytes. Returns (rows, pixels)."""
    position = 0
    total = 0
    rows = 0
    while rows < height:
        if position + prefix > len(body):
            break
        if prefix == 1:
            length = body[position]
        elif prefix == 2:
            length = struct.unpack('>H', body[position:position + 2])[0]
        else:
            length = struct.unpack('>I', body[position:position + 4])[0]
        position += prefix
        if position + length > len(body):
            break
        total += len(unpackbits(body[position:position + length], width))
        position += length
        rows += 1
    return rows, total


def main() -> None:
    path = sys.argv[1]
    banner_w, banner_h, blobs = layer_channel_blobs(path)
    print('%s   banner %dx%d' % (path, banner_w, banner_h))
    for raw, cid, clen, tag, body in blobs:
        print()
        print('  channel %+d  rect %s  declared %d  body %d  tag %d' % (cid, raw, clen, len(body), tag))
        sizes = candidate_sizes(raw)
        for label, cells in sizes.items():
            print('    reading %-24s implies %d cells' % (label, cells))
        hits = []
        for label, cells in sizes.items():
            w = banner_w
            for prefix in (1, 2, 4):
                rows, total = try_decode(body, w, banner_h + 64, prefix)
                if total == cells:
                    hits.append('rect=%s prefix=%d width=%d -> %d cells in %d rows'
                                % (label, prefix, w, total, rows))
        print('    exact matches: %s' % (hits or 'none'))
        # if nothing matches, show what each arrangement actually produced, which is the next clue
        for prefix in (1, 2, 4):
            for w in (banner_w, 512, 510, 496):
                rows, total = try_decode(body, w, banner_h, prefix)
                print('      prefix=%d width=%-4d -> %d rows, %d px' % (prefix, w, rows, total))


if __name__ == '__main__':
    main()
