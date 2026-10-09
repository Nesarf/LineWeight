"""Tests for the surface.

`grain` on a brush says how much a medium shows the tooth; a `Paper` says what the tooth *is*. Without it, "pencil on
smooth cartridge" and "pencil on rough watercolour paper" are the same drawing, which is the gap the per-stroke
specification names as media simulation.

The rule that decides whether adding the field was worth anything is the same one the profiles are held to: **a field
the renderer ignores is a comment**, so every property is tested by changing it and measuring the picture.
"""

import pytest

from lineweight import raster
from lineweight.core import stroke_record


def a_record(brush='pencil'):
    rec = stroke_record([(20, 60), (90, 30), (160, 80), (230, 40)], brush, seed=11)
    return {'brush': rec['brush'], 'centre': rec['centre'], 'pressure': rec['pressure'],
            'seed': rec['seed'], 'colour_int': (26, 26, 26)}


def ink_and_shape(layer):
    data = layer.data
    return sum(data[3::4]) / 255.0, sum(1 for i in range(3, len(data), 4) if data[i] > 0)


def test_the_default_paper_is_exactly_the_old_behaviour():
    """**The compatibility guarantee, and it is byte-for-byte rather than approximate.**

    Every layer written before this existed has no paper. Naming nothing has to reproduce the old sampling exactly,
    which is why `Paper.at` special-cases the identity instead of dividing by a scale of 1.0 -- a default that is
    *nearly* the old behaviour would be worse than one that is exactly it, because the difference would show up as an
    unexplained one-bit change in a rendered image.
    """
    assert raster.PAPERS['default'].tooth == 1.0
    assert raster.PAPERS['default'].scale == 1.0
    assert raster.PAPERS['default'].direction == 0.0
    for x, y in ((0.0, 0.0), (12.5, 80.0), (63.25, 7.75), (199.0, 119.0)):
        assert raster.PAPERS['default'].at(x, y, 0) == raster.grain_at(x, y, 0)
        assert raster.PAPERS['default'].at(x, y, 7) == raster.grain_at(x, y, 7)
    plain = raster.stroke_layer(a_record(), 260, 120, 1.0)
    named = raster.stroke_layer(a_record(), 260, 120, 1.0, paper=raster.PAPERS['default'])
    assert plain.data == named.data, 'naming the default surface changed the render'


def test_a_paper_changes_the_surface_and_not_the_shape():
    """The signature that separates a surface from a brush: ink moves, the touched-pixel count does not.

    A surface modulates how much of each dab is laid down. If a paper changed the outline it would be a geometry
    setting wearing a texture's name, and the shape of a drawing would depend on which sheet it was painted on.
    """
    plain_ink, plain_shape = ink_and_shape(raster.stroke_layer(a_record(), 260, 120, 1.0))
    for name in ('smooth', 'drawing', 'rough', 'canvas'):
        ink, shape = ink_and_shape(raster.stroke_layer(a_record(), 260, 120, 1.0, paper=raster.PAPERS[name]))
        # within a percent rather than exactly: a lighter tooth lets a rim pixel or two round above zero and start
        # counting as painted. That is a rounding effect at the bottom of the range, not a shape change, and asserting
        # equality would be asserting the rounding.
        assert abs(shape - plain_shape) <= plain_shape * 0.01, '%s changed the shape' % name
        assert ink != pytest.approx(plain_ink), '%s did not reach the renderer' % name


def test_more_tooth_means_less_ink():
    """The amplitude does what its name says, checked as an ordering rather than as four separate numbers."""
    inks = {}
    for name in ('smooth', 'default', 'drawing', 'rough'):
        inks[name] = ink_and_shape(raster.stroke_layer(a_record(), 260, 120, 1.0,
                                                       paper=raster.PAPERS[name]))[0]
    assert inks['smooth'] > inks['default'] > inks['rough'], inks


def test_direction_makes_the_tooth_anisotropic():
    """A woven or laid sheet has a direction, and the point of the field is that a horizontal and a vertical sample
    disagree, which neither `tooth` nor `scale` can produce."""
    canvas = raster.PAPERS['canvas']
    assert canvas.direction > 0
    along_x = [canvas.at(x, 60.0, 0) for x in range(20, 220, 4)]
    along_y = [canvas.at(120.0, y, 0) for y in range(5, 115, 2)]

    def variation(values):
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    isotropic = raster.PAPERS['drawing']
    assert isotropic.direction == 0.0
    assert abs(variation(along_x) - variation(along_y)) > 0.002, 'direction did not stretch the tooth'


