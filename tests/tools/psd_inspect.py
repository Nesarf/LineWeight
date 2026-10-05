"""Parse a PSD's layer section completely, and compare two files field by field.

Reading a PSD by hand went wrong repeatedly while this was being written -- the layer and mask section has two nested
length fields, and the records are followed by channel data inside the same block, so a single miscounted offset makes
every following field nonsense. One read of SAI's own file concluded it had no layers at all; another produced layer
names made of binary. Neither was true, and both were my arithmetic.

The comparison mode is the point. A container format is learned by diffing a file the target application wrote against
one this project wrote, and the useful output is the first field where they disagree.
"""
import struct
import sys


def read_psd(path: str) -> dict:
    with open(path, 'rb') as handle:
        data = handle.read()
    out: dict = {'bytes': len(data), 'path': path}
    if data[:4] != b'8BPS':
        raise ValueError('not a PSD: %r' % data[:4])
    out['version'] = struct.unpack('>H', data[4:6])[0]
    out['channels'] = struct.unpack('>H', data[12:14])[0]
    out['height'] = struct.unpack('>I', data[14:18])[0]
    out['width'] = struct.unpack('>I', data[18:22])[0]
    out['depth'] = struct.unpack('>H', data[22:24])[0]
    out['mode'] = struct.unpack('>H', data[24:26])[0]

    o = 26
    out['colour_mode_len'] = struct.unpack('>I', data[o:o + 4])[0]
    o += 4 + out['colour_mode_len']
    out['resources_len'] = struct.unpack('>I', data[o:o + 4])[0]
    o += 4 + out['resources_len']

    # the layer and mask section, with the layer info block's own length nested inside it
    out['layer_mask_len'] = struct.unpack('>I', data[o:o + 4])[0]
    o += 4
    out['layer_info_len'] = struct.unpack('>I', data[o:o + 4])[0]
    o += 4
    info_start = o
    info_end = o + out['layer_info_len']

    signed = struct.unpack('>h', data[o:o + 2])[0]
    out['layer_count_signed'] = signed
    out['first_alpha_is_transparency'] = signed < 0
    count = abs(signed)
    o += 2

    layers = []
    for index in range(count):
        top, bottom, left, right = struct.unpack('>iiii', data[o:o + 16])
        o += 16
        nch = struct.unpack('>H', data[o:o + 2])[0]
        o += 2
        channels = []
        for _ in range(nch):
            cid, clen = struct.unpack('>hI', data[o:o + 6])
            o += 6
            channels.append((cid, clen))
        sig, blend = data[o:o + 4], data[o + 4:o + 8]
        opacity, clipping, flags = data[o + 8], data[o + 9], data[o + 10]
        o += 12
        extra_len = struct.unpack('>I', data[o:o + 4])[0]
        o += 4
        extra = data[o:o + extra_len]
        o += extra_len
        name_len = extra[0]
        name = extra[1:1 + name_len].decode('latin-1', 'replace')
        at = 1 + name_len
        at += (4 - (at % 4)) % 4
        mask_len = struct.unpack('>I', extra[at:at + 4])[0]
        at += 4 + mask_len
        blending_len = struct.unpack('>I', extra[at:at + 4])[0]
        at += 4 + blending_len
        blocks = []
        while at + 12 <= len(extra) and extra[at:at + 4] == b'8BIM':
            key = extra[at + 4:at + 8].decode('latin-1', 'replace')
            blen = struct.unpack('>I', extra[at + 8:at + 12])[0]
            blocks.append((key, blen))
            at += 12 + blen + (blen % 2)
        layers.append({'index': index, 'rect': (top, bottom, left, right), 'channels': channels,
                       'sig': sig, 'blend': blend, 'opacity': opacity, 'clipping': clipping,
                       'flags': flags, 'name': name, 'extra_len': extra_len, 'mask_len': mask_len,
                       'blending_len': blending_len, 'blocks': blocks,
                       'record_end': o})
    out['layers'] = layers
    out['records_end'] = o
    # whatever sits between the last record and the end of the block is channel data
    out['channel_data_len'] = info_end - o
    out['declared_channel_total'] = sum(length for layer in layers for _cid, length in layer['channels'])
    out['global_mask_len'] = struct.unpack('>I', data[info_end:info_end + 4])[0]
    out['merged_offset'] = info_end + 4 + out['global_mask_len']
    out['merged_compression'] = (struct.unpack('>H', data[out['merged_offset']:out['merged_offset'] + 2])[0]
                                 if out['merged_offset'] + 2 <= len(data) else None)
    return out


