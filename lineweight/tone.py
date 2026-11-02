"""Halftone screens: a value rendered as a periodic arrangement of marks rather than as a flat tint.

**Why this is not a colour.** In a screen-tone drawing a mid grey is not ink at that lightness; it is black dots on white
paper at a spacing that makes the eye read grey. The difference matters when the picture is copied. A flat grey has no
structure to copy, and its boundary is the only thing a line finder can see; a screen has structure at the dot pitch,
which is a length, so the same tone drawn at two page sizes is the same tone only if the pitch is quoted against the page.

**The geometry is the printing convention.** One mark per cell on a square lattice rotated to forty-five degrees -- the
rotation that keeps the lattice from lining up with the drawing's own vertical and horizontal strokes, where it would
read as a pattern rather than as a tone. The mark's size follows from the coverage asked for, computed per shape below.

**Antialiasing is the same statement the rasteriser makes for a stroke**: coverage is the mark's own radius plus half a
pixel minus the distance to its centre, clipped to nought and one. A screen's edge and a stroke's edge therefore soften
by the same rule, which is what keeps a screen from looking pasted onto a drawing.

**What this is not.** A screen is not a value the fill stage can produce on its own: it needs a pitch, an angle and a
shape, and those are decisions about the printing the picture imitates, not about the picture. That is why they are
arguments here and not something derived from the grey.

**The shapes, and why more than one.** A round dot is the default, and it has a ceiling: past fifty per cent the dots
start to touch and the screen can no longer get darker, so a print that wants eighty per cent has to switch. That is why
the catalogue is not a matter of taste -- each entry is what carries a particular range or a particular look:

    dot       the default; best below fifty per cent
    ellipse   a dot stretched on one axis, which keeps a middle grey readable well past fifty
    square    a hard-cornered dot for a mechanical or screen-printed look
    line      a band, for a flat tone that reads as ruling rather than as grain
    cross     two rulings at right angles, which is the shading a comic puts on a shadow
    noise     no lattice at all -- stochastic, for a texture that should not look ruled

Every one of them except `noise` is periodic and takes an `origin`, because a screen belongs to the page and not to the
shape it fills: two adjacent areas at the same pitch must continue each other's lattice, or their boundary reads as a
change of tone when it is only a change of value.
"""
import numpy as np

#: The lattice rotation, in degrees, that printing uses for a dot screen.
DEFAULT_ANGLE = 45.0
#: The distance between mark centres, in page pixels at the 2880 reference. Nine is a coarse comic screen; a finer one is
#: six to seven and a newspaper's is nearer four at this scale.
DEFAULT_PITCH = 9.0
#: How much of its length an ellipse keeps on its short axis. Seven tenths closes the gap between dots late enough that
#: the middle of the tonal range stays readable, which is the whole reason the ellipse exists.
DEFAULT_RATIO = 0.7
#: The seed a stochastic screen uses. Fixed so that the same project renders the same texture twice.
DEFAULT_SEED = 0


def _flat(width, height, value):
    """The two ends, which need no geometry at all."""
    if value <= 0.0:
        return np.zeros((height, width), dtype=np.float64), True
    if value >= 1.0:
        return np.ones((height, width), dtype=np.float64), True
    return None, False


def _rotated(width, height, origin, angle):
    """The cell coordinates in the lattice's own frame, offset so that the lattice belongs to the page."""
    row, column = np.mgrid[0:height, 0:width]
    row = row + float(origin[1])
    column = column + float(origin[0])
    theta = np.deg2rad(angle)
    along = column * np.cos(theta) + row * np.sin(theta)
    across = -column * np.sin(theta) + row * np.cos(theta)
    return along, across


