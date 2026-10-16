import numpy as np
from types import SimpleNamespace

from vinfall.engine import Camera, MonitorEngine
from vinfall.tracking import PeopleMonitor


def test_clock_pause_restart_and_two_camera_room_fusion(tmp_path):
    engine = MonitorEngine(tmp_path)
    engine.deliver_event = lambda *args: None
    engine.status = 'ready'
    room = engine.rooms[0]
    points = np.zeros((15,17,3),np.float32)
    points[:,:,2] = .9
    points[:,5,:2] = [.45,.25]
    points[:,6,:2] = [.55,.25]
    points[:,11,:2] = [.45,.5]
    points[:,12,:2] = [.55,.5]
    points[5:,5,:2] = [.65,.74]
    points[5:,6,:2] = [.75,.74]
    points[5:,11,:2] = [.45,.75]
    points[5:,12,:2] = [.55,.75]
    data = {'points':points,'times':np.arange(15)/10,'boxes':np.tile([.4,.1,.6,.8],(15,1)),
            'offsets':np.arange(16),'appearances':np.zeros((15,24))}
    classifier = SimpleNamespace(threshold=.6,predict_windows=lambda vectors:(vectors[:,-1,-2]>.5).astype(float))
    engine.classifier, engine.extractor = classifier, object()
    token = engine.start_webcam()
    live_camera = engine.room('106').cameras[0]
    room.cameras = [Camera(i,tmp_path/f'cam{i}.mp4',data,PeopleMonitor(classifier)) for i in (0,1)]
    room.duration = 1.5
    engine.control('play')
    engine.elapsed = 1.4
    engine.advance()
    events = engine.events.list()
    assert len(events) == 1 and events[0]['room_id'] == '101'
    assert events[0]['cameras'] == [0,1]
    engine.control('pause')
    assert not engine.playing
    engine.control('restart')
    assert engine.playing and engine.elapsed == 0
    assert engine.webcam_session == token and engine.room('106').cameras[0] is live_camera
    assert all(c.cursor == -1 and not c.monitor.people for c in room.cameras)
    engine.elapsed = 1.4
    engine.advance()
    assert len(engine.events.list()) == 2
    engine.close()
