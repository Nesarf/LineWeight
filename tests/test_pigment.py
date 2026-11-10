"""What a mixture does when the two tubes do not tint equally, and the two axes that get conflated.

The scripts each carried a four-line `mix(a, b, t)` before this module existed. It interpolated three numbers by the
ratio of the tubes, which silently assumed that scooping twice as much of a pigment moves the mixture twice as far.
Oil paint does not work that way, and the giveaway is a pair of pigments that disagree about the order: cadmium yellow
is opaque and weak, ultramarine is transparent and strong. A table that ranked one axis by the other would put them on
the same side, so two of the tests below are about the two axes staying independent.
"""

from lineweight import pigment


def test_equal_strengths_reproduce_the_straight_interpolation():
    """等强度时必须退化成旧的线性插值 —— 换进脚本之后，行为只在强度不同的地方变。"""
    middle = pigment.mix_by_strength((0.0, 0.0, 0.0), (255.0, 255.0, 255.0), 0.5, 1.0, 1.0)
    assert middle == (127.5, 127.5, 127.5)
    assert pigment.mix_by_strength((10.0, 20.0, 30.0), (100.0, 200.0, 300.0), 0.0, 1.0, 1.0) == (10.0, 20.0, 30.0)
    assert pigment.mix_by_strength((10.0, 20.0, 30.0), (100.0, 200.0, 300.0), 1.0, 1.0, 1.0) == (100.0, 200.0, 300.0)


def test_the_stronger_pigment_reaches_further_into_the_mixture():
    """同样一半的量，着色力强的那一边占的比例更大 —— 这是这个模块存在的唯一理由。"""
    weak, strong = 0.25, 0.75
    toward_weak = pigment.mix_by_strength((0.0, 0.0, 0.0), (100.0, 100.0, 100.0), 0.5, weak, strong)
    toward_strong = pigment.mix_by_strength((0.0, 0.0, 0.0), (100.0, 100.0, 100.0), 0.5, strong, weak)
    assert toward_weak[0] > 50.0
    assert toward_strong[0] < 50.0
    assert toward_weak[0] + toward_strong[0] == 100.0


def test_the_white_you_tint_into_decides_how_far_the_tint_reaches():
    """同样比例的群青：进锌白里明显比进钛白里更蓝 —— 白色的强弱决定一条 tint ladder 的坡度。

    这一条本来是写反的。第一版断言「一成群的群青进钛白就已经很蓝」，而算出来只走到二百三十三：**钛白把
    一切吃掉了**，这不是算错，是钛白确实如此。所以能判定的不是「一点就够」，而是「换一种白，同一点就走得
    更远」—— 这也正是 W&N 把 mixing white 与 titanium white 分开写一篇的理由。
    """
    into_titanium = pigment.mix_pigments('titanium_white', 'ultramarine_blue', 0.10)
    into_zinc = pigment.mix_pigments('zinc_white', 'ultramarine_blue', 0.10)
    assert into_zinc[0] < into_titanium[0] < 250.0


def test_opacity_and_strength_are_independent_axes():
    """两个轴必须能互相反驳：不透明的颜料可能着色力弱，透明的可能强。"""
    assert pigment.opacity_of('cadmium_yellow') == pigment.OPAQUE
    assert pigment.strength_of('cadmium_yellow') < pigment.strength_of('ultramarine_blue')
    assert pigment.opacity_of('ultramarine_blue') == pigment.TRANSPARENT
    # 反过来也要成立一次，否则「独立」只是单向的巧合
    assert pigment.opacity_of('titanium_white') == pigment.OPAQUE
    assert pigment.strength_of('titanium_white') > pigment.strength_of('zinc_white')
    assert pigment.opacity_of('zinc_white') != pigment.OPAQUE


def test_zinc_white_tints_less_than_titanium_white_at_the_same_ratio():
    """同一比例的加白，锌白比钛白弱 —— 这是表中那个「半透明且弱」的白色存在的意思。"""
    base = (60.0, 90.0, 140.0)
    titanium = pigment.tint(base, 0.30, 'titanium_white')
    zinc = pigment.tint(base, 0.30, 'zinc_white')
    assert titanium[0] > zinc[0]
    assert zinc[0] > base[0]


def test_adding_black_at_a_small_ratio_already_darkens():
    """加黑不是「按比例变暗」：一成黑让明度掉了十几点，但没有塌掉。

    第一版写成「一成黑压掉大半明度」，算出来是二百降到一百八十五 —— 断言写的是感觉，不是这个式子。
    能判定的是两件事：掉得足够看得见，且远没有到一半。
    """
    base = (200.0, 190.0, 180.0)
    shaded = pigment.shade(base, 0.10)
    assert shaded[0] < base[0] - 10.0
    assert shaded[0] > base[0] * 0.85
    assert shaded[0] > 0.0


def test_the_three_operations_are_the_three_the_handbooks_name():
    """tint / shade / tone 是可数清单，顺序与名字都要和事实库对得上。"""
    assert pigment.MIX_OPERATIONS == ('tint', 'shade', 'tone')
    base = (120.0, 100.0, 80.0)
    for name in pigment.MIX_OPERATIONS:
        moved = pigment.operate(base, name, 0.5)
        assert moved != base


def test_a_tone_stays_lighter_than_a_shade_at_the_same_ratio():
    """同样比例的加灰与加黑：两者都降彩度，但灰把明度留住，黑不留 —— 这才是两者并列的理由。

    第一版断言「加灰保留色相更多」，算出来两边几乎一样（红蓝差八十五对八十六），因为往中性灰走也把差距
    减半。能判定的差别在明度：加灰之后三个通道的和明显高于加黑之后。
    """
    base = (200.0, 80.0, 40.0)
    grey = pigment.tone(base, 0.5)
    black = pigment.shade(base, 0.5)
    assert sum(grey) > sum(black)
    assert max(grey) - min(grey) < max(base) - min(base)
    assert max(black) - min(black) < max(base) - min(base)


def test_an_unknown_pigment_or_operation_is_refused_by_name():
    """拼错的颜料名要报出可用的那些，而不是悄悄给一个默认色。"""
    for call in (lambda: pigment.pigment('burnt_sienna'),
                 lambda: pigment.operate((0.0, 0.0, 0.0), 'glaze', 0.5)):
        try:
            call()
        except KeyError as error:
            assert 'known:' in str(error)
        else:
            raise AssertionError('a bad name was accepted')


def test_the_table_holds_every_opacity_class():
    """三个不透明度等级都要有实例，否则那个等级等于没定义。"""
    classes = {row[1] for row in pigment.PIGMENTS.values()}
    assert set(pigment.OPACITY_CLASSES) <= classes
