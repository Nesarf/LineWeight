"""Weighted linework without a tablet.

Public surface: a brush, a pressure model, a stroke-to-outline expander, and a calibration measurement.

    from lineweight import BRUSHES, stroke, inked_svg

    d, opacity = stroke([(0, 0), (100, 20), (200, 0)], 'ink')
    #  d is a filled outline in SVG path syntax, with the width already varied along it
"""
from .core import BRUSHES, inked_svg, outline, parse_path, pressures, stroke

__all__ = ['BRUSHES', 'stroke', 'inked_svg', 'outline', 'pressures', 'parse_path']
__version__ = '0.1.0'
