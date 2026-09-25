"""Weighted linework without a tablet.

Public surface: a brush, a pressure model, a stroke-to-outline expander, and a calibration measurement.

    from lineweight import BRUSHES, stroke, inked_svg

    d, opacity = stroke([(0, 0), (100, 20), (200, 0)], 'ink')
    #  d is a filled outline in SVG path syntax, with the width already varied along it
"""
from .core import (BRUSHES, from_record, inked_svg, load_strokes, outline, parse_path, pressures,
                    region_fill, save_strokes, stroke, stroke_record, weld_endpoints)

__all__ = ['BRUSHES', 'stroke', 'stroke_record', 'from_record', 'save_strokes', 'load_strokes',
           'inked_svg', 'outline', 'pressures', 'parse_path', 'weld_endpoints', 'region_fill']
__version__ = '0.1.0'

from .raster import Layer, blend, clip, composite, stroke_layer  # noqa: E402,F401
