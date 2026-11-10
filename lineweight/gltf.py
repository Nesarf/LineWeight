"""把一层一层的画导成 glTF：**一层一个节点，一层一张纹理。**

一张 2D 分层画在 3D 里的诚实对应不是"把它压成一张图贴上去"，而是**把每一层做成一块平面，按原来的迭放顺序沿 z
错开一点点**。于是 Blender 或 Rhino 打开之后看到的是一叠卡片：关掉哪一张、移动哪一张，都还是那张画的一块。

**为什么是 glTF 而不是 OBJ。** OBJ 没有材质引用、没有透明度、没有节点名的一等公民，而这里要的正好是那三样：每块
平面要有自己的纹理、自己的 alpha、自己的名字。glTF 2.0 三样都直接表达，而且它是 MMD、Unity、Blender、Rhino 都能
读的那一个交集。

**坐标。** glTF 的 y 向上，而这里每一层的像素都是 y 向下。所以顶点在 y 上是翻的，UV 的 v 也是翻的 —— 两处都翻，
画面才是正的。**只翻一处会让整张画上下颠倒，而那正是这类导出器最常见的错。**

**交错不是问题，因为不做深度测试之外的事。** 每层沿 +z 偏 `gap`，读的时候按 z 排就是迭放顺序。这个文件不写相机、
不写灯光：观者（Blender）自己会有一个，而写死一个相机只会挡住人家的视口。
"""
import base64
import json
import os

import numpy as np

from . import raster as r

FLOAT = 5126
UNSIGNED_SHORT = 5123
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963


def _texture_png(layer, path):
    """把一层写成 PNG，**透明的地方保持透明**。

    这里不走 `raster.save_png`：它是给「一张画」用的，总会把一个背景合成进去 —— 而这一层之外的画不该被它挡住，那一
    层自己的 alpha 必须原样留到文件里。**一个导出器如果让每层都变成不透明的方片，它在 3D 里叠起来仍然"看起来对"，
    而分层已经没了。**
    """
    from PIL import Image

    array = np.frombuffer(bytes(layer.data), dtype=np.uint8).reshape(layer.height, layer.width, 4)
    Image.fromarray(array, 'RGBA').save(path)
    return path


