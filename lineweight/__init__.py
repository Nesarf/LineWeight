"""Weighted linework without a tablet.

Public surface: a brush, a pressure model, a stroke-to-outline expander, a calibration measurement, and the bridges
that carry the result into a drawing application.

    from lineweight import BRUSHES, stroke, inked_svg

    d, opacity = stroke([(0, 0), (100, 20), (200, 0)], 'ink')
    #  d is a filled outline in SVG path syntax, with the width already varied along it

    from lineweight import Document, jsx_document
    #  the same drawing as a layered document, and then as a script Illustrator runs natively

`Layer` is the document model's. The raster compositor has a `Layer` of its own, which stays reachable as
`lineweight.raster.Layer` rather than being shadowed here -- two different things under one name is how a caller ends
up passing the wrong one to something that will not complain.
"""
from .core import (BRUSHES, Region, from_record, inked_svg, load_strokes, outline, parse_path, parse_transform,
                    pressures, region_fill, save_strokes, stroke, stroke_record, weld_endpoints)

__all__ = ['BRUSHES', 'stroke', 'stroke_record', 'from_record', 'save_strokes', 'load_strokes',
           'inked_svg', 'outline', 'pressures', 'parse_path', 'parse_transform', 'weld_endpoints', 'region_fill',
           'Region']
__version__ = '0.1.0'

from .doc import (Appearance, Document, Layer, Path, from_strokes, parse_colour,  # noqa: E402,F401
                  resize_to_fit)
from .app import jsx_document  # noqa: E402,F401
from .xfl import write_xfl  # noqa: E402,F401
from .ref import Greyscale, measure, scan, summarise, compare, check  # noqa: E402,F401
from .project import (DEFAULT_STAGES, LIVE, SUPERSEDED, Mark, Project,  # noqa: E402,F401
                      load_project, save_project)
from . import run  # noqa: E402,F401

__all__ += ['Document', 'Layer', 'Path', 'Appearance', 'from_strokes', 'parse_colour', 'jsx_document',
            'write_xfl', 'run', 'resize_to_fit',
            'Greyscale', 'measure', 'scan', 'summarise', 'compare', 'check',
            'Project', 'Mark', 'save_project', 'load_project', 'DEFAULT_STAGES', 'LIVE', 'SUPERSEDED']
