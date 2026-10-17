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


def test_alert_history_filters_pagination_and_validation(tmp_path):
    engine = MonitorEngine(tmp_path)
    try:
        # More than the snapshot's 200-item limit must remain queryable.
        ids = []
        for index in range(205):
            event, _ = engine.events.create('101', 'Phòng 101', 'sample', str(index), index, 0)
            ids.append(event)
        lost, _ = engine.events.create('106', 'Webcam', 'live', 'session', 1, 0, kind='occlusion')
        engine.events.acknowledge(lost)
        with TestClient(create_app(engine, start_engine=False)) as client:
            default = client.get('/api/alerts').json()
            assert default['total'] == 206 and len(default['items']) == 50
            assert default['limit'] == 50 and default['offset'] == 0
            first = client.get('/api/alerts', params={'room_id': '101', 'limit': 200}).json()
            last = client.get('/api/alerts', params={'room_id': '101', 'limit': 200, 'offset': 200}).json()
            assert first['total'] == last['total'] == 205
            assert len(first['items']) == 200 and len(last['items']) == 5
            assert {e['id'] for e in first['items'] + last['items']} == set(ids)
            filtered = client.get('/api/alerts', params={
                'room_id': '106', 'kind': 'occlusion', 'acknowledged': 'true'}).json()
            assert filtered['total'] == 1 and filtered['items'][0]['id'] == lost
            assert filtered['items'][0]['cameras'] == [0]
            assert filtered['items'][0]['observations'][0]['kind'] == 'occlusion'
            assert client.get('/api/alerts?acknowledged=false').json()['total'] == 205
            for query in ('offset=999', 'room_id=missing', "room_id=' OR 1=1--", 'kind=fall&acknowledged=true'):
                assert client.get('/api/alerts?' + query).json()['items'] == []
            for query in ('limit=0', 'limit=201', 'offset=-1', 'kind=unknown', 'acknowledged=unknown', 'room_id='):
                assert client.get('/api/alerts?' + query).status_code == 422
    finally:
        engine.close()
