"""glTF 出口：**一层一个节点，一层一张纹理，而每一层的透明度来自它自己。**

这些测试守的不是「文件写出来了」，而是那三件让分层在 3D 里仍然成立的事：

1. 节点数等于层数，而节点名就是层名 —— 否则在 Blender 的大纲里看到的是一排 `Object.001`；
2. 每层有自己的纹理，纹理里那一层的 alpha 还在 —— 否则每一层都是一块不透明的方片，叠起来"看起来对"而完全没分层；
3. 沿 z 的偏移随层递增 —— 否则所有平面共面，谁盖谁由浮点误差决定。
"""
import json
import os

import numpy as np

from lineweight import gltf, psd


def _layers(count=3):
    made = []
    for index in range(count):
        layer = psd.Layer('sheet %d' % index, 40, 20)
        for i in range(0, len(layer.data), 4):
            layer.data[i] = 30 + index * 40
            layer.data[i + 1] = 60
            layer.data[i + 2] = 90
            layer.data[i + 3] = 255 if index == 0 else 96
        made.append(layer)
    return made


def test_each_layer_becomes_a_named_node_with_its_own_texture(tmp_path):
    path, count = gltf.save_gltf(_layers(3), str(tmp_path / 'picture.gltf'))
    assert count == 3
    document = json.load(open(path, encoding='utf-8'))
    assert [node['name'] for node in document['nodes']] == ['sheet_0', 'sheet_1', 'sheet_2']
    assert len(document['meshes']) == 3
    assert len(document['materials']) == 3
    assert len(document['textures']) == 3
    assert len(document['images']) == 3
    for image in document['images']:
        assert os.path.exists(tmp_path / image['uri']), 'a texture the glTF points at is missing'


def test_the_layers_are_stacked_along_z_in_their_own_order(tmp_path):
    path, _ = gltf.save_gltf(_layers(3), str(tmp_path / 'picture.gltf'))
    document = json.load(open(path, encoding='utf-8'))
    heights = []
    for mesh in document['meshes']:
        accessor = document['accessors'][mesh['primitives'][0]['attributes']['POSITION']]
        heights.append(accessor['min'][2])
    assert heights == sorted(heights), 'the sheets are not stacked bottom to top'
    assert len(set(heights)) == 3, 'two sheets share a plane'


def test_the_texture_keeps_the_layer_alpha(tmp_path):
    """**一个不透明的方片也能『看起来对』，只要它是那张画的一部分。** 所以这里直接量 alpha。"""
    path, _ = gltf.save_gltf(_layers(2), str(tmp_path / 'picture.gltf'))
    document = json.load(open(path, encoding='utf-8'))
    upper = tmp_path / document['images'][1]['uri']
    from PIL import Image
    decoded = Image.open(str(upper)).convert('RGBA')
    alphas = np.asarray(decoded)[:, :, 3].tolist()
    assert 0 < max(alphas) < 255, 'the upper sheet came out fully opaque'


def test_the_buffer_holds_every_vertex_it_claims(tmp_path):
    path, _ = gltf.save_gltf(_layers(2), str(tmp_path / 'picture.gltf'))
    document = json.load(open(path, encoding='utf-8'))
    binary = (tmp_path / document['buffers'][0]['uri']).read_bytes()
    assert len(binary) == document['buffers'][0]['byteLength']
    for view in document['bufferViews']:
        assert view['byteOffset'] + view['byteLength'] <= len(binary), 'a view runs past the end of the buffer'
