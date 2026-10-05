"""Decode and draw a PSD layer's channels, so what a file contains can be looked at instead of inferred.

Everything about this container was learned by comparing bytes, and bytes had gone as far as they could: two files were
both structurally valid, both had the right channel counts, both had layer names, and one drew and the other did not. The
difference has to be in the pixels, and pixels are not readable in a hex dump.

The alpha channel is drawn on its own because that is where a layer's shape lives. RGB in a layer's channels is only
meaningful where alpha says so; a picture of the RGB alone shows a rectangle of colour whether or not anything is there.
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lineweight.psd import unpackbits                      # noqa: E402


def read_layer(path: str) -> dict:
    data = open(path, 'rb').read()
    at = 26
    at += 4 + struct.unpack('>I', data[at:at + 4])[0]      # colour mode data
    at += 4 + struct.unpack('>I', data[at:at + 4])[0]      # image resources
    at += 4                                                # layer and mask section length
    info_len = struct.unpack('>I', data[at:at + 4])[0]
    at += 4
    info_end = at + info_len
    count = struct.unpack('>h', data[at:at + 2])[0]
    at += 2
    width = struct.unpack('>I', data[8 + 10:8 + 14])[0]
    height = struct.unpack('>I', data[8 + 6:8 + 10])[0]
    header_channels = struct.unpack('>H', data[12:14])[0]

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
        at += 8                                            # signature and blend mode
        opacity, clipping, flags = data[at], data[at + 1], data[at + 2]
        at += 4
        extra_len = struct.unpack('>I', data[at:at + 4])[0]
        at += 4 + extra_len
        layers.append({'rect': (top, bottom, left, right), 'channels': channels,
                       'opacity': opacity, 'clipping': clipping, 'flags': flags})

    # the channel data follows the last record, one blob per channel in the order the records listed them
    blobs = {}
    for layer_index, layer in enumerate(layers):
        for cid, clen in layer['channels']:
            comp = struct.unpack('>H', data[at:at + 2])[0]
            at += 2
            body = data[at:at + clen]
            at += clen
            rows = []
            if comp == 1:
                position = 0
                for _y in range(height):
                    n = body[position]
                    position += 1
                    rows.append(unpackbits(body[position:position + n], width))
                    position += n
            elif comp == 0:
                rows = [body[y * width:(y + 1) * width] for y in range(height)]
            else:
                rows = []
            blobs[(layer_index, cid)] = (comp, b''.join(rows))
    return {'width': width, 'height': height, 'header_channels': header_channels,
            'count': count, 'layers': layers, 'blobs': blobs, 'info_end': info_end, 'file': len(data)}


def describe(path: str) -> None:
    info = read_layer(path)
    print('=' * 74)
    print(path)
    print('  %dx%d, header %d channels, %+d layers, %d bytes'
          % (info['width'], info['height'], info['header_channels'], info['count'], info['file']))
    for i, layer in enumerate(info['layers']):
        top, left, bottom, right = layer['rect']
        print('  [%d] rect %d,%d..%d,%d  opacity %d flags %#04x' % (i, left, top, right, bottom,
                                                                   layer['opacity'], layer['flags']))
        for cid, clen in layer['channels']:
            comp, flat = info['blobs'][(i, cid)]
            if not flat:
                print('      channel %+d: %d bytes declared, not decoded' % (cid, clen))
                continue
            values = list(flat)
            name = 'alpha' if cid == -1 else 'RGB'[cid] if 0 <= cid <= 2 else 'ch%d' % cid
            # alpha: 0 is transparent, so 255 is ink. RGB: the paper is bright, so ink is dark.
            ink = sum(1 for v in values if (v > 32 if cid == -1 else v < 200))
            print('      channel %+d (%-5s): comp %d, %d bytes, ink %d of %d (%.2f%%), min %d max %d'
                  % (cid, name, comp, clen, ink, len(values), 100.0 * ink / len(values),
                     min(values), max(values)))


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        describe(argument)
