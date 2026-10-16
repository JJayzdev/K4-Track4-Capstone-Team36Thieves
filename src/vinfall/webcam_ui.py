"""Streamlit controls and bounded refresh for the local webcam session."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import uuid

import streamlit as st

ACTIVE = {"STARTING", "RUNNING", "STOPPING"}
SESSION_KEY = "_vinfall_webcam"
STATE_NAMES = {"NORMAL": "Đang theo dõi", "CALIBRATING": "Chờ hiệu chuẩn",
               "NO_DATA": "Thiếu mốc tư thế", "SUSPECTED": "Nghi té ngã",
               "ALERT": "Cảnh báo nghi té ngã"}


def stop_webcam():
    """Release the camera when navigating to recorded-video modes."""
    session = st.session_state.get(SESSION_KEY)
    if session is None:
        return True
    return session.stop(timeout=2.0)


def _begin(root, config, camera_index, variant):
    old = st.session_state.get(SESSION_KEY)
    if old is not None and not old.stop(timeout=2.0):
        st.session_state["_webcam_ui_error"] = "Webcam đang được giải phóng. Chờ vài giây rồi bấm bắt đầu lại."
        return
    model = root / f"models/pose_landmarker_{variant}.task"
    if not model.is_file():
        st.session_state["_webcam_ui_error"] = f"Thiếu model {variant}. Chạy scripts/download_model.py --variant {variant}."
        return
    from .realtime import RealtimeSession
    directory = root / "runs/webcam" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    metadata = {"source": "local_webcam", "camera_index": camera_index,
                "model_variant": variant, "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                "config": asdict(config), "timestamp_basis": "monotonic_capture_elapsed_ms",
                "save_video": False, "start_delay_seconds": 5}
    (directory / "session_meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    session = RealtimeSession(model, config, directory, camera_index=camera_index,
                              max_width=640, idle_timeout_s=20.0, start_delay_s=5.0)
    st.session_state[SESSION_KEY] = session
    st.session_state["_webcam_ui_error"] = ""
    st.session_state["_webcam_notified"] = set()
    session.start()


def _placeholder(message="Webcam đang tắt", detail="Bấm Bắt đầu webcam khi bạn đã sẵn sàng."):
    st.markdown(f'''<div class="vf-webcam-empty"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="6" y="13" width="27" height="25" rx="5"/><path d="m33 21 10-6v22l-10-6M17 13l3-5h8l3 5"/><circle cx="19.5" cy="25.5" r="5"/></svg><strong>{message}</strong><span>{detail}</span></div>''', unsafe_allow_html=True)


def render_webcam(root, config):
    root = Path(root)
    st.markdown('''<style>
.vf-webcam-empty{min-height:350px;display:flex;flex-direction:column;gap:14px;align-items:center;justify-content:center;background:#132e41;border:1px solid #2f4b60;color:#8aafc1;border-radius:15px;text-align:center;padding:35px}
.vf-webcam-empty svg{width:62px;height:62px;color:#4b839c;margin-bottom:4px}.vf-webcam-empty strong{font-size:17px;color:#d6e8f0;font-weight:600}.vf-webcam-empty span{font-size:12px;max-width:340px;line-height:1.7;color:#8aaabd}
.vf-live-state{border:1px solid #d9e7e9;border-left:4px solid #13828b;border-radius:11px;background:#fff;padding:17px 18px;margin-bottom:14px}.vf-live-state small{display:block;font-size:10px;letter-spacing:.1em;color:#8197a6;margin-bottom:7px}.vf-live-state strong{font-size:18px;color:#225669;letter-spacing:-.025em}.vf-live-state.alert{border-color:#f1cdd3;border-left-color:#d14c60;background:#fff5f6}.vf-live-state.alert strong{color:#bd3b52}
</style><div class="vf-section-kicker">CAMERA TRÊN MÁY</div><h2 class="vf-section-title">Webcam realtime</h2><p class="vf-section-copy">Xem tư thế và cảnh báo ngay từ webcam của máy đang chạy VinFall.</p>''', unsafe_allow_html=True)
    session = st.session_state.get(SESSION_KEY)
    initial = session.snapshot() if session else None
    active = bool(initial and initial.status in ACTIVE)
    camera_column, model_column, note_column = st.columns([1, 1, 1.7])
    with camera_column:
        camera_index = st.selectbox("Camera trên máy", [0, 1, 2], disabled=active,
                                    format_func=lambda n: f"Camera {n}" + (" · mặc định" if n == 0 else ""),
                                    key="webcam_index")
    with model_column:
        variants = [v for v in ("full", "lite") if (root / f"models/pose_landmarker_{v}.task").is_file()]
        variant = st.selectbox("Mô hình pose", variants or ["full"], disabled=active,
                                format_func=lambda v: "Full · cân bằng" if v == "full" else "Lite · nhẹ hơn",
                                key="webcam_variant")
    with note_column:
        st.caption("Một người · Camera cố định · Thấy toàn thân và sàn. Sau khi model sẵn sàng, bạn có 5 giây để vào vị trí trước khi webcam mở.")
    start_column, stop_column, reset_column, _ = st.columns([1.2, 1, 1.35, 2])
    with start_column:
        if st.button("Bắt đầu webcam", type="primary", disabled=active, key="webcam_start", use_container_width=True):
            _begin(root, config, camera_index, variant)
            st.rerun()
    with stop_column:
        if st.button("Dừng webcam", disabled=not active, key="webcam_stop", use_container_width=True):
            stop_webcam()
            st.rerun()
    with reset_column:
        if st.button("Hiệu chuẩn lại", disabled=not initial or initial.status != "RUNNING", key="webcam_reset", use_container_width=True):
            _begin(root, config, camera_index, variant)
            st.rerun()
    if st.session_state.get("_webcam_ui_error"):
        st.error(st.session_state["_webcam_ui_error"])

    @st.fragment(run_every=.2 if active else None)
    def panel():
        current = st.session_state.get(SESSION_KEY)
        snapshot = current.snapshot() if current else None
        # Controls live outside the fragment: refresh them once startup finishes
        # (or cleanup changes phase), otherwise reset would remain disabled.
        if active and snapshot and initial and snapshot.status != initial.status:
            st.rerun()
        video_area, details = st.columns([2.2, 1], gap="large")
        with video_area:
            if snapshot and snapshot.status == "RUNNING" and snapshot.frame is not None:
                st.image(snapshot.frame, channels="BGR", output_format="JPEG", width="stretch")
            elif snapshot and snapshot.status == "STARTING":
                _placeholder("Đang chuẩn bị webcam…", "Đang khởi tạo model. Sau đó có 5 giây chuẩn bị vị trí; giữ đứng rõ toàn thân khi có hình.")
            elif snapshot and snapshot.status == "STOPPING":
                _placeholder("Đang dừng webcam…", "Đợi camera và model giải phóng trước khi bắt đầu phiên khác.")
            else:
                _placeholder()
        with details:
            detection = snapshot.detection if snapshot else None
            alert = bool(snapshot and snapshot.events)
            state = STATE_NAMES.get(detection.state, "Chờ dữ liệu") if detection else (
                "Đang khởi tạo" if snapshot and snapshot.status == "STARTING" else "Webcam đang tắt")
            if snapshot and snapshot.status not in ACTIVE:
                state = "Đã dừng webcam" if snapshot.status == "STOPPED" else "Không mở được webcam"
            st.markdown(f'<div class="vf-live-state {"alert" if alert else ""}"><small>TRẠNG THÁI PHIÊN</small><strong>{state}</strong></div>', unsafe_allow_html=True)
            one, two = st.columns(2)
            one.metric("Thời gian camera", f"{snapshot.elapsed_ms / 1000:.1f} s" if snapshot else "0.0 s")
            two.metric("Cảnh báo", len(snapshot.events) if snapshot else 0)
            three, four = st.columns(2)
            three.metric("FPS xử lý", f"{snapshot.fps:.1f}" if snapshot else "—")
            four.metric("Tuổi khung hình", f"{snapshot.frame_age_ms:.0f} ms" if snapshot and snapshot.status == "RUNNING" else "—")
            if snapshot and snapshot.error:
                st.error(snapshot.error)
                st.caption("Kiểm tra quyền Camera cho ứng dụng desktop trong Windows, đóng ứng dụng khác đang dùng camera hoặc thử chỉ số camera khác.")
            if snapshot and snapshot.status == "RUNNING" and detection:
                obs = detection.observation
                deadline = config.calibration_ms + config.calibration_grace_ms
                if not obs.calibrated:
                    if detection.timestamp_ms > deadline:
                        st.warning("Chưa đủ mốc đứng để hiệu chuẩn. Điều chỉnh góc camera, vào vị trí thấy toàn thân rồi bấm Hiệu chuẩn lại.")
                    else:
                        st.info("Đang lấy mốc đứng. Giữ rõ toàn thân trong 3 giây đầu có hình.")
                elif not obs.landmarks_valid:
                    st.warning("Đang thiếu mốc tư thế; không cộng thời gian xác nhận ngã.")
                if snapshot.fps < 6 and snapshot.frame_count > 10:
                    st.caption("FPS xử lý thấp. Có thể dừng và thử model Lite để giảm tải.")
        if snapshot and snapshot.events:
            st.error("Có cảnh báo nghi té ngã trong phiên webcam này. Kiểm tra trực tiếp tình huống.")
            notified = st.session_state.setdefault("_webcam_notified", set())
            for event in snapshot.events:
                if event["event_id"] not in notified:
                    st.toast(f"Nghi té ngã · {event['video_timestamp_ms'] / 1000:.2f} giây", icon="⚠️")
                    notified.add(event["event_id"])
            rows = [{"Thời gian từ khi có hình": f"{e['video_timestamp_ms'] / 1000:.3f} giây",
                     "Trạng thái": "CẢNH BÁO NGHI NGÃ",
                     "Lý do": "Hạ thấp nhanh, thân nghiêng và duy trì đủ thời gian"} for e in snapshot.events]
            st.dataframe(rows, hide_index=True, use_container_width=True)
        if snapshot and snapshot.csv_path and snapshot.csv_path.is_file():
            st.download_button("Tải CSV webcam", snapshot.csv_path.read_bytes(), "vinfall-webcam-su-kien.csv", "text/csv", on_click="ignore", key="webcam_csv")
        st.caption("Chỉ xử lý trên máy, không ghi video webcam. CSV chỉ ghi cảnh báo thật từ detector; thời điểm tính từ lúc camera có hình. Mỗi lần bắt đầu/hiệu chuẩn lại tạo phiên mới.")

    panel()
    st.markdown('<div class="vf-limits">Webcam dùng bộ phát hiện thử nghiệm một người. Kết quả chưa chứng minh độ tin cậy thực tế.</div>', unsafe_allow_html=True)
