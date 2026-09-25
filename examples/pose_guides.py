#!/usr/bin/env python3
"""Draws the pose skeletons ControlNet's openpose model expects, from poses defined here rather than borrowed.

    python tools/pose_guides.py --out art/pose-guides

**Why the poses are drawn rather than downloaded.** A pose reference pack is somebody else's work, and a pose that
cannot be reproduced by whoever reads this repository is not a definition of anything. So the six poses are written
down here as joint positions and rendered, and the file is the definition. Nothing here is a copy of a reference
sheet; it is a stick figure, which is the only kind of image that carries no authorship.

The keypoint order is the one openpose uses, because that is what the model reads: nose, neck, shoulders, elbows,
wrists, hips, knees, ankles. ControlNet conditions on the *limbs*, so what has to be right is which joint connects
to which -- the drawing itself can be as crude as it likes.
"""
from __future__ import annotations

import argparse
import math
import os

from PIL import Image, ImageDraw

W, H = 512, 768

# The keypoint order openpose reads, and the colours it draws them in. Getting the pairing wrong is the one mistake
# that produces a pose that is not the pose asked for.
BONES = [
    ('neck', 'nose', (255, 0, 0)),
    ('neck', 'shoulder_l', (255, 85, 0)),
    ('shoulder_l', 'elbow_l', (255, 170, 0)),
    ('elbow_l', 'wrist_l', (255, 255, 0)),
    ('neck', 'shoulder_r', (170, 255, 0)),
    ('shoulder_r', 'elbow_r', (85, 255, 0)),
    ('elbow_r', 'wrist_r', (0, 255, 0)),
    ('neck', 'hip_l', (0, 255, 85)),
    ('hip_l', 'knee_l', (0, 255, 170)),
    ('knee_l', 'ankle_l', (0, 255, 255)),
    ('neck', 'hip_r', (0, 170, 255)),
    ('hip_r', 'knee_r', (0, 85, 255)),
    ('knee_r', 'ankle_r', (0, 0, 255)),
]

# **The five poses, as joint positions in a fraction of the frame.** These are the arms of the same six poses the
# sheet uses, written down once so that a pose means one thing everywhere in this project.
POSES: dict[str, dict[str, tuple[float, float]]] = {
    'crossed': {
        'nose': (0.50, 0.16), 'neck': (0.50, 0.24),
        'shoulder_l': (0.42, 0.26), 'elbow_l': (0.62, 0.40), 'wrist_l': (0.38, 0.40),
        'shoulder_r': (0.58, 0.26), 'elbow_r': (0.38, 0.42), 'wrist_r': (0.62, 0.44),
        'hip_l': (0.44, 0.50), 'knee_l': (0.42, 0.68), 'ankle_l': (0.41, 0.88),
        'hip_r': (0.56, 0.50), 'knee_r': (0.58, 0.68), 'ankle_r': (0.59, 0.88),
    },
    'hips': {
        'nose': (0.50, 0.15), 'neck': (0.50, 0.23),
        'shoulder_l': (0.42, 0.25), 'elbow_l': (0.33, 0.38), 'wrist_l': (0.38, 0.48),
        'shoulder_r': (0.58, 0.25), 'elbow_r': (0.67, 0.38), 'wrist_r': (0.62, 0.48),
        'hip_l': (0.44, 0.50), 'knee_l': (0.42, 0.68), 'ankle_l': (0.41, 0.88),
        'hip_r': (0.56, 0.50), 'knee_r': (0.58, 0.68), 'ankle_r': (0.59, 0.88),
    },
    'glass': {
        'nose': (0.50, 0.16), 'neck': (0.50, 0.24),
        'shoulder_l': (0.42, 0.26), 'elbow_l': (0.36, 0.38), 'wrist_l': (0.47, 0.42),
        'shoulder_r': (0.58, 0.26), 'elbow_r': (0.66, 0.36), 'wrist_r': (0.60, 0.46),
        'hip_l': (0.44, 0.50), 'knee_l': (0.42, 0.68), 'ankle_l': (0.41, 0.88),
        'hip_r': (0.56, 0.50), 'knee_r': (0.58, 0.68), 'ankle_r': (0.59, 0.88),
    },
    'fan': {
        'nose': (0.50, 0.16), 'neck': (0.50, 0.24),
        'shoulder_l': (0.42, 0.26), 'elbow_l': (0.35, 0.36), 'wrist_l': (0.45, 0.32),
        'shoulder_r': (0.58, 0.26), 'elbow_r': (0.66, 0.36), 'wrist_r': (0.60, 0.46),
        'hip_l': (0.44, 0.50), 'knee_l': (0.42, 0.68), 'ankle_l': (0.41, 0.88),
        'hip_r': (0.56, 0.50), 'knee_r': (0.58, 0.68), 'ankle_r': (0.59, 0.88),
    },
    'behind': {
        'nose': (0.50, 0.17), 'neck': (0.50, 0.25),
        'shoulder_l': (0.42, 0.27), 'elbow_l': (0.34, 0.36), 'wrist_l': (0.45, 0.44),
        'shoulder_r': (0.58, 0.27), 'elbow_r': (0.66, 0.36), 'wrist_r': (0.55, 0.44),
        'hip_l': (0.44, 0.50), 'knee_l': (0.42, 0.68), 'ankle_l': (0.41, 0.88),
        'hip_r': (0.56, 0.50), 'knee_r': (0.58, 0.68), 'ankle_r': (0.59, 0.88),
    },
    'offering': {
        'nose': (0.50, 0.16), 'neck': (0.50, 0.24),
        'shoulder_l': (0.42, 0.26), 'elbow_l': (0.38, 0.38), 'wrist_l': (0.48, 0.40),
        'shoulder_r': (0.58, 0.26), 'elbow_r': (0.68, 0.34), 'wrist_r': (0.58, 0.42),
        'hip_l': (0.44, 0.50), 'knee_l': (0.42, 0.68), 'ankle_l': (0.41, 0.88),
        'hip_r': (0.56, 0.50), 'knee_r': (0.58, 0.68), 'ankle_r': (0.59, 0.88),
    },
}


def draw_pose(name: str, joints: dict[str, tuple[float, float]]) -> Image.Image:
    image = Image.new('RGB', (W, H), (0, 0, 0))
    pen = ImageDraw.Draw(image)
    points = {key: (x * W, y * H) for key, (x, y) in joints.items()}
    for a, b, colour in BONES:
        pen.line([points[a], points[b]], fill=colour, width=8)
    for key, (x, y) in points.items():
        radius = 13 if key in ('nose', 'neck') else 10
        pen.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(255, 255, 255))
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='art/pose-guides')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for name, joints in POSES.items():
        image = draw_pose(name, joints)
        # a white skeleton on black, which is the form the openpose model was trained on
        image.save(os.path.join(args.out, name + '.png'))
        print('  %s' % os.path.join(args.out, name + '.png'))
    print('%d poses' % len(POSES))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