def describe(info: dict) -> None:
    print('%s' % info['path'])
    print('  header   %dx%d, %d channels, depth %d, mode %d, %d bytes'
          % (info['width'], info['height'], info['channels'], info['depth'], info['mode'], info['bytes']))
    print('  sections colour_mode %d, resources %d, layer+mask %d, layer info %d'
          % (info['colour_mode_len'], info['resources_len'], info['layer_mask_len'], info['layer_info_len']))
    print('  count    signed %d (transparency flag %s)'
          % (info['layer_count_signed'], info['first_alpha_is_transparency']))
    for layer in info['layers']:
        top, bottom, left, right = layer['rect']
        print('   [%d] name=%-18r rect %d,%d..%d,%d (%dx%d) opacity %d clip %d flags %#06x blend %r'
              % (layer['index'], layer['name'], left, top, right, bottom, right - left, bottom - top,
                 layer['opacity'], layer['clipping'], layer['flags'], layer['blend']))
        print('       channels %s' % (layer['channels'],))
        print('       extra %d: mask %d, blending %d, blocks %s'
              % (layer['extra_len'], layer['mask_len'], layer['blending_len'], layer['blocks']))
    print('  records end %d, channel data %d bytes, channels claim %d bytes'
          % (info['records_end'], info['channel_data_len'], info['declared_channel_total']))
    print('  global mask %d, merged compression %s' % (info['global_mask_len'], info['merged_compression']))


def compare(a_path: str, b_path: str) -> int:
    a, b = read_psd(a_path), read_psd(b_path)
    print('A (reference) %s' % a_path)
    print('B (this project) %s' % b_path)
    print()
    differences = 0
    for key in ('width', 'height', 'channels', 'depth', 'mode', 'colour_mode_len', 'resources_len',
                'layer_mask_len', 'layer_info_len', 'layer_count_signed', 'channel_data_len',
                'global_mask_len', 'merged_compression'):
        av, bv = a.get(key), b.get(key)
        if key.endswith('_len') and av != bv:
            mark = '  '                                # lengths legitimately differ with content
        else:
            mark = '  ' if av == bv else '<>'
            differences += 1 if av != bv else 0
        print('  %s %-24s A=%-14s B=%s' % (mark, key, av, bv))
    print()
    print('  layers: A has %d, B has %d' % (len(a['layers']), len(b['layers'])))
    for i in range(max(len(a['layers']), len(b['layers']))):
        la = a['layers'][i] if i < len(a['layers']) else None
        lb = b['layers'][i] if i < len(b['layers']) else None
        for label, layer in (('A', la), ('B', lb)):
            if layer is None:
                print('    [%d] %s absent' % (i, label))
                continue
            print('    [%d] %s name=%-14r channels=%s blend=%r flags=%#06x extra=%d blocks=%s'
                  % (i, label, layer['name'], layer['channels'], layer['blend'], layer['flags'],
                     layer['extra_len'], layer['blocks']))
    return differences


if __name__ == '__main__':
    if len(sys.argv) == 2:
        describe(read_psd(sys.argv[1]))
    elif len(sys.argv) == 3:
        raise SystemExit(compare(sys.argv[1], sys.argv[2]))
    else:
        print('usage: psd_inspect.py FILE [FILE_TO_COMPARE]')
        raise SystemExit(2)
