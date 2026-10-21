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

## The files

**`skeleton.json`** -- 279 bones, stored **columnar**: three parallel arrays (`name`, `parent`, `pos`) where a bone is
an index. **This is what a pose is composed down**; without parents a VMD's per-bone rotations have nowhere to
accumulate.

**`poses.json`** -- 36 frames, each a list of `[x, y, z]` in the order of the file's `joint` array, **divided by that
frame's own height** (stored as `scale`). Three frames per peak of the motion's speed curve, named `before`, `peak` and
`after`, because **the frame worth drawing is not the fastest one** -- see below.

**`motions.json`** -- one entry per motion: frame span, how many of its bones this skeleton shares, mean and peak
speed, and the frame numbers of the peaks. **The shared count is the thing to read first**: a motion recorded on a
different model shares 58 or 59 of these 279 bones, which is enough for the limbs and the spine and nothing else.

**`shape/`** -- a volume profile per model, two of each. `<model>.json` measures every mesh, so its width is the
silhouette's width, arms and hair included. `<model>-body.json` measures only the meshes whose name contains `body`,
so its width is the body's. **The second one is the part a front view cannot draw**: it says how deep the trunk is as
well as how wide, and the two are not proportional -- on the Zome model the hips are the widest band at 0.162 and the
chest the deepest at 0.086 over 0.120 wide, so the cross-section turns from an ellipse lying down to one standing up.

## The size budget

**One gigabyte is the allowance and 63 KB is the use**, which is not a sign that there is nothing left to pack. A
character's vertices are about 1.3 MB; its profile is 3.4 KB; the mesh can be measured again whenever the source is
still on the drive. **What a drawing needs from a surface is a width at a height**, and that is 64 rows of four numbers.

## Why the files are shaped this way

**A drawing tool does not need a model, and that is not a figure of speech.** There are no learned weights here --
these are coordinates, and coordinates can be measured again, so the only question is what has to stay for the library
to be rebuildable and usable. Two answers shrank the directory from 91 KB to 33 KB without losing anything:

- **Columnar instead of one object per bone.** `"name"`, `"parent"` and `"pos"` were 279 keys each, plus indentation;
  most of `skeleton.json` was its own field names.
- **Ratios instead of model units.** A joint at 0.4 of a body survives a change of model; a joint at 9.05 units does
  not. The divisor is kept in `scale`, so the absolute picture can still be recovered.

## Coordinates and units

`y` is up, `x` is right, and `z` points into the page. **`skeleton.json` is in the model's own units** -- that skeleton
stands about 14 units tall -- and **`poses.json` is not**: every pose is divided by its own frame's height, so a value
there is a fraction of a body. A drawing uses the ratios directly and takes its sizes from its own canvas.

## Why these frames

For each motion the sum of every major joint's angle change per frame is computed, the strongest peaks are taken, and
three frames are stored around each: two samples before the peak, the peak itself, and two after.

**The peak is the frame not to draw.** At a peak the limb is moving fastest *through* a pose, held for one frame; just
before it the body is committed and the shape is still closing; just after it the shape has opened out and the movement
is finished. Three different pictures of one movement, and only the middle of the three carries the prediction.

## What is not here, and each omission is deliberate

- **No mesh, but its profile.** Vertices are 1.3 MB per model and the shape they make is 3.4 KB of widths and depths;
  the mesh itself would be a copy, and a copy is the one thing a rebuildable library does not need.
- **No inverse kinematics.** A leg driven by an IK bone is placed by that bone's target, and this composes rotations
  only -- so a knee on an IK-driven leg reads where its own rotation puts it.
- **Interpolation is linear.** A VMD carries 64 bytes of interpolation curves per record and this does not read them.
- **No motion for the meshes in `E:\ANMS`.** Four VRM files declare no animations and the one FBX with curve nodes has
  no keyframe curves under them, which is why the motions come from a different library entirely.
