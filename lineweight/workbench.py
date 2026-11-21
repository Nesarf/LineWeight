"""画一笔、查一次、不满意就改、再查一次 —— 三层里唯一有状态的那一层。

**前两层是只读的。** `aesthetic` 只回答「这个库知道什么」，`standards` 只回答「这一笔画对了吗」。而真正画画的
时候这两件事交替发生，而交替本身就是最容易漏掉的部分：画完一笔要查，查完要改，改完要再查 —— 每一次都得自己
记着上一支笔的 id。

这个模块把那个循环收进一个对象：

```python
from lineweight import workbench

session = workbench.Session(1400, 900, title='a face')
lid = session.stroke(points, 'brush', layer='eye', note='the upper lid')

print(session.check(lid.id)[0].line())
#   line   FAIL  stroke variation   1.0000  < 0.95, and a flat line sits at 1.00

session.revise(lid.id, width_profile=[2.4, 4.4, 4.0, 2.0])
print(session.check(lid.id)[0].line())
#   line   ok    stroke variation   0.3912  < 0.95, and a flat line sits at 1.00

session.save('face.json')
```

**它不新做任何一件事。** `stroke` 是 `stroke_record` 加 `add_stroke`，`check` 是 `standards.line`，`revise` 是
`revise_mark`。全部价值在两点：把状态记住，以及**让「改完之后再查一次」变成一句话** —— 而后者正是 `failures()`
存在的原因：一次修改有没有真的解决它要解决的问题，不该靠人记得回头看。
"""
from __future__ import annotations

from . import core, standards
from .project import Mark, Project


class Session:
    """A project, and the loop over it. **One object, because the loop is the thing a caller forgets.**

    `stage` is the default pass a new mark joins; `layer` is not defaulted, because a layer is a fact about the
    drawing and a session that guessed one would put everything on the same sheet.
    """

    def __init__(self, width: int = 1400, height: int = 900, title: str = '',
                 figure=None, stage: str = 'line') -> None:
        self.project = Project(width=int(width), height=int(height), title=title)
        if figure is not None:
            self.project.set_figure(figure)
        self.stage = stage

    # ---- 画 -----------------------------------------------------------------------------------------------

    def stroke(self, points, brush: str, stage: str = '', layer: str = '', note: str = '',
               **record) -> Mark:
        """画一笔。`record` 里的一切原样交给 `stroke_record`，所以宽度剖面、alpha 剖面、边缘、湿笔都在那里。"""
        built = core.stroke_record(list(points), brush, **record)
        return self.project.add_stroke(built, stage=stage or self.stage, layer=layer, note=note)

    def fill(self, region, stage: str = '', layer: str = '', note: str = '', **appearance) -> Mark:
        """铺一块色。**图层在这里尤其重要**：`psd.layers_from_project` 按层分组，而一块色落在哪一层决定了它在
        导出的 PSD 里能不能被单独关掉。"""
        return self.project.add_fill(region, stage=stage or 'colour', layer=layer, note=note, **appearance)

    def erase(self, region, stage: str = '', layer: str = '', note: str = '') -> Mark:
        """擦一块。**擦除只在自己那一层上生效**，所以要擦的东西与画它的那一笔在同一层。"""
        return self.project.add_erase(region, stage=stage or 'colour', layer=layer, note=note)

    # ---- 查 -----------------------------------------------------------------------------------------------

    def check(self, mark_id: str = '') -> list:
        """一支笔的判据；不给 id 就查全部。**返回 `Finding` 列表，空列表不是通过 —— 它是「没有可查的东西」。**"""
        if mark_id:
            marks = [self.project.by_id(mark_id)]
        else:
            marks = self.project.live()
        findings = []
        for mark in marks:
            if mark.kind != 'stroke':
                continue
            findings.append(standards.line(mark.as_record(), stage=mark.stage))
        return findings

    def failures(self, mark_id: str = '') -> list:
        """被判不过的那些。**改完之后要再调一次** —— 否则「改过了」与「改对了」没有分别。"""
        return [finding for finding in self.check(mark_id) if finding.ok is False]

    # ---- 改 -----------------------------------------------------------------------------------------------

    def revise(self, mark_id: str, **changes) -> Mark:
        """改一笔。`appearance.` 与 `geometry.` 前缀与命令行上的 `--set` 一致，所以两边可以照抄。

        不带前缀的字段进 `geometry`，因为那是绝大多数。
        """
        appearance, geometry, others = {}, {}, {}
        for key, value in changes.items():
            if key.startswith('appearance.'):
                appearance[key[len('appearance.'):]] = value
            elif key.startswith('geometry.'):
                geometry[key[len('geometry.'):]] = value
            elif key in ('stage', 'note'):
                others[key] = value
            else:
                geometry[key] = value
        return self.project.revise_mark(mark_id, appearance=appearance or None,
                                        geometry=geometry or None, **others)

    def rewind(self, steps: int = 1) -> list:
        """退回若干步。**日志按逆序撤销**，所以一次 `rewind(1)` 撤掉的正是刚才那一次改动。"""
        return self.project.rewind(steps)

    # ---- 看与存 -------------------------------------------------------------------------------------------

    def marks(self, layer: str = '', stage: str = '') -> list:
        """活着的那些，按画序。`layer` 与 `stage` 都是过滤，不给就全给。"""
        return [mark for mark in self.project.live()
                if (not layer or mark.layer == layer) and (not stage or mark.stage == stage)]

    def render(self, scale: float = 1.0, sweep: bool = True):
        """把整份工程画成一层。**`sweep=True` 是默认值**，因为画面那条路一直用它，而 `False` 只留给邮票模型的
        对照。"""
        from . import raster

        return raster.render_marks([mark.to_dict() for mark in self.project.live()],
                                   self.project.width, self.project.height, scale, sweep=sweep)

    def save(self, path: str) -> str:
        from .project import save_project

        save_project(self.project, path)
        return path

    @classmethod
    def load(cls, path: str) -> 'Session':
        from .project import load_project

        project = load_project(path)
        session = cls(project.width, project.height, project.title, stage=project.stage_names()[0]
                      if project.stage_names() else 'line')
        session.project = project
        return session

    def log(self) -> list:
        """这份工程做过什么。**一个改过的工程没有日志就说不清它是怎么来的。**"""
        return list(self.project.log)
