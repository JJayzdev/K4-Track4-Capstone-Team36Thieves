import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
import numpy as np
import pytest

import vinfall.engine as engine_module
from vinfall.engine import MonitorEngine
from vinfall.events import EventStore
from vinfall.server import create_app


def fake_models(engine):
    data = {'points':np.ones((20,17,3),np.float32)*.9,
            'times':np.arange(20)/10, 'boxes':np.tile([.2,.1,.4,.8],(20,1)),
            'offsets':np.arange(21), 'appearances':np.zeros((20,24)), 'duration':np.array(2.0)}
    engine.extractor = SimpleNamespace(extract_people=lambda path:data)
    engine.classifier = SimpleNamespace(threshold=.6,predict_windows=lambda vectors:np.zeros(len(vectors)))


@pytest.mark.parametrize('camera_index',[0,1])
def test_single_video_loads_and_streams_by_actual_camera_index(tmp_path,monkeypatch,camera_index):
    data = tmp_path/'data'
    data.mkdir()
    video = data/f'adl-01-cam{camera_index}.mp4'
    video.write_bytes(b'test-video-content')
    monkeypatch.setattr(engine_module,'DATA',data)
    engine = MonitorEngine(tmp_path/'runtime')
    try:
        fake_models(engine)
        for room in engine.rooms:
            engine.load_room(room,room.source)
        engine.status = 'ready'
        state = engine.snapshot()
        assert sum(len(room['cameras']) for room in state['rooms']) == 1
        assert state['rooms'][0]['cameras'][0]['index'] == camera_index
        assert all(room['state']=='empty' and room['error'] is None for room in state['rooms'][1:] if room['kind']=='replay')
        assert state['rooms'][-1]['state']=='offline'
        assert state['duration'] == 2
        with TestClient(create_app(engine,start_engine=False)) as client:
            response = client.get(f'/api/rooms/101/video/{camera_index}',headers={'Range':'bytes=0-3'})
            assert response.status_code == 206 and response.content == b'test'
            assert client.get(f'/api/rooms/101/video/{1-camera_index}').status_code == 404
            payload = client.get('/api/sources').json()
            assert payload['sequences'] == ['adl-01']
            assert payload['camera_indices'] == {'adl-01':[camera_index]}
            assert client.post('/api/control',json={'action':'play'}).status_code == 200
        engine.elapsed = 2
        engine.advance()
        assert not engine.playing
        engine.control('play')
        assert engine.elapsed == 0 and engine.playing
    finally:
        engine.close()


def test_camera_membership_changes_between_one_and_two(tmp_path,monkeypatch):
    data = tmp_path/'data'
    data.mkdir()
    for name in ('single-cam1.mp4','paired-cam0.mp4','paired-cam1.mp4'):
        (data/name).touch()
    monkeypatch.setattr(engine_module,'DATA',data)
    engine = MonitorEngine(tmp_path/'runtime')
    try:
        fake_models(engine)
        room = engine.rooms[0]
        for source,expected in [('paired',[0,1]),('single',[1]),('paired',[0,1])]:
            engine.load_room(room,source)
            assert [camera.index for camera in room.cameras] == expected
            assert room.error is None and not room.loading
    finally:
        engine.close()


def test_single_camera_evidence_keeps_camera_one_id(tmp_path,monkeypatch):
    engine = MonitorEngine(tmp_path/'runtime')
    class Capture:
        def set(self,*args): pass
        def read(self): return True,np.zeros((24,64,3),np.uint8)
        def release(self): pass
    monkeypatch.setattr(engine_module.cv2,'VideoCapture',lambda path:Capture())
    engine.webhook = ''
    try:
        event,_ = engine.events.create('101','Phòng 101','single','run',1.0,1,[1])
        engine.deliver_event(event,'101','Phòng 101','single',1.0,[(1,tmp_path/'single-cam1.mp4')])
        assert engine.events.list()[0]['available_cameras'] == [1]
        with TestClient(create_app(engine,start_engine=False)) as client:
            assert client.get(f'/api/alerts/{event}/evidence/1').status_code == 200
            assert client.get(f'/api/alerts/{event}/evidence/0').status_code == 404
    finally:
        engine.close()


def test_migrating_old_alert_database_preserves_two_camera_evidence(tmp_path):
    path = tmp_path/'legacy.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('''CREATE TABLE alerts (
            id TEXT PRIMARY KEY, room_id TEXT, room_name TEXT, source TEXT,
            run_id TEXT, created_at TEXT, video_time REAL, cameras TEXT, acknowledged_at TEXT,
            UNIQUE(room_id,run_id))''')
        connection.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?)',
                           ('a'*32,'101','Phòng 101','fall-01','old-run','2026-10-16',1.0,'[0]','already-acknowledged'))
    store = EventStore(path)
    try:
        legacy = store.list()[0]
        assert legacy['available_cameras'] == [0,1]
        assert legacy['acknowledged_at'] == 'already-acknowledged'
        store.create('102','Phòng 102','adl-01','new-run',1.0,0,[0])
        assert len(store.list()) == 2
    finally:
        store.close()
