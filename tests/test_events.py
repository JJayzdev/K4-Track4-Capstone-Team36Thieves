from vinfall.events import EventStore


def test_two_cameras_merge_into_one_incident_and_ack_persists(tmp_path):
    path = tmp_path / "events.sqlite3"
    store = EventStore(path)
    event, created = store.create("101","Phòng 101","fall-01","run-1",1.5,0)
    assert created
    same, created = store.create("101","Phòng 101","fall-01","run-1",1.7,1)
    assert same == event and not created
    assert len(store.list()) == 1
    assert store.list()[0]["cameras"] == [0,1]
    assert store.acknowledge(event)
    assert not store.acknowledge("missing")
    store.close()
    restored = EventStore(path)
    assert restored.list()[0]["acknowledged_at"]
    restored.create("102","Phòng 102","fall-01","run-1",1.5,0)
    restored.create("101","Phòng 101","fall-01","run-2",1.5,0)
    assert len(restored.list()) == 3
    restored.close()
