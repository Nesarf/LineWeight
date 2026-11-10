"""把导出的 glTF 读回来、渲染成一张图：**这才是「打开看了一眼」。**

本机没有 Blender，也没有 Rhino。而「文件是合法 glTF」与「打开之后看得见」是两件事 —— 前者一个校验器就能回答
（`@gltf-transform/cli inspect` 已经回答过），后者要有人真的把它显示出来。

这个工具用最小的代价回答后者：读 JSON、对每一块取它 POSITION 的 z、把它的纹理按 z 错开叠起来。

**错开是等轴测的近似。** 真实的三维里这一叠沿 z 排；在纸上，它们沿对角线排 —— 于是「它们本来是分开的」这一句
在二维里也能被看见。**而这个工具刻意不复用 `lineweight` 的渲染器**：它读的是文件，不是画它的那个对象；如果它
读出来的东西和原画不一样，那说明导出器错了，而不是说明渲染器错了。
"""
import base64
import io
import json
import os
import sys

from PIL import Image

PAPER = (232, 226, 212, 255)


def _texture(document, base, primitive):
    """这一块的纹理，从 material 一路走到 image。**中间任何一环断了都要说出来**，而不是给一张空白。"""
    material = document['materials'][primitive['material']]
    info = material['pbrMetallicRoughness']['baseColorTexture']
    source = document['textures'][info['index']]['source']
    uri = document['images'][source]['uri']
    if uri.startswith('data:'):
        payload = uri.split(',', 1)[1]
        return Image.open(io.BytesIO(base64.b64decode(payload))).convert('RGBA')
    return Image.open(os.path.join(base, uri)).convert('RGBA')


def preview(path, out_path, spread=3.0):
    """`spread` 是 z 到像素的换算 —— 一个单位长度换算成几个像素的错开。"""
    base = os.path.dirname(os.path.abspath(path))
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)

    sizes = set()
    for mesh in document['meshes']:
        accessor = document['accessors'][mesh['primitives'][0]['attributes']['POSITION']]
        sizes.add((accessor['max'][0] - accessor['min'][0], accessor['max'][1] - accessor['min'][1]))
    if len(sizes) != 1:
        raise ValueError('the sheets are not all the same size: %r' % (sizes,))

    zs = []
    for mesh in document['meshes']:
        accessor = document['accessors'][mesh['primitives'][0]['attributes']['POSITION']]
        zs.append(accessor['min'][2])
    lowest, highest = min(zs), max(zs)
    step = (highest - lowest) / max(1, len(zs) - 1) if len(zs) > 1 else 0.0

    sheet = None
    canvas = None
    for index, node in enumerate(document['nodes']):
        mesh = document['meshes'][node['mesh']]
        image = _texture(document, base, mesh['primitives'][0])
        if canvas is None:
            margin = int(round((highest - lowest) * spread)) + 8
            canvas = Image.new('RGBA', (image.width + margin, image.height + margin), PAPER)
        offset = int(round((zs[node['mesh']] - lowest) * spread))
        canvas.alpha_composite(image, (offset, margin - 4 - offset))
    out = os.path.join(base, out_path) if not os.path.isabs(out_path) else out_path
    canvas.save(out)
    return out, len(document['nodes']), (lowest, highest, step)


def main(argv):
    path = argv[1] if len(argv) > 1 else None
    if not path:
        print('usage: gltf_preview.py <file.gltf> [out.png]')
        return 2
    out = argv[2] if len(argv) > 2 else os.path.splitext(path)[0] + '-preview.png'
    out, count, (lowest, highest, step) = preview(path, out)
    print('%s  %d sheets  z %.4f..%.4f (step %.4f)' % (out, count, lowest, highest, step))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
