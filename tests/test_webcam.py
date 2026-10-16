from types import SimpleNamespace

import cv2
from fastapi.testclient import TestClient
import numpy as np

from vinfall.engine import MonitorEngine
from vinfall.server import create_app
from test_tracking import classifier, person


def live_engine(tmp_path):
    engine = MonitorEngine(tmp_path)
    engine.status = 'ready'
    engine.classifier = classifier()
    engine.extractor = SimpleNamespace(infer=lambda frames: [[person()]])
    clock = [100.]
    engine.clock = lambda: clock[0]
    return engine, clock


def test_webcam_api_and_real_jpeg_decoding_with_session_ownership(tmp_path):
    engine, clock = live_engine(tmp_path)
    try:
        with TestClient(create_app(engine, start_engine=False)) as client:
            assert client.post('/api/webcam/start', headers={'Origin': 'https://external.invalid'}).status_code == 403
            token = client.post('/api/webcam/start').json()['session']
            assert client.post('/api/webcam/start').status_code == 409
            jpeg = cv2.imencode('.jpg', np.full((240, 320, 3), 90, np.uint8))[1].tobytes()
            result = client.post('/api/webcam/frame', content=jpeg, headers={'Content-Type': 'image/jpeg', 'X-Vinfall-Session': token})
            assert result.status_code == 200 and result.json()['people'][0]['track_id'] == 1
            state = client.get('/api/state').json()
            assert state['rooms'][-1]['cameras'][0]['visible_count'] == 1
            assert token not in str(state)
            assert client.get('/api/rooms/106/video/0').status_code == 404
            assert client.post('/api/webcam/frame', content=jpeg, headers={'Content-Type': 'image/jpeg', 'X-Vinfall-Session': 'wrong'}).status_code == 409
            assert client.post('/api/webcam/frame', content=b'not an image', headers={'Content-Type': 'image/jpeg', 'X-Vinfall-Session': token}).status_code == 400
            assert client.post('/api/webcam/frame', content=b'x'*1_000_001, headers={'Content-Type': 'image/jpeg', 'X-Vinfall-Session': token}).status_code == 413
            assert client.put('/api/tracking', json={'missing_seconds': 1}).status_code == 400
            assert client.put('/api/tracking', json={'exit_zones': [[.9, .1, .2, .5]]}).status_code == 400
            assert client.post('/api/webcam/stop', json={'session': 'wrong'}).status_code == 409
            assert client.post('/api/webcam/stop', json={'session': token}).status_code == 200
            assert not engine.room('106').cameras
    finally:
        engine.close()


def test_camera_transport_gap_and_disconnect_do_not_imply_a_fall(tmp_path):
    engine, clock = live_engine(tmp_path)
    frame = np.zeros((240, 320, 3), np.uint8)
    try:
        token = engine.start_webcam()
        for i in range(16):
            clock[0] = 100+i/10
            engine.process_webcam(token, frame)
        # A transport gap resets the people histories before normal frames resume.
        clock[0] = 104
        engine.extractor.infer = lambda frames: [[]]
        engine.process_webcam(token, frame)
        assert not engine.room('106').cameras[0].monitor.people
        engine.check_webcam_timeout(110)
        assert engine.webcam_session is None and engine.room('106').error
        assert engine.events.list() == []
    finally:
        engine.close()


def test_live_disappearance_saves_current_and_last_seen_evidence(tmp_path):
    engine, clock = live_engine(tmp_path)
    engine.configure_tracking({'missing_seconds': 2})
    frame = np.zeros((240, 320, 3), np.uint8)
    try:
        token = engine.start_webcam()
        for i in range(16):
            clock[0] = 100+i/10
            engine.process_webcam(token, frame)
        engine.extractor.infer = lambda frames: [[]]
        for i in range(16, 45):
            clock[0] = 100+i/10
            engine.process_webcam(token, frame+100)
        event = engine.events.list()[0]
        assert event['room_id'] == '106' and event['kind'] == 'occlusion'
        assert event['observations'][0]['track_id'] == 1
        engine.executor.submit(lambda: None).result(timeout=5)
        with TestClient(create_app(engine, start_engine=False)) as client:
            current = client.get(f"/api/alerts/{event['id']}/evidence/0")
            previous = client.get(f"/api/alerts/{event['id']}/evidence/0/person/1")
            assert current.status_code == previous.status_code == 200
            assert current.content != previous.content
            image = cv2.imdecode(np.frombuffer(previous.content, np.uint8), cv2.IMREAD_COLOR)
            x, y = (np.asarray(event['observations'][0]['last_box'][:2])*[320,240]).astype(int)
            b, g, r = (int(channel) for channel in image[y, x])
            assert g > r+20 and g > b+50  # Last seen image marks the missing person's box.
            assert 'occlusion' in client.get('/api/alerts/export').text
        assert engine.webcam_session == token
    finally:
        engine.close()


def test_settings_survive_restart_and_update_each_camera(tmp_path):
    engine, _ = live_engine(tmp_path)
    engine.configure_tracking({'missing_seconds': 15, 'exit_zones': [[.1, .1, .3, .6]]})
    engine.close()
    restored = MonitorEngine(tmp_path)
    try:
        assert restored.tracking_settings.missing_seconds == 15
        assert restored.tracking_settings.exit_zones == [[.1, .1, .3, .6]]
    finally:
        restored.close()


def test_multiple_missing_people_are_recorded_and_later_incidents_can_alert(tmp_path):
    engine, clock = live_engine(tmp_path)
    engine.configure_tracking({'missing_seconds': 2})
    engine.deliver_event = lambda *args: None
    frame = np.zeros((240, 320, 3), np.uint8)
    try:
        token = engine.start_webcam()
        engine.extractor.infer = lambda frames: [[person(.3), person(.75, color=4)]]
        for i in range(16):
            clock[0] = 100+i/10
            engine.process_webcam(token, frame)
        engine.extractor.infer = lambda frames: [[]]
        for i in range(16, 40):
            clock[0] = 100+i/10
            engine.process_webcam(token, frame)
        first = engine.events.list()[0]
        assert {o['track_id'] for o in first['observations']} == {1, 2}
        engine.events.acknowledge(first['id'])
        engine.extractor.infer = lambda frames: [[person(.3)]]
        for i in range(40, 60):
            clock[0] = 100+i/10
            engine.process_webcam(token, frame)
        engine.extractor.infer = lambda frames: [[]]
        for i in range(60, 85):
            clock[0] = 100+i/10
            engine.process_webcam(token, frame)
        assert len(engine.events.list()) == 2
        assert any(e['acknowledged_at'] for e in engine.events.list())
    finally:
        engine.close()
