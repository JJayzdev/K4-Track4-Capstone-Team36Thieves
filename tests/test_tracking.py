from types import SimpleNamespace

import numpy as np
import pytest

from vinfall.tracking import PeopleMonitor, TrackingSettings


def person(x=.45, lying=False, y=.5, color=0):
    points = np.zeros((17, 3), np.float32)
    points[:, 2] = .9
    points[11, :2], points[12, :2] = [x-.04, y], [x+.04, y]
    points[5, :2], points[6, :2] = [x-.04+(.2 if lying else 0), y-(.01 if lying else .25)], [x+.04+(.2 if lying else 0), y-(.01 if lying else .25)]
    appearance = np.zeros(24, np.float32)
    appearance[[color, 8+color, 16+color]] = 1
    return {'points': points, 'box': np.array([x-.08, y-.4, x+.08, min(.98, y+.25)], np.float32),
            'appearance': appearance}


def classifier():
    return SimpleNamespace(threshold=.6, predict_windows=lambda sequences: (sequences[:, -1, -2] > .5).astype(float))


def test_two_people_have_independent_histories_when_order_and_sizes_change():
    monitor = PeopleMonitor(classifier())
    alerts = []
    for i in range(20):
        a = person(.3, i >= 6, .75 if i >= 6 else .5, color=0)
        b = person(.75, color=4)
        # The person standing still is larger than the falling person.
        b['box'][0] -= .06
        b['box'][2] += .06
        detections = [a, b] if i % 2 == 0 else [b, a]
        alerts += monitor.update(i/10, detections)
    people = monitor.snapshot()
    assert len(people) == 2 and {p['track_id'] for p in people} == {1, 2}
    assert [(a['kind'], a['track_id']) for a in alerts] == [('fall', 1)]
    assert next(p for p in people if p['track_id'] == 2)['state'] == 'observing'


def test_interior_disappearance_alerts_once_while_other_person_stays():
    monitor = PeopleMonitor(classifier(), TrackingSettings(missing_seconds=2))
    for i in range(16):
        assert not monitor.update(i/10, [person(.3), person(.75, color=3)])
    alerts = []
    for i in range(16, 55):
        alerts += monitor.update(i/10, [person(.75, color=3)])
    assert len(alerts) == 1 and alerts[0]['kind'] == 'occlusion' and alerts[0]['track_id'] == 1
    assert alerts[0]['last_seen'] == 1.5 and alerts[0]['missing_seconds'] >= 2
    assert len(monitor.people) == 2


@pytest.mark.parametrize('exit_kind', ['edge', 'door'])
def test_exiting_does_not_raise_occlusion_alert(exit_kind):
    settings = TrackingSettings(missing_seconds=2, exit_zones=[[.35, .65, .65, .9]] if exit_kind == 'door' else [])
    monitor = PeopleMonitor(classifier(), settings)
    for i in range(16):
        monitor.update(i/10, [person(.45 if exit_kind == 'door' else .45+i*.033)])
    assert not any(monitor.update(i/10, []) for i in range(16, 60))


def test_brief_false_detection_never_arms_disappearance_alarm():
    monitor = PeopleMonitor(classifier(), TrackingSettings(missing_seconds=2))
    monitor.update(0, [person()])
    assert not any(monitor.update(i/10, []) for i in range(1, 60))


def test_boxes_without_enough_pose_evidence_do_not_arm_disappearance_alarm():
    monitor = PeopleMonitor(classifier(), TrackingSettings(missing_seconds=2))
    weak = person()
    weak['points'][:, 2] = .1
    for i in range(25):
        assert not monitor.update(i/10, [weak])
    assert not any(monitor.update(i/10, []) for i in range(25, 60))


def test_reappearance_before_timeout_keeps_id_and_cancels_missing_timer():
    monitor = PeopleMonitor(classifier(), TrackingSettings(missing_seconds=2))
    for i in range(16):
        monitor.update(i/10, [person()])
    for i in range(16, 30):
        assert not monitor.update(i/10, [])
    assert not monitor.update(3, [person()])
    assert [p['track_id'] for p in monitor.snapshot()] == [1]
    assert not monitor.update(4.5, [])
    assert monitor.update(5.1, [])[0]['kind'] == 'occlusion'


def test_new_entrant_after_exit_receives_new_id():
    monitor = PeopleMonitor(classifier())
    for i in range(16):
        monitor.update(i/10, [person(.45+i*.033)])
    monitor.update(2.5, [])
    monitor.update(2.6, [person(.8)])
    assert [p['track_id'] for p in monitor.snapshot()] == [2]


def test_ids_are_local_to_each_camera():
    first, second = PeopleMonitor(classifier()), PeopleMonitor(classifier())
    first.update(0, [person(.3), person(.7)])
    second.update(0, [person(.7)])
    assert len(first.people) == 2 and len(second.people) == 1
