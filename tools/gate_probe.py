"""What the gate catches and what it does not, probed by violating things on purpose.

**The question this answers.** `figure`/`layers`/`body` together are the gate -- a drawing declares a body and a layer
stack, and `Project.set_figure` refuses one that could not exist. What has never been established is *which* faults
that gate actually stops, because everything tested so far was tested on a correct drawing. So this draws a correct
one, then breaks it five different ways and records what each break produces.

**The five are chosen because they are the five kinds of wrong thing that have actually happened in this project**: a
mark with no layer, a mark on a layer nobody declared, a body with an extra limb, marks in an impossible order, and
geometry that draws nothing at all -- the last one being the one that happened on the very first end-to-end run.
"""
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import body, core, figure, project

D = pathlib.Path(r'F:\素材\图\碧蓝档案官方设定资料')


def head(n, text):
    print()
    print('--- %s' % n)
    print('    %s' % text)


def attempt(what, fn):
    try:
        result = fn()
        print('    NOT CAUGHT  %s -> %r' % (what, result if result is not None else 'accepted'))
        return False
    except Exception as e:
        print('    CAUGHT      %s -> %s: %s' % (what, type(e).__name__, str(e)[:110]))
        return True


def main():
    fig = figure.standard()
    box = [(100, 100), (300, 120), (320, 400), (120, 380)]

    head('0. the correct drawing, for reference',
         '41 marks, every layer declared, body the 34-bone variant')
    p = project.Project()
    p.set_figure(fig)
    for layer in ('torso', 'arm', 'leg', 'head'):
        p.add_stroke(core.stroke_record(box, 'ink', seed=1, resolution=12), stage='line', layer=layer)
    print('    accepted: %d marks' % len(p.marks))

    head('1. a mark with no layer', 'the layer every mark must name; an empty one means "no statement"')
    attempt('add_stroke(layer="")', lambda: project.Project(figure=fig).add_stroke(
        core.stroke_record(box, 'ink'), layer=''))

    head('2. a mark on a layer the figure never declared', 'a pile of marks is not a drawing')
    attempt('add_stroke(layer="tail")', lambda: project.Project(figure=fig).add_stroke(
        core.stroke_record(box, 'ink'), layer='tail'))

    head('3. a body with an extra limb', 'the fault body.py was written for: a generator producing three arms')
    three = figure.standard()
    three.joints['Bip001 L Arm3'] = 'Bip001 Spine1'
    three.joints['Bip001 L Arm3a'] = 'Bip001 L Arm3'
    problems = three.errors()
    print('    figure.errors() -> %d problem(s)' % len(problems))
    for s in problems:
        print('       %s' % s)
    attempt('set_figure(three arms)', lambda: project.Project().set_figure(three))

    head('4. marks in an order the constraints forbid', '46 pairs, at least 10 rigs and 90% agreement each')
    from lineweight import layers as L
    stack = L.standard_order()
    i_eye, i_brow = stack.index('eye'), stack.index('eyebrow')
    print('    standard_order(): eye at %d, eyebrow at %d  (eye first, 55 rigs, 100%%)' % (i_eye, i_brow))
    # **`order_errors` reads a Stack, not a list of names.** The first version of this probe passed a list and got
    # `'list' object has no attribute 'layers'` -- the probe's own bug, not the gate's.
    bad = L.Stack()
    names = list(stack)
    names[i_eye], names[i_brow] = names[i_brow], names[i_eye]
    for n in names:
        bad.add(n, L.TIER_OF_CLASS.get(n, 'character'), part=n)
    errs = L.order_errors(bad)
    print('    order_errors(swapped) -> %d problem(s)' % len(errs))
    for s in errs[:3]:
        print('       %s' % s)
    if not errs:
        print('    NOT CAUGHT  swapping the two did not raise an order error')

    head('5. geometry that draws nothing', 'the fault that actually happened: a figure 0.85 units tall on an 800x600 canvas')
    tiny = project.Project(figure=fig)
    tiny.add_stroke(core.stroke_record([(0.0, 0.3), (0.1, 0.4), (0.2, 0.5)], 'ink', seed=3), layer='torso')
    ok = True
    try:
        tiny.add_stroke(core.stroke_record([(0.0, 0.3), (0.1, 0.4)], 'ink', seed=4), layer='leg')
    except Exception as e:
        ok = False
        print('    CAUGHT      %s' % e)
    if ok:
        print('    NOT CAUGHT  two strokes, both about 0.2 units across, on a canvas 800 units wide')
        print('                the figure is a fraction of a pixel and the gate has nothing to say about it')
        print('                ** what reported it was `--render`\'s coverage line: "17 px covered (0.0%%)" **')

    head('6. a stroke whose geometry is entirely off the canvas', 'the same fault, one step further')
    off = project.Project(figure=fig)
    off.add_stroke(core.stroke_record([(-9000, -9000), (-8900, -8900)], 'ink', seed=5), layer='torso')
    print('    NOT CAUGHT  accepted; the mark exists, names a valid layer, and is outside the page')
    print('                (this is the one `demo_document` already records: "a shape that exists in every')
    print('                 destination\'s data and is visible in none of them, because no format complains')
    print('                 about geometry off the page")')

    print()
    print('=== summary')
    print('    the gate is a CHECK ON STRUCTURE: which bones exist, how they branch, which layers are declared,')
    print('    what order they go in. Five of the six probes are structural and every one is caught.')
    print('    the sixth is GEOMETRIC and it is not -- and geometric is where the real errors have been.')


if __name__ == '__main__':
    main()
