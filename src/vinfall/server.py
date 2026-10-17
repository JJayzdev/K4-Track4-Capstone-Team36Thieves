import asyncio
from contextlib import asynccontextmanager
import csv
import io
import json
from typing import Literal

import cv2
import numpy as np

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .config import MODELS, ROOT
from .engine import MonitorEngine


class Control(BaseModel):
    action: str
    speed: float | None = None
    loop: bool | None = None


class Source(BaseModel):
    sequence: str


class WebcamSession(BaseModel):
    session: str


class TrackingConfig(BaseModel):
    missing_seconds: float = 8
    minimum_seen: float = 1
    exit_margin: float = .08
    exit_zones: list[list[float]] = []


def create_app(engine=None, start_engine=True):
    monitor = engine or MonitorEngine()

    @asynccontextmanager
    async def lifespan(app):
        if start_engine:
            monitor.start()
        yield
        if start_engine:
            monitor.close()

    app = FastAPI(title="VinFall · Giám sát té ngã", lifespan=lifespan)
    app.state.monitor = monitor
    static = ROOT / "src" / "vinfall" / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "DELETE"} and origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return Response("Origin not allowed", status_code=403)
        return await call_next(request)

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/api/state")
    def state():
        return monitor.snapshot()

    @app.get("/api/health")
    def health():
        return {"status": monitor.status, "message": monitor.message, "rooms": len(monitor.rooms),
                "cameras": sum(len(r.cameras) for r in monitor.rooms)}

    @app.get("/api/sources")
    def sources():
        return {"sequences": monitor.sources(), "dataset": "UR Fall Detection Dataset",
                "camera_indices": {source: [index for index, _ in monitor.source_cameras(source)]
                                   for source in monitor.sources()},
                "source_url": "https://fenix.ur.edu.pl/~mkepski/ds/uf.html"}

    @app.get("/api/training-report")
    def training_report():
        path = MODELS / "training_report.json"
        if not path.exists():
            raise HTTPException(404, "Chưa có báo cáo huấn luyện")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.post("/api/control")
    def control(body: Control):
        try:
            monitor.control(body.action, body.speed, body.loop)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True}

    @app.put("/api/rooms/{room_id}/source")
    def change_source(room_id: str, body: Source):
        try:
            monitor.change_source(room_id, body.sequence)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @app.put('/api/tracking')
    def tracking(body: TrackingConfig):
        try:
            monitor.configure_tracking(body.model_dump())
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {'ok': True}

    @app.post('/api/webcam/start')
    def start_webcam():
        try:
            return {'session': monitor.start_webcam(), 'room_id': '106'}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/webcam/stop')
    def stop_webcam(body: WebcamSession):
        try:
            monitor.stop_webcam(body.session)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'ok': True}

    @app.post('/api/webcam/frame')
    async def webcam_frame(request: Request, session: str = Header(alias='X-Vinfall-Session')):
        if request.headers.get('content-type', '').split(';')[0] != 'image/jpeg':
            raise HTTPException(415, 'Khung hình phải là JPEG')
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                raise HTTPException(413, 'Khung hình tối đa 1 MB')
        frame = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or min(frame.shape[:2]) < 16:
            raise HTTPException(400, 'Không đọc được ảnh webcam')
        if max(frame.shape[:2]) > 960:
            scale = 960 / max(frame.shape[:2])
            frame = cv2.resize(frame, None, fx=scale, fy=scale)
        try:
            return await run_in_threadpool(monitor.process_webcam, session, frame)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/rooms/{room_id}/video/{camera}")
    def video(room_id: str, camera: int):
        room = monitor.room(room_id)
        stream = next((item for item in room.cameras if item.index == camera), None) if room else None
        if stream is None or stream.path is None:
            raise HTTPException(404, "Camera chưa sẵn sàng")
        return FileResponse(stream.path, media_type="video/mp4")

    @app.get("/api/alerts")
    def alerts(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               room_id: str | None = Query(None, min_length=1, max_length=64),
               kind: Literal['fall', 'occlusion'] | None = None,
               acknowledged: bool | None = None):
        return monitor.events.query(limit=limit, offset=offset, room_id=room_id,
                                    kind=kind, acknowledged=acknowledged)

    @app.get("/api/alerts/export")
    def export():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "room", "source", "created_at_utc", "video_time_seconds", "cameras", "acknowledged_at_utc", 'kind', 'observations'])
        for event in monitor.events.list(limit=100000):
            writer.writerow([event["id"], event["room_name"], event["source"], event["created_at"],
                             event["video_time"], ";".join(str(c) for c in event["cameras"]), event["acknowledged_at"],
                             event['kind'], json.dumps(event['observations'], ensure_ascii=False)])
        return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=vinfall-alerts.csv"})

    @app.post("/api/alerts/{event_id}/acknowledge")
    def acknowledge(event_id: str):
        if not monitor.events.acknowledge(event_id):
            raise HTTPException(404, "Không tìm thấy cảnh báo")
        return {"ok": True}

    @app.get("/api/alerts/{event_id}/evidence/{camera}")
    def evidence(event_id: str, camera: int):
        if len(event_id) != 32 or any(c not in "0123456789abcdef" for c in event_id) or camera not in (0, 1):
            raise HTTPException(404)
        path = monitor.runtime / "evidence" / f"{event_id}-cam{camera}.jpg"
        if not path.exists():
            raise HTTPException(404, "Ảnh đang được lưu hoặc không có khung hình hợp lệ")
        return FileResponse(path, media_type="image/jpeg")

    @app.get('/api/alerts/{event_id}/evidence/{camera}/person/{track_id}')
    def last_seen_evidence(event_id: str, camera: int, track_id: int):
        if len(event_id) != 32 or any(c not in '0123456789abcdef' for c in event_id) or camera not in (0, 1) or track_id < 1:
            raise HTTPException(404)
        path = monitor.runtime / 'evidence' / f'{event_id}-cam{camera}-person{track_id}-last.jpg'
        if not path.exists():
            raise HTTPException(404, 'Chưa có ảnh cuối cùng của người này')
        return FileResponse(path, media_type='image/jpeg')

    @app.websocket("/ws")
    async def websocket(socket: WebSocket):
        origin = socket.headers.get("origin")
        if origin and origin.split("://", 1)[-1].rstrip("/") != socket.headers.get("host"):
            await socket.close(code=1008)
            return
        await socket.accept()
        try:
            while True:
                await socket.send_json(monitor.snapshot())
                await asyncio.sleep(.15)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    return app
