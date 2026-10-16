import numpy as np

from vinfall.detector import FallDetector


def pose(hip_y=.5, lying=False, valid=True):
    points = np.zeros((17, 3))
    points[:, 2] = .9 if valid else .1
    points[11, :2] = [.45, hip_y]
    points[12, :2] = [.55, hip_y]
    points[5, :2] = [.45 + (.22 if lying else 0), hip_y - (.01 if lying else .25)]
    points[6, :2] = [.55 + (.22 if lying else 0), hip_y - (.01 if lying else .25)]
    box = np.array([.4, hip_y - .4, .6, hip_y + .3])
    return points, box


def test_confirms_transition_and_only_emits_once():
    detector = FallDetector(threshold=.6, confirm_seconds=.4)
    for t in (0,.1,.2,.3):
        assert not detector.update(t,.1,*pose())
    emitted = [detector.update(t,.9,*pose(.75,lying=True)) for t in (.4,.5,.6,.7,.8,.9,1.0)]
    assert sum(emitted) == 1
    assert detector.state == "alert"


def test_person_already_lying_does_not_generate_a_fall():
    detector = FallDetector(.6,.4)
    assert not any(detector.update(i/10,.99,*pose(.75,lying=True)) for i in range(30))


def test_missing_landmarks_interrupt_confirmation_and_keep_latched_alert():
    detector = FallDetector(.6,.4)
    for t in (0,.1,.2):
        detector.update(t,.1,*pose())
    detector.update(.3,.9,*pose(.75,lying=True))
    detector.update(.4,.9,*pose(.75,lying=True))
    assert not detector.update(.5,.99,*pose(valid=False))
    assert detector.state == "unknown"
    assert not detector.update(1.0,.99,*pose(.75,lying=True))
    detector.reset()
    for i in range(4):
        detector.update(i/10,.1,*pose())
    for i in range(4,12):
        detector.update(i/10,.99,*pose(.75,lying=True))
    detector.update(1.3,0,*pose(valid=False))
    assert detector.state == "alert"


def test_brief_high_score_does_not_trigger():
    detector = FallDetector(.6,.4)
    for t in (0,.1,.2):
        detector.update(t,.1,*pose())
    assert not detector.update(.3,.9,*pose(.75,lying=True))
    assert not detector.update(.4,.1,*pose(.75,lying=True))
    assert detector.state == "observing"


def test_short_occlusion_pauses_confirmation_without_counting_unseen_time():
    detector = FallDetector(.6,.3)
    for t in (0,.1,.2):
        detector.update(t,.1,*pose())
    for t in (.3,.4):
        assert not detector.update(t,.99,*pose(.75,lying=True))
    assert not detector.update(.5,.99,*pose(valid=False))
    assert not detector.update(.6,.99,*pose(.75,lying=True))
    assert not detector.update(.7,.99,*pose(.75,lying=True))
    assert detector.update(.8,.99,*pose(.75,lying=True))


def test_bending_without_lowering_hip_does_not_alert():
    detector = FallDetector(.6,.3)
    for t in (0,.1,.2):
        detector.update(t,.1,*pose())
    assert not any(detector.update(i/10,.99,*pose(.5,lying=True)) for i in range(3,20))
