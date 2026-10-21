# The model library

**What this is.** The geometry a drawing is laid out on, kept beside the tool that lays it out. `learn/` holds what can
be counted -- how many parts a body has, what a line's width encodes; **this holds what has a position**: a skeleton's
rest positions and parents, and the joint positions of frames taken from motion that was actually performed.

**Everything here is generated, never hand written.** The sources are outside the repository and are large; what lands
here is 90 KB of coordinates. Rebuild with:

```
python tools/build_model_library.py \
  --pmx  "E:\ANMS\Rindo...\RINDO_Full.pmx" \
  --motion "G:\KKS\[VMD]\...\Motion.vmd" \
  --motion "G:\KKS\[VMD]\...\動作.vmd" \
  --out model
```

## The three files

**`skeleton.json`** -- 279 bones: name, rest position, and the parent by name. **This is what a pose is composed
down**; without parents a VMD's per-bone rotations have nowhere to accumulate.

**`poses.json`** -- 36 frames, each giving 20 joints as world positions. Three frames per peak of the motion's speed
curve, named `before`, `peak` and `after`, because **the frame worth drawing is not the fastest one** -- see below.

**`motions.json`** -- one entry per motion: frame span, how many of its bones this skeleton shares, mean and peak
speed, and the frame numbers of the peaks. **The shared count is the thing to read first**: a motion recorded on a
different model shares 58 or 59 of these 279 bones, which is enough for the limbs and the spine and nothing else.

## Coordinates and units

`y` is up, `x` is right, and `z` points into the page. The units are the model's own -- this skeleton stands about 14
units tall, and the motions were performed on models of a similar scale, so a ratio survives and an absolute size does
not. **A drawing therefore uses ratios from here and sizes from its own canvas.**

## Why these frames

For each motion the sum of every major joint's angle change per frame is computed, the strongest peaks are taken, and
three frames are stored around each: two samples before the peak, the peak itself, and two after.

**The peak is the frame not to draw.** At a peak the limb is moving fastest *through* a pose, held for one frame; just
before it the body is committed and the shape is still closing; just after it the shape has opened out and the movement
is finished. Three different pictures of one movement, and only the middle of the three carries the prediction.

## What is not here, and each omission is deliberate

- **No mesh.** Vertices are 26 MB per model and a drawing does not need them; what a drawing needs from a body is
  where its joints are.
- **No inverse kinematics.** A leg driven by an IK bone is placed by that bone's target, and this composes rotations
  only -- so a knee on an IK-driven leg reads where its own rotation puts it.
- **Interpolation is linear.** A VMD carries 64 bytes of interpolation curves per record and this does not read them.
- **No motion for the meshes in `E:\ANMS`.** Four VRM files declare no animations and the one FBX with curve nodes has
  no keyframe curves under them, which is why the motions come from a different library entirely.