def dot_screen(width, height, value, pitch=DEFAULT_PITCH, angle=DEFAULT_ANGLE, origin=(0.0, 0.0)):
    """Coverage for a value drawn as a rotated lattice of round dots.

    A dot of radius `r` in a cell of area `pitch * pitch` covers `pi r r / pitch²`, so `r = pitch * sqrt(value / pi)`.
    """
    flat, done = _flat(width, height, value)
    if done:
        return flat
    along, across = _rotated(width, height, origin, angle)
    du = (along % pitch) - pitch / 2.0
    dv = (across % pitch) - pitch / 2.0
    distance = np.hypot(du, dv)
    radius = pitch * np.sqrt(value / np.pi)
    return np.clip(radius + 0.5 - distance, 0.0, 1.0)


def ellipse_screen(width, height, value, pitch=DEFAULT_PITCH, angle=DEFAULT_ANGLE,
                   origin=(0.0, 0.0), ratio=DEFAULT_RATIO):
    """The same value as dots stretched on one axis.

    **Why this exists.** Round dots stop growing usefully near fifty per cent -- they touch, and a screen that has touched
    is a screen at its darkest. An ellipse grows along one axis after the other has closed, so the tonal range above the
    middle is still a range of sizes. A dot of semi-axes `a` and `b = a * ratio` covers `pi a b / pitch²`, so
    `a = pitch * sqrt(value / (pi * ratio))`.
    """
    flat, done = _flat(width, height, value)
    if done:
        return flat
    along, across = _rotated(width, height, origin, angle)
    du = (along % pitch) - pitch / 2.0
    dv = (across % pitch) - pitch / 2.0
    major = pitch * np.sqrt(value / (np.pi * ratio))
    minor = major * ratio
    # Normalised radius: one on the ellipse's own boundary, so the anti-aliasing width is one pixel of the minor axis.
    normalised = np.hypot(du / max(major, 1e-9), dv / max(minor, 1e-9))
    return np.clip(0.5 + (1.0 - normalised) * max(minor, 0.5), 0.0, 1.0)


def square_screen(width, height, value, pitch=DEFAULT_PITCH, angle=DEFAULT_ANGLE, origin=(0.0, 0.0)):
    """A square dot on the same rotated lattice.

    A square of half-side `h` covers `(2h)² / pitch²`, so `h = pitch * sqrt(value) / 2`. The edge is a `max` of the two
    offsets rather than a radius, which is what makes it square.
    """
    flat, done = _flat(width, height, value)
    if done:
        return flat
    along, across = _rotated(width, height, origin, angle)
    du = np.abs((along % pitch) - pitch / 2.0)
    dv = np.abs((across % pitch) - pitch / 2.0)
    half = 0.5 * pitch * np.sqrt(value)
    return np.clip(half + 0.5 - np.maximum(du, dv), 0.0, 1.0)


def line_screen(width, height, value, pitch=DEFAULT_PITCH, angle=DEFAULT_ANGLE, origin=(0.0, 0.0)):
    """The value as parallel bands, which is the other screen a comic uses for a flat tone.

    A band grows in one direction and its coverage is linear: a width `w` in a cell of width `pitch` covers `w / pitch`.
    """
    flat, done = _flat(width, height, value)
    if done:
        return flat
    _along, across = _rotated(width, height, origin, angle)
    dv = (across % pitch) - pitch / 2.0
    half = 0.5 * value * pitch
    return np.clip(half + 0.5 - np.abs(dv), 0.0, 1.0)


def cross_screen(width, height, value, pitch=DEFAULT_PITCH, angle=DEFAULT_ANGLE, origin=(0.0, 0.0)):
    """Two rulings at right angles, which is how a comic hatches a shadow.

    **The two must not simply be added.** Two rulings each at the requested value would cover `2v - v²`, so asking for
    half would deliver three quarters. Each ruling is solved for the value that makes the union land on the request:
    `v = 1 - sqrt(1 - value)`, which for half is 0.293 each.
    """
    flat, done = _flat(width, height, value)
    if done:
        return flat
    each = 1.0 - np.sqrt(max(0.0, 1.0 - value))
    _along, across = _rotated(width, height, origin, angle)
    first = 0.5 * each * pitch
    second = 0.5 * each * pitch
    band_a = np.clip(first + 0.5 - np.abs((across % pitch) - pitch / 2.0), 0.0, 1.0)
    _along2, across2 = _rotated(width, height, origin, angle + 90.0)
    band_b = np.clip(second + 0.5 - np.abs((across2 % pitch) - pitch / 2.0), 0.0, 1.0)
    return np.maximum(band_a, band_b)


