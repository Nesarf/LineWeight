"""Pass invariants: the mechanism, not the rule book.

`DESIGN-PROJECT.md` first listed four acceptance rules taken from one artist's recording. The second recording
contradicted three of them, so they were demoted to advisory. What these tests are about is therefore **not** whether
any particular bound is right -- it is whether the machinery behaves honestly:

  * a stage that declares nothing must be reported as claiming nothing, never as passing;
  * an invariant that cannot be measured must be reported as unmeasurable, never as passing;
  * a failing invariant must be a finding, never an exception -- a check that can kill the run is a check that gets
    removed;
  * and the advisory flag must be visible, because a demoted rule that looks authoritative is worse than no rule.
"""
from __future__ import annotations

import pytest

from lineweight import Project, stroke_record
from lineweight.invariants import Finding, MEASURES, check, check_project, format_findings, measure_layer
from lineweight.raster import Layer, fill_polygon, render_marks


def a_measured_layer(colour: tuple[int, int, int], coverage: float = 0.25) -> dict:
    """A canvas with a known patch of colour on it, measured through the real measuring code."""
    layer = Layer(80, 80)
    side = int(80 * coverage ** 0.5)
    fill_polygon(layer, [(10.0, 10.0), (10.0 + side, 10.0), (10.0 + side, 10.0 + side), (10.0, 10.0 + side)],
                 colour, 1.0)
    return measure_layer(layer)


def test_a_stage_that_declares_nothing_is_reported_as_claiming_nothing():
    """The failure mode this guards is silence: an empty finding list reads exactly like a pass, and a mechanism whose
    default is 'passed' stops being looked at within a week."""
    findings = check({'role': 'line'}, {'coverage': 0.2})
    assert len(findings) == 1
    assert findings[0].ok is None
    assert 'claims nothing' in findings[0].detail
    assert format_findings(findings).count('?') >= 1


def test_an_invariant_that_cannot_be_measured_is_not_a_pass():
    """A drift needs a previous stage to drift from. With none, the honest answer is 'unknown' -- defaulting to pass
    would mean the first pass ever checked always passes whatever the bound is."""
    stage = {'role': 'colour', 'invariants': [
        {'name': 'values held', 'measure': 'luminance_drift', 'op': '<', 'value': 0.05}]}
    findings = check(stage, {'luminance': 100.0}, previous=None)
    assert findings[0].ok is None
    assert 'not measurable' in findings[0].detail

    # and an unknown measure name is reported, not raised
    findings = check({'role': 'x', 'invariants': [{'name': 'n', 'measure': 'vibes', 'op': '<', 'value': 1}]},
                     {'coverage': 0.1})
    assert findings[0].ok is None and 'unknown measure' in findings[0].detail


def test_a_failing_invariant_is_a_finding_and_never_an_exception():
    """A check that can kill the run is a check that gets taken out. Every stage of a real drawing gets judged, however
    badly it does, and the caller decides what to do about it."""
    stage = {'role': 'colour', 'invariants': [
        {'name': 'values held', 'measure': 'luminance_drift', 'op': '<', 'value': 0.05}]}
    findings = check(stage, {'luminance': 150.0}, previous={'luminance': 100.0})
    assert findings[0].ok is False
    assert findings[0].measured == pytest.approx(0.5)
    # a malformed spec is a finding too, not a crash
    findings = check({'role': 'x', 'invariants': [{'name': 'n', 'measure': 'coverage', 'op': '~', 'value': 1}]},
                     {'coverage': 0.5})
    assert findings[0].ok is None and 'bad invariant spec' in findings[0].detail


