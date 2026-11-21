"""这个库自己的判断，做成可以问的东西。

**审美库现在有两种读者，而第二种没有入口。** 一种是人：`AESTHETIC-LIBRARY.md` 三百多 KB、`learn/` 下面六份
文件，互相引用，读一遍要半个钟头。另一种是程序：`tools/check_learn.py` 拿它们做七项检查，`roles.py` 与
`pigment.py` 各持一份事实的副本。

**于是「这个库知道什么」与「这个库认为什么画错了」在代码里没有名字。** 一个外部调用者要判断自己画得对不对，
能做的只有读 Markdown —— 而一次会话里读三百 KB 的代价，每次都要付。

三种问题，三种形状：

```python
from lineweight import aesthetic

aesthetic.names()                 # 四十七条事实的名字
aesthetic.fact('line_kinds')      # 一条：count / items / source
aesthetic.errors()                # 十种画错的模式，每种带「为什么」与「能不能查」
aesthetic.verify()                # 库与它自己的数据是否一致，返回问题列表
```

**`verify()` 必须在这里，而不只在 `tools/`。** 外部使用者拿不到 `tools/`，而「数据与代码是否还一致」正是
这条库最容易被破坏的地方：两份副本无声地漂移，这个工程已经因此把一条错阈值留用两轮。

**数据的位置有两种可能，因为打包之后 `learn/` 不在原位。** 源码树里它在仓库根；装成一个包之后它必须进
`lineweight/data/learn`。这个模块先找后者，再找前者，于是现在能用，而发布时只要把文件放对地方。
"""
from __future__ import annotations

import json
import os
import re

_LEARN = None


def learn_dir() -> str:
    """**先找包里那一份，再找旁边那一份。** 前者是发布后的位置，后者是源码树里的位置。"""
    global _LEARN
    if _LEARN is not None:
        return _LEARN
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, 'data', 'learn'), os.path.join(os.path.dirname(here), 'learn')):
        if os.path.isdir(candidate):
            _LEARN = candidate
            return _LEARN
    raise FileNotFoundError('no learn/ beside %s; the library data is missing' % here)


def _read(name: str) -> str:
    with open(os.path.join(learn_dir(), name), encoding='utf-8') as handle:
        return handle.read()


def facts() -> dict:
    """全部事实，包括 `purpose` 那一条说明。**返回的是文件里的形状，不改一个键。**"""
    return json.loads(_read('facts.json'))


def names() -> list:
    """事实的名字，排序之后。`purpose` 不是一条事实，它说明这个文件在收什么，所以不在里面。"""
    return sorted(key for key in facts() if key != 'purpose')


def fact(name: str) -> dict:
    """一条事实。名字不在表里时抛 `KeyError` 而不是返回空 —— 一个空字典读起来像一个「这条没有内容」的答案。"""
    table = facts()
    if name == 'purpose' or name in table:
        return table[name]
    raise KeyError('%r is not in facts.json; it has: %s' % (name, ', '.join(names())))


