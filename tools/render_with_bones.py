"""Render a .blend and write every bone's screen position beside it.

**The pair this produces is the one the tables have been missing.** The bone names said what a part is and how many pieces
it comes in; the PSD layers said where a part sits in a texture page. Neither says where a part is **in a picture**. This
does: the same camera projection that draws the picture also places every bone on it, so the two cannot disagree.

**Nothing is saved into the source.** The file is opened, rendered into the output path, and Blender exits; the .blend on
disk is untouched.

    blender --background --factory-startup --python render_with_bones.py -- in.blend out.png out.json

The JSON holds, per bone: the screen position of its head and tail in pixels and in 0-1 fractions, and whether it is in
front of the camera. A bone behind the camera reports `visible: false` rather than a nonsense coordinate.
"""

import json
import math
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view


def world_bounds(objects):
    low = [float('inf')] * 3
    high = [float('-inf')] * 3
    for obj in objects:
        for corner in obj.bound_box:
            point = obj.matrix_world @ __import__('mathutils').Vector(corner)
            for i in range(3):
                low[i] = min(low[i], point[i])
                high[i] = max(high[i], point[i])
    if low[0] == float('inf'):
        return None
    return low, high


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if len(args) < 3:
        print('usage: -- in.blend out.png out.json')
        return 2
    source, out_png, out_json = args[0], args[1], args[2]

    bpy.ops.wm.open_mainfile(filepath=source)
    scene = bpy.context.scene

    # **The file's own camera if it has one.** `camera_to_view_selected` is the obvious way to frame a rig and it does not
    # work here: it needs a 3D viewport's context and background mode has none, so it raised on a Mesh. Framing is done by
    # arithmetic instead -- a camera on -Y, far enough back for the whole bounding box to fit the vertical field of view.
    meshes = [obj for obj in scene.objects if obj.type == 'MESH']
    # **A scene camera that is not a camera.** In this file `scene.camera` points at a Mesh, so `world_to_camera_view`
    # reached for `view_frame` on an object that has no such thing. The check is on the object's type, not on whether the
    # slot is filled -- a wrong occupant is as bad as an empty one.
    camera = scene.camera if (scene.camera is not None and scene.camera.type == 'CAMERA') else None
    if camera is None:
        bounds = world_bounds(meshes) if meshes else None
        camera_data = bpy.data.cameras.new('measure-camera')
        camera = bpy.data.objects.new('measure-camera', camera_data)
        scene.collection.objects.link(camera)
        if bounds:
            low, high = bounds
            centre = [(low[i] + high[i]) * 0.5 for i in range(3)]
            size = max(high[i] - low[i] for i in range(3))
            # the vertical field of view of a 50 mm lens on a 36 mm sensor
            half_angle = math.atan(0.5 * camera_data.sensor_height / camera_data.lens) if camera_data.sensor_height else 0.35
            distance = (size * 0.5) / max(0.05, math.tan(half_angle)) * 1.25
            camera.location = (centre[0], low[1] - distance, centre[2])
            camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        else:
            camera.location = (0.0, -4.0, 1.0)
            camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        scene.camera = camera

    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1536
    scene.render.resolution_percentage = 100
    scene.render.filepath = out_png
    scene.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)

    width = scene.render.resolution_x * scene.render.resolution_percentage / 100.0
    height = scene.render.resolution_y * scene.render.resolution_percentage / 100.0
    bones = {}
    for obj in scene.objects:
        if obj.type != 'ARMATURE':
            continue
        for bone in obj.data.bones:
            head = obj.matrix_world @ bone.head_local
            tail = obj.matrix_world @ bone.tail_local
            head_view = world_to_camera_view(scene, scene.camera, head)
            tail_view = world_to_camera_view(scene, scene.camera, tail)
            visible = head_view.z > 0 and tail_view.z > 0
            bones.setdefault(obj.name, {})[bone.name] = {
                'head_px': [round(head_view.x * width, 1), round((1.0 - head_view.y) * height, 1)],
                'tail_px': [round(tail_view.x * width, 1), round((1.0 - tail_view.y) * height, 1)],
                'head_uv': [round(head_view.x, 4), round(1.0 - head_view.y, 4)],
                'visible': bool(visible),
            }

    with open(out_json, 'w', encoding='utf-8') as handle:
        json.dump({'source': source, 'size': [width, height], 'armatures': bones}, handle, ensure_ascii=False, indent=1)
    total = sum(len(group) for group in bones.values())
    print('RENDERED %s' % out_png)
    print('BONES %d in %d armature(s) -> %s' % (total, len(bones), out_json))
    return 0


main()
