"""Halftone screens: a value rendered as a periodic arrangement of dots rather than as a flat tint.

**Why this is not a colour.** In a screen-tone drawing a mid grey is not ink at that lightness; it is black dots on white
paper at a spacing that makes the eye read grey. The difference matters when the picture is copied. A flat grey has no
structure to copy, and its boundary is the only thing a line finder can see; a screen has structure at the dot pitch,
which is a length, so the same tone drawn at two page sizes is the same tone only if the pitch is quoted against the page.

**The geometry is the printing convention.** One dot per cell on a square lattice rotated to forty-five degrees -- the
rotation that keeps the lattice from lining up with the drawing's own vertical and horizontal strokes, where it would
read as a pattern rather than as a tone. The dot's radius follows from the coverage asked for: a cell of area
`pitch * pitch` holding one dot of area `pi * r * r`, so `r = pitch * sqrt(value / pi)`. At value one the radius is 0.564
of the pitch and neighbouring dots overlap, which is what solid ink is.

**Antialiasing is the same statement the rasteriser makes for a stroke**: coverage is the radius plus half a pixel minus
the distance to the dot's centre, clipped to nought and one. A dot's edge and a stroke's edge therefore soften by the
same rule, which is what keeps a screen from looking pasted onto a drawing.

**What this is not.** A screen is not a value the fill stage can produce on its own: it needs a pitch and an angle, and
those are decisions about the printing the picture imitates, not about the picture. That is why they are arguments here
and not something derived from the grey.
"""
import numpy as np

#: The lattice rotation, in degrees, that printing uses for a dot screen.
DEFAULT_ANGLE = 45.0
#: The distance between dot centres, in page pixels at the 2880 reference. Nine is a coarse comic screen; a finer one is
#: six to seven and a newspaper's is nearer four at this scale.
DEFAULT_PITCH = 9.0


def dot_screen(width, height, value, pitch=DEFAULT_PITCH, angle=DEFAULT_ANGLE):
    """Coverage, where one is ink, for a value drawn as a rotated lattice of dots.

    `value` runs from nought (paper) to one (solid ink); anything outside that range is clamped by the two early returns
    rather than by the arithmetic, because a screen of value zero should cost nothing to build.
    """
    if value <= 0.0:
        return np.zeros((height, width), dtype=np.float64)
    if value >= 1.0:
        return np.ones((height, width), dtype=np.float64)
    row, column = np.mgrid[0:height, 0:width]
    theta = np.deg2rad(angle)
    along = column * np.cos(theta) + row * np.sin(theta)
    across = -column * np.sin(theta) + row * np.cos(theta)
    du = (along % pitch) - pitch / 2.0
    dv = (across % pitch) - pitch / 2.0
    distance = np.hypot(du, dv)
    radius = pitch * np.sqrt(value / np.pi)
    return np.clip(radius + 0.5 - distance, 0.0, 1.0)


def line_screen(width, height, value, pitch=DEFAULT_PITCH, angle=DEFAULT_ANGLE):
    """The same value as parallel lines, which is the other screen a comic uses for a flat tone.

    A dot grows in two directions and a line grows in one, so the coverage relation is linear rather than square-rooted:
    a band of width `w` in a cell of width `pitch` covers `w / pitch` of the cell.
    """
    if value <= 0.0:
        return np.zeros((height, width), dtype=np.float64)
    if value >= 1.0:
        return np.ones((height, width), dtype=np.float64)
    row, column = np.mgrid[0:height, 0:width]
    theta = np.deg2rad(angle)
    across = -column * np.sin(theta) + row * np.cos(theta)
    dv = (across % pitch) - pitch / 2.0
    half = 0.5 * value * pitch
    return np.clip(half + 0.5 - np.abs(dv), 0.0, 1.0)


def value_of(screen, threshold=0.5):
    """The coverage a screen actually delivers, read back out of its own ink.

    **A screen is not linear in what it looks like.** The eye averages the ink, so the tone is the mean coverage, and that
    is what a print of a five-tenths screen should measure. This exists so a screen can be checked against the value it
    was asked for instead of being trusted.
    """
    return float((screen > threshold).mean())