def errors() -> list:
    """画错的模式，按文件顺序。**每一行都是一个被看见过的错**，带位置、现象、原因与能不能查。"""
    rows = []
    for line in _read('errors.jsonl').splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def sources() -> list:
    """`sources.md` 里那张表的行，键是表头。**出处是这个库的证据，不是附注。**"""
    text = _read('sources.md')
    rows = []
    header = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if header is None:
            header = cells
            continue
        if all(set(cell) <= set('-: ') for cell in cells):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def extracts() -> object:
    """书页摘录的索引，原样返回。**它是一张列表，不是一张表** —— 每一项有 `file` / `book` / `page` / `name` / `why`。

    没有这一份时给空列表，因为摘录是可选的：一份只有 `sources.md` 的库仍然是一份库。
    """
    path = os.path.join(learn_dir(), 'extracts', 'index.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


PROSE = ('sources.md', 'README.md', 'model-parts.json')


def verify() -> list:
    """数据与读它的代码是否还一致。**返回问题列表，空列表才是一个通过。**

    **每一条都对应一种静默的错**：一个 count 与它的列表不符、一份出处不在书架里、一个字段两处各说一套。这些都
    不会让库跑不起来 —— 它会照常加载、照常读起来像真的，只在有人拿那条事实去做事的时候才露出来。
    """
    problems = []
    try:
        table = facts()
    except (OSError, ValueError) as error:
        return ['facts.json will not load: %s' % error]

    # 1 -- 一个 count 与它列的条数不符
    for key, entry in table.items():
        if not isinstance(entry, dict) or 'count' not in entry:
            continue
        items = entry.get('items')
        if items is None:
            # **有 `count` 而没有 `items` 不是错。** 有的条目数的是「几组轴」，它的内容是 `axes` 之类的另一把键。
            # 把这一条报成问题会让 `verify()` 每次带出十一条假警报，而一个总在报的检查等于没有检查。
            continue
        if entry['count'] != len(items):
            problems.append('%s says count %s but lists %d' % (key, entry['count'], len(items)))

    # 2 -- 一个出处不在书架里
    shelf_text = _read('sources.md')
    for key, entry in table.items():
        if not isinstance(entry, dict) or not entry.get('source'):
            continue
        quoted = str(entry['source'])
        # **两种出处，查法不同。** 从书里来的一条必须点名书架上的一本；而在本库里量出来的一条没有书可点，
        # `measured:` 前缀就是这个意思 —— 少了这条分支，每个测量都会被报成无出处的断言。
        if quoted.startswith('measured:'):
            continue
        # **页码要先摘掉。** 引用写 `Hampton p10.`，书架上写 `Michael Hampton`；整串比会把一本确实在架上的
        # 书报成没有出处 —— 第一版就是这么报的，四处。
        head = re.split(r'[,\'"(]', quoted)[0].strip()
        head = re.sub(r'\s+p\.?\s*\d+.*$', '', head).strip()
        candidates = [head]
        if 'MEDIBANG' in quoted:
            candidates = ['MEDIBANG']
        elif 'CLIP STUDIO' in quoted:
            candidates = ['CLIP STUDIO']
        if not any(candidate and candidate.lower() in shelf_text.lower() for candidate in candidates):
            problems.append('%s cites a source the shelf does not name: %s' % (key, head))

    # 4 -- 索引里点名的文件不在盘上
    index = extracts()
    if isinstance(index, dict):
        listing = index.get('extracts') or index.get('files') or []
        if isinstance(listing, dict):
            listing = list(listing.values())
    else:
        # **它是一张列表**，而写这段的时候以为是表 —— 于是第一版在这里抛了 `AttributeError`。一个索引的
        # 形状不是它的名字能说出来的东西。
        listing = index
    for item in listing:
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = str(item.get('file', ''))
        else:
            continue
        if name and not os.path.exists(os.path.join(learn_dir(), 'extracts', name)):
            problems.append('extracts/index.json names %r, which is not on disk' % name)

    # 6 -- 散文文件在，而且不是空的
    for name in PROSE:
        path = os.path.join(learn_dir(), name)
        if not os.path.exists(path):
            problems.append('%s is missing' % name)
        elif os.path.getsize(path) < 64:
            problems.append('%s is nearly empty' % name)

    # 7 -- 一条事实与读它的代码各说一套
    from . import pigment, roles

    entry = table.get('part_roles') or {}
    from_file = {(str(item.get('part')), str(item.get('role')))
                 for item in entry.get('items', []) if isinstance(item, dict)}
    from_code = set(roles.PART_ROLES.items())
    for part, role_name in sorted(from_file - from_code):
        problems.append('part %r is %r in facts.json but missing from roles.PART_ROLES' % (part, role_name))
    for part, role_name in sorted(from_code - from_file):
        problems.append('part %r is %r in roles.PART_ROLES but missing from facts.json' % (part, role_name))
    for part, role_name in sorted(from_code & from_file):
        if role_name not in roles.ROLES:
            problems.append('part %r is given the unknown role %r' % (part, role_name))

    order_entry = table.get('part_order') or {}
    tiers_file = tuple(tuple(tier) for tier in order_entry.get('items', []) if isinstance(tier, list))
    if tiers_file != roles.PART_TIERS:
        problems.append('part_order in facts.json is %r but roles.PART_TIERS is %r'
                        % (tiers_file, roles.PART_TIERS))

    mix_entry = table.get('paint_mix_operations') or {}
    listed = tuple(mix_entry.get('items', []))
    if listed != pigment.MIX_OPERATIONS:
        problems.append('paint_mix_operations in facts.json is %r but pigment.MIX_OPERATIONS is %r'
                        % (listed, pigment.MIX_OPERATIONS))
    added = mix_entry.get('added') or {}
    for name in pigment.MIX_OPERATIONS:
        if not added.get(name):
            problems.append('paint_mix_operations does not say what %r adds' % name)

    for pair in (table.get('pigment_opacity_pairs') or {}).get('items', []):
        if not isinstance(pair, dict):
            continue
        for side, expected in (('opaque', pigment.OPAQUE), ('transparent', pigment.TRANSPARENT)):
            named = pair.get(side)
            if not named:
                problems.append('pigment_opacity_pairs has a pair with no %r member' % side)
                continue
            # **比较的是表里那个颜料的不透明度，不是「名字在不在某个集合里」。** `OPAQUE` 与 `TRANSPARENT` 是
            # 两档常量的名字，不是两份名单；第一版把它们当名单查，于是六个颜料全被报成不在其中。
            key = str(named).replace(' ', '_')
            if key not in pigment.PIGMENTS:
                problems.append('pigment %r is paired in facts.json but missing from pigment.PIGMENTS' % named)
                continue
            actual = pigment.opacity_of(key)
            if actual != expected:
                problems.append('pigment %r is on the %s side of its pair but the table calls it %r'
                                % (named, side, actual))

    # 9 -- 十种错误模式，每一种都要说出它为什么发生
    for row in errors():
        for field in ('pattern', 'what', 'why'):
            if not row.get(field):
                problems.append('errors.jsonl has a row without a %r: %r'
                                % (field, row.get('pattern', '<unnamed>')))
    return problems
