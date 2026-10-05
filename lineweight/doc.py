"""A drawing as a document, rather than as a string of SVG.

**Why this file exists.** Everything before it produced SVG text directly, which was fine while SVG was the only
destination. It stops being fine the moment the same drawing has to arrive in Illustrator as layers, in Animate as
importable outlines, and in SAI as a layered raster: those are three different shapes of the same drawing, and a
string cannot be re-shaped. So the drawing is built once, here, as structure -- layers holding paths, each path
carrying geometry and the appearance of that geometry -- and every writer walks that structure.

**Coordinates are SVG's**, x right and y **down**, because that is what `core` produces and what a drawing measured
from a picture has. Flipping the axis is a decision that belongs to the writer that needs it (Illustrator's y is up),
and it is easier to get right in one place per writer than to keep two conventions alive in the model.

**A path here is already an outline, not a stroke.** `lineweight` expands a variable-width stroke into a filled
contour before it ever reaches this file, which is the whole point of the library: the weight lives in the geometry,
so no destination has to support variable-width strokes to receive it. A path may also be carried as a plain
centre line to be stroked uniformly, which is what small details and construction lines want.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[float, float]


@dataclass
class Appearance:
    """How a path is painted. Kept separate from geometry because the same shape is often drawn twice.

    `opacity` is 0-1, as it is everywhere else in this library; the writers that want percentages convert. `stroke`
    is only consulted when `filled` is false, so a path never silently loses one of the two.
    """
    fill: str = '#1A1620'
    stroke: str | None = None
    stroke_width: float = 1.0
    opacity: float = 1.0
    filled: bool = True

    def as_filled(self, colour: str | None = None, opacity: float | None = None) -> 'Appearance':
        return Appearance(fill=colour or self.fill, stroke=None, stroke_width=self.stroke_width,
                          opacity=self.opacity if opacity is None else opacity, filled=True)

    def as_stroked(self, colour: str | None = None, width: float | None = None) -> 'Appearance':
        return Appearance(fill=self.fill, stroke=colour or self.stroke or self.fill,
                          stroke_width=self.stroke_width if width is None else width,
                          opacity=self.opacity, filled=False)


@dataclass
class Path:
    """One piece of geometry, in SVG coordinates, either filled (an outline) or stroked (a centre line)."""
    points: list[Point]
    appearance: Appearance = field(default_factory=Appearance)
    closed: bool = True
    name: str = ''

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError('a path needs at least two points, got %d' % len(self.points))

    def bounds(self) -> tuple[float, float, float, float]:
        xs = [x for x, _ in self.points]
        ys = [y for _, y in self.points]
        return min(xs), min(ys), max(xs), max(ys)

    def extent(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bounds()
        return x1 - x0, y1 - y0


@dataclass
class Layer:
    """A named layer. Layers are the unit every destination agrees on: Illustrator and Animate both have them,
    and a layered raster needs them, so a drawing that is not layered cannot be handed to any of the three."""
    name: str
    paths: list[Path] = field(default_factory=list)
    visible: bool = True
    locked: bool = False

    def add(self, path: Path) -> Path:
        self.paths.append(path)
        return path

    def bounds(self) -> tuple[float, float, float, float] | None:
        boxes = [p.bounds() for p in self.paths]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))


@dataclass
class Document:
    """A drawing: layers, and the canvas they sit on."""
    width: float = 800.0
    height: float = 600.0
    layers: list[Layer] = field(default_factory=list)
    title: str = 'lineweight'

    def layer(self, name: str) -> Layer:
        """Get-or-create by name, so callers can address layers without tracking them."""
        for existing in self.layers:
            if existing.name == name:
                return existing
        created = Layer(name=name)
        self.layers.append(created)
        return created

    def add(self, path: Path, layer: str = 'LINE') -> Path:
        return self.layer(layer).add(path)

    def paths(self) -> list[Path]:
        return [p for layer in self.layers for p in layer.paths]

    def bounds(self) -> tuple[float, float, float, float] | None:
        boxes = [b for b in (layer.bounds() for layer in self.layers) if b is not None]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def counts(self) -> dict[str, int]:
        return {'layers': len(self.layers), 'paths': len(self.paths()),
                'points': sum(len(p.points) for p in self.paths())}


# ---------------------------------------------------------------- colour

def parse_colour(value: str) -> tuple[int, int, int]:
    """`#RGB`, `#RRGGBB` and `#RRGGBBAA` into 0-255 triples. Alpha is dropped here because every destination
    carries opacity as its own property rather than folded into the colour."""
    text = value.strip().lstrip('#')
    if len(text) == 3:
        text = ''.join(c * 2 for c in text)
    if len(text) not in (6, 8):
        raise ValueError('not a hex colour: %r' % value)
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError as exc:
        raise ValueError('not a hex colour: %r' % value) from exc


def format_colour(rgb: tuple[int, int, int]) -> str:
    return '#%02X%02X%02X' % rgb


# ---------------------------------------------------------------- building from the stroke model

def from_strokes(strokes: list[dict], width: float | None = None, height: float | None = None,
                 layer: str = 'LINE') -> Document:
    """Turns expanded strokes into a layered document.

    Each stroke may carry its own colour and layer, because in real linework they are not uniform: the contour of a
    silhouette, the lines inside a face and a construction line are three different decisions, and flattening them
    into one layer here would throw away the only structure the destinations understand.
    """
    doc = Document()
    for item in strokes:
        points = list(item['outline'])
        if len(points) < 2:
            continue
        doc.add(Path(points=points,
                     appearance=Appearance(fill=item.get('colour', '#1A1620'), filled=True,
                                           opacity=float(item.get('opacity', 1.0))),
                     closed=True,
                     name=item.get('name', '')),
                layer=item.get('layer', layer))
    if width is not None:
        doc.width = width
    if height is not None:
        doc.height = height
    boxes = doc.bounds()
    # **The canvas is sized to the drawing, and the test has to be against the argument rather than the attribute.**
    # `Document` defaults its canvas to 800x600, so checking `height is None` after construction is never true and
    # the size was silently left at the default -- a generated document whose canvas had nothing to do with its
    # contents. The size a caller passed is the one fact this function has that `Document` does not.
    if boxes:
        if width is None:
            doc.width = boxes[2] + 20
        if height is None:
            doc.height = boxes[3] + 20
    return doc