def noise_screen(width, height, value, pitch=DEFAULT_PITCH, angle=DEFAULT_ANGLE,
                 origin=(0.0, 0.0), seed=DEFAULT_SEED):
    """A stochastic screen: no lattice, and the only shape here that is not periodic.

    **`pitch` is used as a blur, not as a spacing.** White noise thresholded at the value covers the value on average and
    looks like television static; blurring it first and renormalising gives clumps the size of the pitch, which is what a
    grain or a spatter tone reads as. The seed is fixed by default so that two renders of one project agree.
    """
    flat, done = _flat(width, height, value)
    if done:
        return flat
    # **The seed is the whole of the phase here.** A stochastic screen has no lattice to phase, and mixing the origin into
    # the seed would make one project's texture change when the page is scaled -- which is the failure a fixed seed is
    # there to prevent.
    rng = np.random.default_rng(int(seed))
    field = rng.random((height, width))
    if pitch > 1.5:
        from scipy import ndimage
        field = ndimage.uniform_filter(field, size=max(1, int(round(pitch / 3.0))), mode='wrap')
        spread = field.std()
        if spread > 1e-9:
            field = (field - field.mean()) / spread
    # **The threshold is a quantile, not the value itself.** `field` is normalised noise, so comparing it against `value`
    # compares a z-score against a coverage and delivers whatever the noise's own distribution happens to give -- asking
    # for half came back at 0.69. The `value` quantile of the field is the level below which that share of the pixels
    # lie, so the coverage is right by construction rather than by luck.
    threshold = float(np.quantile(field, value))
    spread = float(field.std()) or 1.0
    # A soft edge rather than a step: a stochastic screen whose boundary is a stair looks like a bitmap pasted on a
    # drawing whose lines are all anti-aliased.
    return np.clip((threshold - field) / (0.5 * spread) + 0.5, 0.0, 1.0)


#: The catalogue, by the name a project's `tone.shape` uses.
SCREENS = {
    'dot': dot_screen,
    'ellipse': ellipse_screen,
    'square': square_screen,
    'line': line_screen,
    'cross': cross_screen,
    'noise': noise_screen,
}


def screen(spec, width, height, scale=1.0, origin=(0.0, 0.0)):
    """Build the screen a project's `tone` field asks for.

    `scale` converts the pitch and the origin from page units to the pixels being drawn, because the pitch is a length on
    the page and the lattice belongs to the page. An unknown shape is refused rather than quietly drawn as dots.
    """
    shape = str(spec.get('shape', 'dot'))
    build = SCREENS.get(shape)
    if build is None:
        raise ValueError('unknown screen shape %r; known are %s' % (shape, ', '.join(sorted(SCREENS))))
    return build(width, height, float(spec.get('value', 0.5)),
                 pitch=float(spec.get('pitch', DEFAULT_PITCH)) * scale,
                 angle=float(spec.get('angle', DEFAULT_ANGLE)),
                 origin=(origin[0] * scale, origin[1] * scale),
                 **({'ratio': float(spec['ratio'])} if shape == 'ellipse' and 'ratio' in spec else {}),
                 **({'seed': int(spec['seed'])} if shape == 'noise' and 'seed' in spec else {}))


def value_of(screen_array, threshold=0.5):
    """The coverage a screen actually delivers, read back out of its own ink.

    **A screen is not linear in what it looks like.** The eye averages the ink, so the tone is the mean coverage, and that
    is what a print of a five-tenths screen should measure. This exists so a screen can be checked against the value it
    was asked for instead of being trusted.
    """
    return float((screen_array > threshold).mean())