def test_the_measured_values_are_the_ones_the_videos_produced():
    """The measuring code has to agree with the code that measured the recordings, or the bounds derived from those
    recordings mean nothing here. Two checks that do not need a video: a neutral patch has no warmth and no chroma, and
    a saturated patch has both."""
    grey = a_measured_layer((140, 140, 140))
    assert grey['saturation'] == pytest.approx(0.0, abs=0.5)
    assert grey['warmth'] == pytest.approx(0.0, abs=0.5)

    warm = a_measured_layer((180, 120, 130))
    assert warm['warmth'] > 20, 'a red-brown patch must measure warm, as video 1 lines did'
    assert warm['saturation'] > 20

    # coverage is the fraction of the canvas actually painted, and it is the patch size we asked for
    assert grey['coverage'] == pytest.approx(0.25, abs=0.02)
    assert a_measured_layer((140, 140, 140), coverage=0.5)['coverage'] == pytest.approx(0.5, abs=0.02)


def test_a_blank_canvas_has_no_measurements_rather_than_zeroes():
    """Nothing drawn means nothing to measure. Reporting luminance 0 would make every bound pass trivially."""
    blank = measure_layer(Layer(40, 40))
    assert blank['coverage'] == 0.0
    assert blank['drawn'] == 0
    assert blank['luminance'] is None and blank['saturation'] is None and blank['warmth'] is None
    for name in ('luminance', 'saturation', 'warmth'):
        assert MEASURES[name](blank, None) is None


def test_the_drift_a_colour_pass_causes_is_measured_against_the_pass_before_it():
    """This is the gate the whole idea rests on: colouring must not quietly repaint the values. Two canvases of the
    same lightness but different hue must drift by about nothing; the same hue made much darker must fail."""
    same_value = a_measured_layer((150, 150, 150))
    same_value_blue = a_measured_layer((130, 150, 170))     # same mean lightness, different hue
    drift = MEASURES['luminance_drift'](same_value_blue, same_value)
    assert drift < 0.05, 'a hue change at constant lightness is exactly what the gate must allow: %.4f' % drift
    assert MEASURES['saturation_ratio'](same_value_blue, same_value) > 1.0

    darker = a_measured_layer((60, 80, 100))
    assert MEASURES['luminance_drift'](darker, same_value) > 0.05, 'repainting the values must be caught'


def test_every_default_stage_carries_its_evidence_and_its_advisory_flag():
    """The rules were demoted because one recording contradicted them. Nothing in the defaults may read as a law: each
    spec names the measurement it came from, and every finding comes back marked advisory."""
    project = Project()
    for stage in project.stages:
        for spec in stage['invariants']:
            assert spec.get('note'), '%s/%s has no evidence attached' % (stage['role'], spec['name'])
            assert spec['measure'] in MEASURES, spec['measure']

    rendered = {'line': a_measured_layer((160, 130, 135)),
                'value': a_measured_layer((140, 140, 140)),
                'colour': a_measured_layer((120, 145, 165)),
                'refine': a_measured_layer((120, 145, 165))}
    findings = check_project(project, rendered)
    assert findings and all(f.advisory for f in findings)
    assert all(f.stage in {s['role'] for s in project.stages} for f in findings)
    # and none of them blew up
    assert not any('raised' in f.detail for f in findings)


def test_checking_a_project_skips_a_pass_that_was_never_rendered():
    """A pass with no rendering is reported as unrendered, not silently dropped and not judged on nothing."""
    project = Project()
    findings = check_project(project, {'line': a_measured_layer((160, 130, 135))})
    stages_reported = {f.stage for f in findings}
    assert stages_reported == {s['role'] for s in project.stages}
    assert any('no measurement supplied' in f.detail for f in findings)


def test_the_report_counts_what_it_found_so_silence_is_visible():
    findings = [Finding('line', 'a', True, 1.0, '< 2'), Finding('colour', 'b', False, 9.0, '< 5'),
                Finding('refine', 'c', None, None, '', 'not measurable here')]
    text = format_findings(findings)
    assert '3 invariant(s): 1 failed, 1 not measurable' in text
    assert 'FAIL' in text and '?' in text and 'ok' in text
