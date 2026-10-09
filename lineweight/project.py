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
# **A mark can be drawn without being accepted.** Drawing programs for tablets have a commit step for exactly this
# reason: a stroke sits provisionally until the artist confirms it, and starting the next stroke without confirming
# clears it. The point is not the saving -- it is that the artist gets a moment to decide that *this* stroke is the
# one, before the next one begins. Without it, strokes accumulate and each one matters less.
#
# The number this shows up as: a recorded painting process drew 145,184 px of line and kept 29,110 px. Drawing five
# times what survives is ordinary, and this gate is the mechanism that produces it. A `draft` is where that churn
# lives -- it is not part of the drawing, it does not render, and throwing it away is the expected outcome for most
# of it rather than an error.
DRAFT = 'draft'

_ID = re.compile(r'^m(\d+)$')


def _highest_id(project: 'Project') -> int:
    """The largest id index anywhere in the project -- among the marks, and among the ids the log has ever named."""
    top = project.counter
    for mark in project.marks:
        m = _ID.match(mark.id)
        if m:
            top = max(top, int(m.group(1)))
    for entry in project.log:
        for mark_id in entry.get('ids', []):
            m = _ID.match(mark_id)
            if m:
                top = max(top, int(m.group(1)))
    return top


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
    # **Ids are never reused, not even after a discard.** Ids used to be derived from the marks present, which meant a
    # draft that was thrown away released its id for the next attempt -- and the log then read `draft m0001`,
    # `discard m0001`, `draft m0001`, which says one stroke was drafted twice when it was two different strokes. The
    # log is the record of what happened; an id that means different things at different points in it is not a record.
    counter: int = 0

    # ---- adding ---------------------------------------------------------------------------------------------

    def stage_names(self) -> list[str]:
        return [s['role'] for s in self.stages]

    def _check_stage(self, stage: str) -> None:
        if stage not in self.stage_names():
            raise ValueError('no such stage: %r (have %s)' % (stage, ', '.join(self.stage_names())))

    def add_stroke(self, record: dict, stage: str = 'line', note: str = '', source: str = '',
                   commit: bool = True) -> Mark:
        """A stroke_record becomes a mark. Geometry comes from the record; nothing is copied out of it.

        **`commit=True` by default, and that default is the considered one.** Drawing programs put an auto-confirm on
        for the same reason: a caller that draws programmatically means the stroke, so making it draft first would
        only be a way to lose it. The interactive workflow -- draw a candidate, look at it, keep it or not -- passes
        `commit=False` and then `commit()` or `begin()`, and that is where the gate pays for itself.
        """
        self._check_stage(stage)
        self.counter = _highest_id(self) + 1
        mark = Mark(id='m%04d' % self.counter, kind='stroke', stage=stage, seq=len(self.marks),
                    geometry={'centre': record['centre'], 'control': record.get('control', []),
                              'pressure': record['pressure'], 'brush': record['brush'],
                              'seed': record.get('seed', 0), 'resolution': record.get('resolution', 14)},
                    appearance={'colour': record.get('colour', '#1A1620')},
                    provenance={'source': source, 'note': note},
                    state=LIVE if commit else DRAFT)
        self.marks.append(mark)
        if not commit:
            self._record('draft', ids=[mark.id])
        return mark

    def add_fill(self, region, stage: str = 'colour', colour: str = '#808080', opacity: float = 1.0,
                 blend: str = 'normal', note: str = '', source: str = '', commit: bool = True) -> Mark:
        """A fill is a mark like any other, so it can be deleted by id.

        **This is the difference that matters.** `region_fill()` used to hand back bare `d` strings; a caller could
        paint them but could not say "remove the third one". A fill mark keeps the polygon it came from as well as the
        path data, so it can be re-styled, re-ordered or dropped without touching any other mark.
        """
        self._check_stage(stage)
        self.counter = _highest_id(self) + 1
        mark = Mark(id='m%04d' % self.counter, kind='fill', stage=stage, seq=len(self.marks),
                    geometry={'points': [list(p) for p in region.points], 'd': region.d},
                    appearance={'fill': colour, 'opacity': opacity, 'blend': blend},
                    provenance={'source': source, 'note': note},
                    state=LIVE if commit else DRAFT)
        self.marks.append(mark)
        if not commit:
            self._record('draft', ids=[mark.id])
        return mark

    # ---- revising ---------------------------------------------------------------------------------------------
    #
    # **The hard rule, stated once here because every method below obeys it: an existing mark is never regenerated.**
    # A change names a mark id and alters that mark. Nothing else in the project moves -- no ids are reassigned, no
    # neighbours are rebuilt, no order is recomputed. That is the whole reason the project is made of marks rather
    # than of layers, and it is what makes "change the third petal" a cheap operation instead of a redraw.
    #
    # It is also the one property a caller cannot check for itself by looking at the result: a rebuild that happened
    # to produce the same picture would be indistinguishable from a local edit. So the tests assert it structurally --
    # every other mark's serialised bytes, before and after, must be identical.

    def _record(self, op: str, **fields) -> dict:
        """Appends one entry to the operation log and returns it.

        A plain append rather than a mutable history object: the log is read far more often than it is written, and
        the simplest thing that preserves the sequence is the least likely to lose an entry.
        """
        entry = dict({'op': op, 'at': len(self.log)}, **fields)
        self.log.append(entry)
        return entry

    def add_strokes(self, records: list[dict], stage: str = 'line', note: str = '',
                    source: str = '', commit: bool = True) -> list[Mark]:
        """Adds several strokes as one operation. Order within the batch is the order drawn.

        A batch is one attempt, so it is committed or drafted as a unit -- which is what makes `commit=False` usable
        for the interactive case: propose a group of strokes as a candidate, look at it, then keep or drop the lot.
        """
        return [self.add_stroke(r, stage=stage, note=note, source=source, commit=commit) for r in records]

    def add_fills(self, regions, stage: str = 'colour', colour: str = '#808080', opacity: float = 1.0,
                  blend: str = 'normal', note: str = '', source: str = '', commit: bool = True) -> list[Mark]:
        """Adds several fills as one operation -- the shape a bucket tool's result arrives in."""
        return [self.add_fill(r, stage=stage, colour=colour, opacity=opacity, blend=blend,
                              note=note, source=source, commit=commit) for r in regions]

    def revise_mark(self, mark_id: str, appearance: dict | None = None, geometry: dict | None = None,
                    stage: str | None = None, note: str | None = None) -> Mark:
        """Changes one mark, in place, and touches nothing else.

        **Identity is not revisable.** `id`, `kind` and `seq` are refused outright rather than ignored, because a
        change to any of them is not a revision -- renaming is a different operation, and turning a stroke into a fill
        or moving a mark in the drawing order would leave the id pointing at something the caller never asked for.
        Refusing loudly beats accepting quietly and leaving a mark whose identity no longer means what it did.

        A field that is not mentioned is left alone, so a caller can change a colour without restating the geometry:
        passing a whole replacement for a field means replacing that field, and omitting it means not touching it.
        """
        mark = self.by_id(mark_id)
        for structural in ('id', 'kind', 'seq'):
            if appearance and structural in appearance:
                raise ValueError('%r is not revisable: it is the mark\'s identity, not its appearance' % structural)
            if geometry and structural in geometry:
                raise ValueError('%r is not revisable: it is the mark\'s identity, not its geometry' % structural)
        if stage is not None:
            self._check_stage(stage)
        before = {'appearance': dict(mark.appearance), 'geometry': dict(mark.geometry), 'stage': mark.stage}
        if appearance:
            mark.appearance.update(appearance)
        if geometry:
            mark.geometry.update(geometry)
        if stage is not None:
            mark.stage = stage
        if note is not None:
            mark.provenance['note'] = note
        after = {'appearance': dict(mark.appearance), 'geometry': dict(mark.geometry), 'stage': mark.stage}
        changed = sorted(k for k in after if before[k] != after[k])
        # **The previous values are kept, not just the names of the fields that changed.** Without them the log
        # records that something happened but cannot put it back, and "go back to how it was two steps ago" -- which
        # is the sentence this software exists to answer -- would be unanswerable from the file.
        self._record('revise', ids=[mark_id], changed=changed,
                     before={k: before[k] for k in changed}, after={k: after[k] for k in changed})
        return mark

    def supersede(self, mark_id: str, reason: str = '') -> Mark:
        """Takes a mark out of the drawing **without removing it**.

        A superseded mark stops rendering and stops being returned by the ordered accessors, but it stays in the file
        with its geometry intact. The analysed recording drew 145,184 px of line and kept 29,110 -- drawing five times
        what survives is ordinary practice, so an erased mark is history rather than garbage, and `restore` is the
        reason to keep it.

        Idempotent: superseding twice is one entry in the log, not two.
        """
        mark = self.by_id(mark_id)
        if mark.state == SUPERSEDED:
            return mark
        mark.state = SUPERSEDED
        self._record('supersede', ids=[mark_id], reason=reason)
        return mark

    def restore(self, mark_id: str) -> Mark:
        """Puts a superseded mark back, at its original place in the drawing order.

        Its `seq` was never touched, so restoring is exact: the mark returns to where it was rather than to the end.
        """
        mark = self.by_id(mark_id)
        if mark.state == LIVE:
            return mark
        mark.state = LIVE
        self._record('restore', ids=[mark_id])
        return mark

    # ---- the commit gate --------------------------------------------------------------------------------------
    #
    # A drawing program for tablets does not put a stroke into the drawing the moment the pen lifts. The stroke sits
    # provisionally, and starting the next one without confirming clears it. That is a deliberate gate with two jobs,
    # and both of them are about the drawing rather than about the file:
    #
    #   1. **It gives the artist a moment to accept the stroke they just made.** "This one is good enough" is a
    #      decision, and a workflow with nowhere to put that decision makes it by default instead of on purpose.
    #   2. **It stops meaningless lines accumulating.** Without the gate every experimental stroke stays, and a
    #      drawing built that way silts up: the picture gets muddier the longer it is worked on, because discarding
    #      is the effortful choice and adding is the easy one. Here discarding is what happens by default and keeping
    #      is what costs an action, which is the right way round.
    #
    # The measured churn this produces: one recorded process drew 145,184 px of line and kept 29,110. Five attempts
    # per kept mark is not waste -- it is what looking and deciding costs.

    def drafts(self) -> list[Mark]:
        """Marks that have been drawn but not accepted. Not part of the drawing, and not rendered."""
        return sorted((m for m in self.marks if m.state == DRAFT), key=lambda m: m.seq)

    def begin(self) -> list[Mark]:
        """Starts a new attempt: **discards anything still uncommitted**. Returns what was dropped.

        This is the "the next stroke clears the last one" behaviour, made explicit. Called before drawing a new
        candidate stroke, it means an unaccepted mark never survives into the next attempt -- which is the whole
        point, because a mark that survives by default is a mark nobody decided to keep.
        """
        dropped = self.drafts()
        for mark in dropped:
            self.marks.remove(mark)
        if dropped:
            self._record('discard', ids=[m.id for m in dropped], reason='superseded by the next attempt')
        return dropped

    def commit(self, *mark_ids: str) -> list[Mark]:
        """Accepts marks into the drawing. With no ids, accepts everything currently drafted.

        **The act this exists for.** A committed mark renders, is returned by the ordered accessors, and can only be
        taken out again by `supersede`, which is a different and more deliberate thing.
        """
        targets = [self.by_id(i) for i in mark_ids] if mark_ids else self.drafts()
        accepted = []
        for mark in targets:
            if mark.state == DRAFT:
                mark.state = LIVE
                accepted.append(mark)
        if accepted:
            self._record('commit', ids=[m.id for m in accepted])
        return accepted

    def discard(self, *mark_ids: str) -> list[Mark]:
        """Throws uncommitted marks away. With no ids, throws away every draft.

        Removal rather than supersession, because a draft was never part of the drawing: there is nothing to restore
        it into, and keeping every rejected attempt in the file would make the churn the gate exists to prevent show
        up in the file instead. The log records that it happened, so it is still visible; only the marks are gone.
        """
        targets = [self.by_id(i) for i in mark_ids] if mark_ids else self.drafts()
        dropped = [m for m in targets if m.state == DRAFT]
        if not dropped and mark_ids:
            raise ValueError('discard expects drafts; %s is committed'
                             % ', '.join(i for i in mark_ids if self.by_id(i).state != DRAFT))
        for mark in dropped:
            self.marks.remove(mark)
        if dropped:
            self._record('discard', ids=[m.id for m in dropped])
        return dropped

    def remove_mark(self, mark_id: str) -> Mark:
        """Deletes a mark outright. The distinction from `supersede` is deliberate and the caller has to mean it.

        **This is the one operation whose effect is not recoverable by ordinary means**, which is why it is not the
        default path. The log keeps the whole mark so that `rewind` can put it back -- but a caller reading the file
        after the log has been trimmed has no way to, and that is the difference being pointed at.
        """
        mark = self.by_id(mark_id)
        self.marks.remove(mark)
        self._record('remove', ids=[mark_id], mark=mark.to_dict())
        return mark

    # ---- going back -----------------------------------------------------------------------------------------

    def rewind(self, to_step: int) -> list[dict]:
        """Undoes logged operations until the log is `to_step` entries long, and says what it undid.

        **The log is kept sufficient to reverse itself, and that is a requirement rather than a convenience.** The
        stated use of this software is describing a drawing and then correcting it, repeatedly, so "that change was
        wrong, go back" is not an edge case -- it is half of how the thing is used.

        Newest first, so a failure partway leaves the project in a state that is still one of its own past states.
        Returns the undone entries rather than a count, because the caller usually wants to say what it undid.

        `remove` is reversible only while its entry is still in the log: the entry carries the whole mark, so rewind
        can restore it exactly, id and position included.
        """
        if to_step < 0 or to_step > len(self.log):
            raise ValueError('cannot rewind to %d: the log has %d entries' % (to_step, len(self.log)))
        undone: list[dict] = []
        while len(self.log) > to_step:
            entry = self.log.pop()
            op = entry.get('op')
            if op == 'revise':
                mark = self.by_id(entry['ids'][0])
                for field, value in entry.get('before', {}).items():
                    if field == 'stage':
                        mark.stage = value
                    else:
                        getattr(mark, field).clear()
                        getattr(mark, field).update(value)
            elif op == 'supersede':
                self.by_id(entry['ids'][0]).state = LIVE
            elif op == 'restore':
                self.by_id(entry['ids'][0]).state = SUPERSEDED
            elif op == 'remove':
                mark = Mark.from_dict(entry['mark'])
                if mark.id in [m.id for m in self.marks]:
                    raise ValueError('cannot undo remove of %s: the id is in use again' % mark.id)
                self.marks.append(mark)
                # **Put it back in drawing order, not at the end of the list.** `seq` was never lost, but appending
                # would leave the file's mark order different from the order it had before the removal -- so undoing
                # everything would still not restore the file byte for byte, and "rewind is exact" would be a claim
                # the data did not support. The list is kept sorted by seq so that a round trip through the log is
                # indistinguishable from never having made the change.
                self.marks.sort(key=lambda m: m.seq)
            else:
                self.log.append(entry)          # an op this version does not know how to reverse
                raise ValueError('cannot rewind past an unknown operation: %r' % (op,))
            undone.append(entry)
        return undone

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
                'log': self.log,
                'counter': self.counter}

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
                   log=d.get('log', []),
                   counter=int(d.get('counter', 0)))


def save_project(project: Project, path: str) -> None:
    """Writes the project. Indented and newline-terminated, because it is meant to be read and diffed by a human."""
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(project.to_dict(), handle, ensure_ascii=False, indent=1)
        handle.write('\n')


def load_project(path: str) -> Project:
    with open(path, encoding='utf-8') as handle:
        return Project.from_dict(json.load(handle))
