"""The project file: a drawing as an ordered set of individually addressable marks.

**This is the product.** An image is something a project can be rendered to; it is not what the software produces. The
reason is in `DESIGN-PROJECT.md`: every stroke and every colour application has to stay a separate, addressable entry,
because the moment two strokes are merged into one step or a patch of colour is stored as a flat block, the only thing
this software is for -- revising, adding and deleting a single mark -- becomes impossible.

`stroke_record()` was already the right atom for lines: one record per stroke, never merged. What was missing is

  * a **fill** mark, so a patch of colour is an entry that can be deleted rather than a `d` string nobody can point at;
  * a **stage** on every mark, so a mark knows which pass it belongs to;
  * a **state**, because drawing five times what survives is normal practice -- the analysed video drew 145,184 px of
    line and kept 29,110 px -- so an erased mark is superseded, not garbage;
  * **order**, because later marks cover earlier ones: the sequence *is* the picture.

A note on `stages`. The four below are a **preset, not a law**. They were derived from one artist's recorded process,
and the second video analysed contradicted three of their four acceptance rules; see the demotion note in
`DESIGN-PROJECT.md`. They are here because most drawings have some staging and it is convenient to name the common one,
not because a project must use them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# The common staging, as a starting point a project may replace. Order is meaningful: it is the order the passes run.
#
# **The invariants below are advisory and come from ONE recording.** They are kept because a worked example of the
# mechanism is worth more than an empty one, and because a project that agrees with them gets a real check for free.
# They are explicitly not a definition of a correct drawing: the second video analysed contradicted three of the four
# while plainly showing a competent artist at work -- its lines were neutral black rather than warm brown, it had no
# separate value pass at all, and its saturation FELL through the colour stage. Each spec carries the measurement it
# came from, so a reader can judge it rather than trust it. See the demotion note in `DESIGN-PROJECT.md`.
DEFAULT_STAGES = (
    {'role': 'line', 'note': 'the drawing itself, before anything is painted',
     'invariants': [
         {'name': 'the linework is warm, not neutral', 'measure': 'warmth', 'op': '>', 'value': 0.0,
          'note': 'video 1 measured R-B +10. Video 2 measured +0.3 (neutral black) and is equally legitimate -- '
                  'KEER2014 places both black and brown on the natural side of its scale.'},
         {'name': 'something was actually drawn', 'measure': 'coverage', 'op': '>', 'value': 0.01,
          'note': 'a line pass that covered nothing is the one failure worth catching mechanically.'},
     ]},
    {'role': 'value', 'note': 'light and dark, before any hue exists',
     'invariants': [
         {'name': 'the value pass is near-neutral', 'measure': 'saturation', 'op': '<', 'value': 24.0,
          'note': 'video 1 dipped to 11.5 here, its lowest of the whole recording. Video 2 had no such pass.'},
     ]},
    {'role': 'colour', 'note': 'hue and saturation applied over an established value structure',
     'invariants': [
         {'name': 'the value structure held', 'measure': 'luminance_drift', 'op': '<', 'value': 0.05,
          'note': 'the gate that separates colouring from repainting the values. Video 1: -4.85% over every frame. '
                  'Video 2: -6.12%, which is why the bound is loose rather than tight.'},
         {'name': 'colour actually arrived', 'measure': 'saturation_ratio', 'op': '>', 'value': 1.0,
          'note': 'video 1 rose x2.26. Video 2 FELL to x0.91 -- the counterexample that makes this advisory.'},
     ]},
    {'role': 'refine', 'note': 'local correction; the longest pass in every recording examined',
     'invariants': [
         {'name': 'refining does not move the values', 'measure': 'luminance_drift', 'op': '<', 'value': 0.08,
          'note': 'looser than the colour bound on purpose: refinement is where a drawing is allowed to settle.'},
     ]},
)

LIVE = 'live'
SUPERSEDED = 'superseded'

_ID = re.compile(r'^m(\d+)$')


def _next_index(marks: list['Mark']) -> int:
    """One past the highest id in use, so ids are never reused after a load."""
    top = 0
    for mark in marks:
        m = _ID.match(mark.id)
        if m:
            top = max(top, int(m.group(1)))
    return top + 1


@dataclass
class Mark:
    """One stroke or one fill. **The atom: nothing in a project is smaller than this.**

    `geometry` holds whatever redraws it and nothing about how it looks; `appearance` holds the how and nothing about
    the shape. Keeping those apart is what lets a mark be restyled without being redrawn, which is the same split the
    stylization course notes describe and the same split `stroke_record` already had.
    """
    id: str
    kind: str                       # 'stroke' | 'fill'
    stage: str
    seq: int                        # drawing order; later marks sit on top of earlier ones
    geometry: dict = field(default_factory=dict)
    appearance: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    state: str = LIVE

    def to_dict(self) -> dict:
        return {'id': self.id, 'kind': self.kind, 'stage': self.stage, 'seq': self.seq,
                'geometry': self.geometry, 'appearance': self.appearance,
                'provenance': self.provenance, 'state': self.state}

    @classmethod
    def from_dict(cls, d: dict) -> 'Mark':
        return cls(id=d['id'], kind=d['kind'], stage=d['stage'], seq=d['seq'],
                   geometry=d.get('geometry', {}), appearance=d.get('appearance', {}),
                   provenance=d.get('provenance', {}), state=d.get('state', LIVE))


@dataclass
class Project:
    """Canvas, the passes, and every mark in drawing order."""
    width: float = 800.0
    height: float = 600.0
    title: str = 'lineweight'
    stages: list[dict] = field(default_factory=lambda: [dict(s) for s in DEFAULT_STAGES])
    marks: list[Mark] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)

    # ---- adding ---------------------------------------------------------------------------------------------

    def stage_names(self) -> list[str]:
        return [s['role'] for s in self.stages]

    def _check_stage(self, stage: str) -> None:
        if stage not in self.stage_names():
            raise ValueError('no such stage: %r (have %s)' % (stage, ', '.join(self.stage_names())))

    def add_stroke(self, record: dict, stage: str = 'line', note: str = '', source: str = '') -> Mark:
        """A stroke_record becomes a mark. Geometry comes from the record; nothing is copied out of it."""
        self._check_stage(stage)
        mark = Mark(id='m%04d' % _next_index(self.marks), kind='stroke', stage=stage, seq=len(self.marks),
                    geometry={'centre': record['centre'], 'control': record.get('control', []),
                              'pressure': record['pressure'], 'brush': record['brush'],
                              'seed': record.get('seed', 0), 'resolution': record.get('resolution', 14)},
                    appearance={'colour': record.get('colour', '#1A1620')},
                    provenance={'source': source, 'note': note})
        self.marks.append(mark)
        return mark

    def add_fill(self, region, stage: str = 'colour', colour: str = '#808080', opacity: float = 1.0,
                 blend: str = 'normal', note: str = '', source: str = '') -> Mark:
        """A fill is a mark like any other, so it can be deleted by id.

        **This is the difference that matters.** `region_fill()` used to hand back bare `d` strings; a caller could
        paint them but could not say "remove the third one". A fill mark keeps the polygon it came from as well as the
        path data, so it can be re-styled, re-ordered or dropped without touching any other mark.
        """
        self._check_stage(stage)
        mark = Mark(id='m%04d' % _next_index(self.marks), kind='fill', stage=stage, seq=len(self.marks),
                    geometry={'points': [list(p) for p in region.points], 'd': region.d},
                    appearance={'fill': colour, 'opacity': opacity, 'blend': blend},
                    provenance={'source': source, 'note': note})
        self.marks.append(mark)
        return mark

    # ---- reading --------------------------------------------------------------------------------------------

    def by_id(self, mark_id: str) -> Mark:
        for mark in self.marks:
            if mark.id == mark_id:
                return mark
        raise KeyError(mark_id)

    def in_stage(self, stage: str, live_only: bool = True) -> list[Mark]:
        """Marks of one pass, **in drawing order**. This is what `--stage` renders."""
        return sorted((m for m in self.marks
                       if m.stage == stage and (m.state == LIVE or not live_only)),
                      key=lambda m: m.seq)

    def upto(self, stage: str, live_only: bool = True) -> list[Mark]:
        """Every mark from the first pass through `stage` inclusive -- the state the drawing was in at that point."""
        self._check_stage(stage)
        order = self.stage_names()[:self.stage_names().index(stage) + 1]
        return sorted((m for m in self.marks if m.stage in order and (m.state == LIVE or not live_only)),
                      key=lambda m: m.seq)

    def live(self) -> list[Mark]:
        return sorted((m for m in self.marks if m.state == LIVE), key=lambda m: m.seq)

    # ---- saving ---------------------------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {'version': 2,
                'canvas': {'width': self.width, 'height': self.height},
                'title': self.title,
                'stages': self.stages,
                'marks': [m.to_dict() for m in self.marks],
                'log': self.log}

    @classmethod
    def from_dict(cls, d: dict) -> 'Project':
        version = d.get('version')
        if version != 2:
            raise ValueError('not a version 2 project file (got version %r)' % (version,))
        canvas = d.get('canvas', {})
        return cls(width=canvas.get('width', 800.0), height=canvas.get('height', 600.0),
                   title=d.get('title', 'lineweight'),
                   stages=d.get('stages') or [dict(s) for s in DEFAULT_STAGES],
                   marks=[Mark.from_dict(m) for m in d.get('marks', [])],
                   log=d.get('log', []))


def save_project(project: Project, path: str) -> None:
    """Writes the project. Indented and newline-terminated, because it is meant to be read and diffed by a human."""
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(project.to_dict(), handle, ensure_ascii=False, indent=1)
        handle.write('\n')


def load_project(path: str) -> Project:
    with open(path, encoding='utf-8') as handle:
        return Project.from_dict(json.load(handle))
