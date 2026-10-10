"""The body's structure as a constraint.

The point of these is not that the table is stored; it is that **the failures this project is aimed at are
detectable**. A third arm, a leg growing out of the neck and a limb that cannot bend are all topology errors, and
each one is constructed here and caught.
"""

import pytest

from lineweight import body


def test_the_reference_table_is_the_rigs_own_body():
    """34 joints, and the chains all present -- checked against the rig rather than against the file."""
    assert len(body.JOINT_PARENT) == 34
    for label, chain in body.CHAINS.items():
        for a, b in zip(chain, chain[1:]):
            assert body.JOINT_PARENT[b] == a, '%s is broken between %s and %s' % (label, a, b)


def test_the_reference_body_has_no_structural_errors():
    """The table is a valid body, so anything it rejects is not the table's fault."""
    assert body.structural_errors(dict(body.JOINT_PARENT)) == []


def test_exactly_two_arms_and_two_legs_by_kind():
    kinds = [body.kind(j) for j in body.JOINT_PARENT]
    arms = sorted(j for j in body.JOINT_PARENT if body.kind(j) == 'arm' and 'UpperArm' in j)
    legs = sorted(j for j in body.JOINT_PARENT if body.kind(j) == 'leg' and 'Thigh' in j)
    assert arms == ['Bip001 L UpperArm', 'Bip001 R UpperArm']
    assert legs == ['Bip001 L Thigh', 'Bip001 R Thigh']


def test_a_third_arm_is_caught():
    """**The failure this whole module exists for.** A generator that grows a third limb adds a child at the
    shoulder; the reference has exactly two clavicles and a neck there, so a fourth child is the error."""
    joints = dict(body.JOINT_PARENT)
    joints['Bip001 L UpperArm2'] = 'Bip001 Spine1'          # a third arm, hung off the same place
    problems = body.structural_errors(joints)
    assert any('extra limb' in p for p in problems), problems
    assert any('Bip001 Spine1 has 4 children' in p for p in problems), problems


def test_a_leg_off_the_neck_is_caught():
    joints = dict(body.JOINT_PARENT)
    joints['Bip001 L Thigh'] = 'Bip001 Neck'
    problems = body.structural_errors(joints)
    # **The chain is not broken by this** -- the calf still names the thigh as its parent, so the limb still bends.
    # What is wrong is the attachment, and the pelvis losing a child it should have. Asserting "chain is broken"
    # here would have been asserting the wrong fault, which is what the first version of this test did.
    assert any('attached to Bip001 Neck' in p for p in problems), problems
    # **Two faults, and the module caught only one of them until this test was written.** Moving the thigh away
    # leaves the pelvis a child short; the first arity check read `if got > allowed` and so was blind to it.
    assert any('Bip001 Pelvis has 2 children' in p for p in problems), problems
    assert any('a limb is missing' in p for p in problems), problems
    assert not any('leg.L chain is broken' in p for p in problems), problems


def test_a_limb_that_cannot_bend_is_caught():
    """A chain missing its middle is a limb with no joint in it."""
    joints = dict(body.JOINT_PARENT)
    del joints['Bip001 L Forearm']
    problems = body.structural_errors(joints)
    assert any('arm.L chain is missing Bip001 L Forearm' in p for p in problems), problems


def test_an_invented_joint_is_named_rather_than_accepted():
    joints = dict(body.JOINT_PARENT)
    joints['Bip001 Tail'] = 'Bip001 Pelvis'
    problems = body.structural_errors(joints)
    assert any('Bip001 Tail is not a joint of the rig' in p for p in problems), problems


def test_a_cycle_is_caught():
    joints = dict(body.JOINT_PARENT)
    joints['Bip001 Spine'] = 'Bip001 Head'
    problems = body.structural_errors(joints)
    assert any('is its own ancestor' in p for p in problems), problems


def test_an_extra_limb_is_caught_without_using_any_name():
    """**The name-free check, which is the one that works on something a generator produced.** Its joints may be
    called anything; the shape of the tree is still comparable, and the reference branches 3/3/3 at pelvis, chest and
    hand."""
    ref = body.arity_profile(list(body.JOINT_PARENT.items()))
    assert ref['branching'][:3] == [3, 3, 3, ] or ref['branching'][:3] == [3, 3, 3], ref['branching']
    three_arms = list(body.JOINT_PARENT.items()) + [('extra_limb', 'Bip001 Spine1')]
    assert body.arity_errors(three_arms), 'a fourth child at the chest went unnoticed'


def test_a_two_legged_body_is_rejected_by_shape():
    """A body with the legs missing is not a body, and the shape check says so without knowing the words."""
    without_legs = [(c, p) for c, p in body.JOINT_PARENT.items()
                    if not c.startswith('Bip001 L Thigh') and not c.startswith('Bip001 R Thigh')]
    assert body.arity_errors(without_legs)


def test_a_missing_leg_is_caught_by_arity_as_well_as_an_extra_arm():
    """**Both directions, because the first version of the check only had one.** A body short of a limb is as
    wrong as a body with a spare, and a check that reads `if got > allowed` is blind to half of it."""
    joints = dict(body.JOINT_PARENT)
    joints['Bip001 R Thigh'] = 'Bip001 Neck'          # the right leg, moved off the pelvis
    problems = body.structural_errors(joints)
    assert any('a limb is missing' in p for p in problems), problems
    # and the extra direction still works
    joints2 = dict(body.JOINT_PARENT)
    joints2['third'] = 'Bip001 Pelvis'
    assert any('an extra limb' in p for p in body.structural_errors(joints2))
