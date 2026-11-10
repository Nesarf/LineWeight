"""把一张画的每一块记成一个命名的层，并导出分层 PSD。

**逐笔可改与分层可看是两个能力。** 每一笔已经是可寻址的 `Mark`；而「把树整层关掉，看剩下什么」要求笔分属不同的
纸，因为那一步是判断而不是编辑。

用法：

```python
place, stack = paint_export.stacker(W, H)
picture = place(picture, 'apple body', body_layer)
...
paint_export.export(stack, OUT, 'apple')
```

`place` 返回合成后的画，于是它可以直接替掉原来的 `r.blend(picture, layer, 'normal', 1.0)` —— 一行换一行，不改
任何绘制逻辑。

**透明的像素写成白色。** 消费方按「颜色，用 alpha 遮罩」合成；那里如果是黑的，整张画布会被涂黑，而在 SAI 里那呈现为
「图层名都在、画面是空的」—— 这个坑 `psd.py` 已经记过一次，这里沿用同一个修法。
"""
import os

from lineweight import gltf, psd
from lineweight import raster as r


def as_layer(name, layer, width, height):
    """一张渲染好的图层变成 PSD 的一层。**名字是它在画里的身份，不是一个序号。**"""
    canvas = psd.Layer(name, width, height)
    canvas.data = bytearray(layer.data)
    for i in range(0, len(canvas.data), 4):
        if canvas.data[i + 3] == 0:
            canvas.data[i] = canvas.data[i + 1] = canvas.data[i + 2] = 255
    return canvas


def stacker(width, height):
    """返回 `(place, stack)`。`place(picture, name, layer)` 合成并把那一块记下来。"""
    stack = []

    def place(picture, name, layer):
        stack.append(as_layer(name, layer, width, height))
        return r.blend(picture, layer, 'normal', 1.0)

    return place, stack


def export(stack, out_dir, stem):
    """写一份分层 PSD 与一份 glTF。**同一个 stack 去两个地方，因为它就是这张画的结构。**

    glTF 用 `embed=True`（纹理与缓冲都塞进 JSON），得到一个可以直接拖进 Blender 的单文件 —— 那份文件体积大一些，
    而它省掉了一整类「贴图找不到」的问题。PSD 那边照旧带外部资源，因为 SAI 与 CSP 读的就是那样。
    """
    psd_path = os.path.join(out_dir, '%s.psd' % stem)
    psd.save_psd(stack, psd_path)
    gltf.save_gltf(stack, os.path.join(out_dir, '%s.gltf' % stem), embed=True)
    return psd_path, len(stack)