def save_gltf(layers, path, gap=0.002, embed=False):
    """`layers` 是 `psd.Layer` 的列表，从底到顶。写出 `.gltf` 加同目录的 `.bin` 与 `tex/`。

    `embed=True` 时把缓冲与纹理都塞进 JSON（`data:` URI），得到一个单文件、可以直接拖进 Blender 的 `.gltf` ——
    代价是体积大三分之一左右。
    """
    if not layers:
        raise ValueError('a glTF needs at least one layer')
    directory = os.path.dirname(os.path.abspath(path)) or '.'
    stem = os.path.splitext(os.path.basename(path))[0]
    tex_dir = os.path.join(directory, stem + '_tex')
    os.makedirs(tex_dir, exist_ok=True)

    width = float(layers[0].width)
    height = float(layers[0].height)
    aspect = height / width if width else 1.0
    hw = 0.5
    hh = 0.5 * aspect

    buffer = bytearray()
    buffer_views = []
    accessors = []
    meshes = []
    materials = []
    images = []
    textures = []
    nodes = []
    used = set()

    for index, layer in enumerate(layers):
        z = index * gap
        # **一块有厚度的板，而不是一块平面。** 没有厚度的平面在 Blender 里从侧面看会消失 —— 而一叠卡片从侧面
        # 看正是一叠边，那是这个出口最该给人的那一眼。厚度取 `gap` 的四成，于是相邻两层之间还留着一条缝，
        # 而在正面看它们仍然贴在一起。
        half_t = gap * 0.4 * 0.5
        z0, z1 = z - half_t, z + half_t
        # **v 翻过来。** 图像的第 0 行是画面顶端，而 glTF 的 v=1 才是顶端 —— 不翻的话整张画上下颠倒。
        positions = np.array([
            [-hw, -hh, z1], [hw, -hh, z1], [hw, hh, z1], [-hw, hh, z1],
            [-hw, -hh, z0], [hw, -hh, z0], [hw, hh, z0], [-hw, hh, z0],
        ], dtype=np.float32)
        uvs = np.array([[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0],
                        [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]], dtype=np.float32)
        # 十二个三角形：前面、后面、四条侧边。索引绕序在两面都按外向，因为材质是 `doubleSided` 而这里只要它不
        # 自相交 —— 一张画的每一层从背后看仍然是那一层。
        indices = np.array([0, 1, 2, 0, 2, 3,           # 前
                            4, 6, 5, 4, 7, 6,           # 后
                            0, 4, 5, 0, 5, 1,           # 下
                            1, 5, 6, 1, 6, 2,           # 右
                            2, 6, 7, 2, 7, 3,           # 上
                            3, 7, 4, 3, 4, 0],          # 左
                           dtype=np.uint16)

        pos_offset = len(buffer)
        buffer.extend(positions.tobytes())
        buffer_views.append({'buffer': 0, 'byteOffset': pos_offset, 'byteLength': positions.nbytes,
                             'target': ARRAY_BUFFER})
        accessors.append({'bufferView': len(buffer_views) - 1, 'componentType': FLOAT, 'count': 8,
                          'type': 'VEC3',
                          'min': [float(positions[:, k].min()) for k in range(3)],
                          'max': [float(positions[:, k].max()) for k in range(3)]})

        uv_offset = len(buffer)
        buffer.extend(uvs.tobytes())
        buffer_views.append({'buffer': 0, 'byteOffset': uv_offset, 'byteLength': uvs.nbytes,
                             'target': ARRAY_BUFFER})
        accessors.append({'bufferView': len(buffer_views) - 1, 'componentType': FLOAT, 'count': 8,
                          'type': 'VEC2'})

        idx_offset = len(buffer)
        buffer.extend(indices.tobytes())
        while len(buffer) % 4:
            buffer.append(0)
        buffer_views.append({'buffer': 0, 'byteOffset': idx_offset, 'byteLength': indices.nbytes,
                             'target': ELEMENT_ARRAY_BUFFER})
        accessors.append({'bufferView': len(buffer_views) - 1, 'componentType': UNSIGNED_SHORT,
                          'count': 36, 'type': 'SCALAR'})

        # **一个层名在文件里只出现一次。** 三层的脊点数相同的时候，`mountain-%d % len(ridge)` 会给三块平面同一个
        # 名字 —— 而在 Blender 的大纲里它们变成 `mountain-14` 与 `mountain-14.001`，于是「这一层是什么」丢了一半。
        sheet = _unique(_safe(layer.name), used)
        used.add(sheet)
        tex_name = '%02d_%s.png' % (index, sheet)
        tex_path = os.path.join(tex_dir, tex_name)
        _texture_png(layer, tex_path)
        if embed:
            with open(tex_path, 'rb') as handle:
                payload = base64.b64encode(handle.read()).decode('ascii')
            images.append({'uri': 'data:image/png;base64,' + payload})
            os.remove(tex_path)
            uri = None
        else:
            images.append({'uri': '%s_tex/%s' % (stem, tex_name)})
            uri = None
        textures.append({'source': len(images) - 1, 'sampler': 0})
        materials.append({
            'name': sheet,
            # **不透明度的来源是这一层自己的 alpha 通道。** 关掉 alpha 之后每一层都会变成整块方片，而它们叠在一起
            # 就是最后那张图 —— 那看起来像「成功了」，实际上是什么都没分层。
            'alphaMode': 'BLEND',
            'doubleSided': True,
            'pbrMetallicRoughness': {
                'baseColorTexture': {'index': len(textures) - 1},
                'metallicFactor': 0.0,
                'roughnessFactor': 1.0,
            },
        })
        meshes.append({'name': sheet, 'primitives': [{
            'attributes': {'POSITION': len(accessors) - 3, 'TEXCOORD_0': len(accessors) - 2},
            'indices': len(accessors) - 1,
            'material': len(materials) - 1,
            'mode': 4,
        }]})
        nodes.append({'name': sheet, 'mesh': len(meshes) - 1})

    document = {
        'asset': {'version': '2.0', 'generator': 'lineweight'},
        'scene': 0,
        'scenes': [{'name': 'picture', 'nodes': list(range(len(nodes)))}],
        'nodes': nodes,
        'meshes': meshes,
        'materials': materials,
        'textures': textures,
        'images': images,
        'samplers': [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 33071, 'wrapT': 33071}],
        'accessors': accessors,
        'bufferViews': buffer_views,
        'buffers': [],
    }

    if embed:
        document['buffers'] = [{'byteLength': len(buffer),
                                'uri': 'data:application/octet-stream;base64,'
                                       + base64.b64encode(bytes(buffer)).decode('ascii')}]
    else:
        bin_name = stem + '.bin'
        with open(os.path.join(directory, bin_name), 'wb') as handle:
            handle.write(bytes(buffer))
        document['buffers'] = [{'byteLength': len(buffer), 'uri': bin_name}]

    for name in ('images', 'textures', 'materials', 'samplers'):
        if not document[name]:
            del document[name]

    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)
    return path, len(nodes)


def _unique(name, used):
    """一个在 `used` 里没出现过的名字。

    **层名在大纲里是唯一的那个东西，而重名的两层会变成 `mountain-14` 与 `mountain-14.001`** —— 于是名字丢了一个，
    而丢掉的正好是「这一层是什么」。所以重名在这里就地加序号，不留给观者去猜哪一层是哪一层。
    """
    if name not in used:
        return name
    index = 2
    while '%s-%d' % (name, index) in used:
        index += 1
    return '%s-%d' % (name, index)


def _safe(name):
    """glTF 的节点名可以是任意字符串，而文件名不行。"""
    keep = []
    for character in str(name):
        keep.append(character if character.isalnum() or character in '-_.' else '_')
    return ''.join(keep) or 'layer'
