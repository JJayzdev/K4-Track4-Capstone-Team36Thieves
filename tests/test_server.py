from fastapi.testclient import TestClient

from vinfall.engine import MonitorEngine
from vinfall.server import create_app


def test_api_contract_and_websocket_snapshot(tmp_path):
    engine = MonitorEngine(tmp_path)
    with TestClient(create_app(engine, start_engine=False)) as client:
        assert client.get('/').status_code == 200
        state = client.get('/api/state').json()
        assert len(state['rooms']) == 6 and state['rooms'][-1]['kind'] == 'live'
        assert client.get('/api/rooms/101/video/2').status_code == 404
        assert client.post('/api/control',json={'action':'play'}).status_code == 409
        assert client.put('/api/rooms/101/source',json={'sequence':'../../anything'}).status_code == 400
        assert client.post('/api/control',headers={'Origin':'https://other-site.example'},json={'action':'play'}).status_code == 403
        event,_ = engine.events.create('101','Phòng 101','fall-01','run-1',1.2,0)
        with client.websocket_connect('/ws') as socket:
            payload = socket.receive_json()
            assert payload['alerts'][0]['id'] == event
        assert client.post(f'/api/alerts/{event}/acknowledge').status_code == 200
        exported = client.get('/api/alerts/export')
        assert exported.status_code == 200 and 'Phòng 101' in exported.text
        assert client.get('/api/alerts/not-valid/evidence/0').status_code == 404
    engine.close()