def test_the_paper_belongs_to_the_layer_and_does_not_leak_between_them():
    """Two layers are two sheets. A surface stored anywhere global would make the second one's tooth depend on the
    first one's, which is the sort of coupling that shows up as a picture that changes when an unrelated layer is
    added."""
    fine = raster.Layer(40, 40, paper=raster.PAPERS['smooth'])
    rough = raster.Layer(40, 40, paper=raster.PAPERS['rough'])
    assert fine.paper is raster.PAPERS['smooth']
    assert rough.paper is raster.PAPERS['rough']
    default = raster.Layer(40, 40)
    assert default.paper is raster.PAPERS['default']


def test_an_unknown_paper_is_refused_by_the_command_line_rather_than_guessed(tmp_path):
    """A name that is not in the table is an error naming the ones that are, like every other registry here.

    Driven through the real command line rather than by repeating the guard, because the guard living in the CLI and
    the guard being *reachable* from the CLI are two different claims.
    """
    import subprocess
    import sys
    from lineweight import Project, save_project
    from lineweight.core import stroke_record

    project = Project(width=120, height=120)
    project.add_stroke(stroke_record([(10, 10), (100, 100)], 'ink', seed=1))
    path = str(tmp_path / 'p.json')
    save_project(project, path)

    out = subprocess.run([sys.executable, '-m', 'lineweight', '--render', path,
                          '--out', str(tmp_path / 'o.png'), '--paper', 'cartridge'],
                         capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=180)
    assert out.returncode != 0
    assert 'cartridge' in (out.stderr + out.stdout)
    assert 'rough' in (out.stderr + out.stdout)

    # and a known one works
    good = subprocess.run([sys.executable, '-m', 'lineweight', '--render', path,
                           '--out', str(tmp_path / 'o.png'), '--paper', 'rough'],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=180)
    assert good.returncode == 0, good.stderr[-800:]


def test_the_surface_reaches_a_medium_that_declares_no_grain_of_its_own():
    """**The defect this field had on its first working version, kept as a test.**

    The paper was applied only when the brush declared `grain > 0`, and `ink` declares exactly 0 -- so **four
    different surfaces rendered to byte-identical files** and the feature was inert for the medium this library
    mostly draws in. Found by running the command line over the same project with `--paper` four times and getting
    the same byte count back every time, which is the sort of thing no unit test of the parts would have caught: each
    part was right, and the guard between them was on the wrong thing.

    A rough sheet makes even a loaded pen stutter, so the amplitude is `max(brush * tooth, bite)` and the guard is on
    the surface rather than on the brush.
    """
    assert raster.BRUSHES['ink']['grain'] == 0.0, 'this test is about a medium with no grain of its own'
    inks = {}
    for name in ('default', 'smooth', 'drawing', 'rough', 'canvas'):
        inks[name] = ink_and_shape(raster.stroke_layer(a_record(brush='ink'), 260, 120, 1.0,
                                                       paper=raster.PAPERS[name]))[0]
    assert inks['default'] == pytest.approx(inks['smooth']), 'a smooth sheet should not bite an ink line'
    assert inks['rough'] < inks['drawing'] < inks['default'], inks
    assert len(set(round(v, 3) for v in inks.values())) >= 4, 'the surfaces are still not distinguishable'


def test_bite_is_a_floor_and_tooth_is_a_multiplier():
    """Two fields because they answer two questions, and the difference is visible on the same brush.

    `tooth` scales what the medium reveals; `bite` is what the surface removes regardless. A soft medium (a wash at
    grain 0.45) is dominated by `tooth` and a loaded pen by `bite`, and a single number could not express both.
    """
    wash = a_record(brush='wash')
    assert raster.BRUSHES['wash']['grain'] > 0.3
    rough, smooth = raster.PAPERS['rough'], raster.PAPERS['smooth']
    assert rough.bite > 0.0 and smooth.bite == 0.0
    # the wash reacts to tooth: a smoother sheet leaves more of it
    wash_rough = ink_and_shape(raster.stroke_layer(wash, 260, 120, 1.0, paper=rough))[0]
    wash_smooth = ink_and_shape(raster.stroke_layer(wash, 260, 120, 1.0, paper=smooth))[0]
    assert wash_smooth > wash_rough
