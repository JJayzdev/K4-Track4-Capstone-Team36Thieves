"""VinFall: upload, analyze locally, then replay browser-compatible result files."""
from pathlib import Path
import hashlib
import json
import sys
import uuid
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st
from vinfall.config import Config
from vinfall.analysis import analyze_video
from vinfall.media import encode_browser_video
from vinfall.library import available_samples
from vinfall.dashboard import render_dashboard
from vinfall.theme import render_header, render_upload_guide
from vinfall.webcam_ui import render_webcam, stop_webcam

CONFIG_PATH = ROOT / "configs/hospital_calibration_v3.json"
CONFIG_BYTES = CONFIG_PATH.read_bytes()
CONFIG = Config(**json.loads(CONFIG_BYTES))

st.set_page_config(page_title="VinFall", page_icon="◉", layout="wide", initial_sidebar_state="collapsed")
render_header(realtime=st.session_state.get("vinfall_mode") == "Webcam realtime")

mode = st.radio("Chế độ demo", ["Theo dõi nhiều phòng", "Phân tích một video", "Webcam realtime"], horizontal=True, label_visibility="collapsed", key="vinfall_mode")
if mode == "Webcam realtime":
    render_webcam(ROOT, CONFIG)
    st.stop()
if not stop_webcam():
    st.warning("Đang giải phóng webcam sau khi chuyển chế độ…")
if mode == "Theo dõi nhiều phòng":
    render_dashboard(ROOT)
    st.stop()

st.markdown('<div class="vf-section-kicker">PHÂN TÍCH VIDEO</div><h2 class="vf-section-title">Xem lại từng tình huống</h2><p class="vf-section-copy">Chọn video, phân tích trên máy và đối chiếu cảnh báo cùng khung hình.</p>', unsafe_allow_html=True)
input_mode = st.radio("Nguồn video", ["Tải video lên", "Thư viện nhiều phòng"], horizontal=True)
uploaded = None
selected_sample = None
payload = None
selected_name = None

left, right = st.columns([2.1, 1], gap="large")
with left:
    if input_mode == "Tải video lên":
        uploaded = st.file_uploader("Chọn một video", type=["mp4", "mov", "avi", "mkv", "m4v"],
                                    help="Video tối đa 100 MB; một người, camera cố định, thấy toàn thân và sàn.")
        if uploaded:
            payload, selected_name = uploaded.getvalue(), uploaded.name
    else:
        samples = available_samples(ROOT)
        rooms = ["Tất cả bối cảnh"] + sorted({clip["room"] for clip in samples})
        room = st.selectbox("Bối cảnh phòng", rooms)
        filtered = [clip for clip in samples if room == "Tất cả bối cảnh" or clip["room"] == room]
        if filtered:
            labels = {"fall": "ngã mô phỏng", "normal": "hoạt động thường ngày", "unknown": "chưa gán nhãn"}
            sample_index = st.selectbox("Video mô phỏng", range(len(filtered)),
                                        format_func=lambda i: f"{filtered[i]['id']} · {filtered[i]['room']} · {labels.get(filtered[i]['label'], 'chưa gán nhãn')}")
            selected_sample = filtered[sample_index]
            payload = selected_sample["absolute_path"].read_bytes()
            selected_name = selected_sample["absolute_path"].name
            st.caption("Clip công khai dùng để thử nghiệm bối cảnh phòng; không phải dữ liệu bệnh viện đã kiểm chứng. Nhãn clip không được dùng để tạo cảnh báo.")
        else:
            st.info("Chưa có clip trong nhóm này. Có thể tải video của bạn lên.")
    analyze = st.button("Phân tích video", type="primary", disabled=not payload, use_container_width=False)
with right:
    render_upload_guide()
    with st.expander("Khung hình & ngưỡng thử"):
        suggested_crop = selected_sample.get("crop", "full") if selected_sample else "full"
        crop_label = st.selectbox("Vùng phân tích", ["Toàn bộ khung hình", "Nửa bên phải (preview URFD)"],
                                 index=1 if suggested_crop == "right-half" else 0, key="crop_" + (selected_sample["id"] if selected_sample else "upload"))
        variants = [variant for variant in ("full", "lite", "heavy") if (ROOT / f"models/pose_landmarker_{variant}.task").is_file()]
        variant = st.selectbox("Mô hình pose local", variants,
                               format_func=lambda value: {"lite":"Lite · nhanh", "full":"Full · cân bằng", "heavy":"Heavy · xử lý lâu hơn"}[value]) if variants else "lite"
        st.caption("Model có sẵn của Google, không train lại. Model lớn hơn chưa đồng nghĩa phát hiện ngã tốt hơn; xem báo cáo đo so sánh.")
        st.caption(f"Thấp: hạ tâm thân ≥{CONFIG.low_pose_drop_ratio:.0%} chiều cao đứng. Hạ nhanh ≥{CONFIG.rapid_drop_ratio:.0%} trong 0,7 s, thân nghiêng 2D/3D ≥60°; xác nhận 1,2 s. Đây là ngưỡng thử, chưa kiểm chứng.")
crop = "right-half" if crop_label.startswith("Nửa") else "full"

identity = hashlib.sha256(payload).hexdigest() + ":" + crop + ":" + variant + ":" + hashlib.sha256(CONFIG_BYTES).hexdigest() if payload else None
if st.session_state.get("input_identity") != identity:
    st.session_state.pop("analysis", None)
    st.session_state.pop("analysis_error", None)
    st.session_state["input_identity"] = identity

if not payload:
    st.info("Tải video lên để bắt đầu. Video và model được xử lý cục bộ, không gửi tới dịch vụ cloud.")

if analyze:
    st.session_state.pop("analysis", None)
    st.session_state.pop("analysis_error", None)
    directory = ROOT / "runs" / "web" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    source = directory / ("input" + Path(selected_name).suffix.lower())
    source.write_bytes(payload)
    progress = st.progress(0, text="Đang kiểm tra video và khởi tạo model…")
    try:
        started = time.perf_counter()
        config = CONFIG
        def update(processed, total):
            fraction = min(.85, processed / max(total, processed, 1) * .85) if total else 0
            label = f"Đang phân tích: {processed}/{total} frame" if total else f"Đang phân tích: {processed} frame"
            progress.progress(fraction, text=label)
        model_path = ROOT / f"models/pose_landmarker_{variant}.task"
        result = analyze_video(source, directory, model_path, config,
                               crop=crop, progress_callback=update)
        progress.progress(.88, text="Đang tạo video kết quả để phát trên trình duyệt…")
        browser_result = encode_browser_video(result.raw_video_path, directory / "result.mp4")
        progress.progress(.95, text="Đang chuẩn bị video đầu vào để xem lại…")
        browser_input = encode_browser_video(source, directory / "input_preview.mp4")
        st.session_state["analysis"] = {"result": result, "video": browser_result,
                                         "input": browser_input, "name": selected_name,
                                         "model": variant,
                                         "elapsed_seconds": time.perf_counter() - started}
        (directory / "web_result.json").write_text(json.dumps({
            "input_name": selected_name, "input_sha256": hashlib.sha256(payload).hexdigest(),
            "model_variant": variant, "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            "config_name": CONFIG_PATH.name, "config_sha256": hashlib.sha256(CONFIG_BYTES).hexdigest(),
            "frame_count": result.frame_count, "fps": result.fps, "events": result.events,
            "processing_seconds": st.session_state["analysis"]["elapsed_seconds"],
            "result_video": str(browser_result), "csv": str(result.csv_path)}, ensure_ascii=False, indent=2), encoding="utf-8")
        progress.progress(1.0, text="Hoàn tất. Có thể phát lại hoặc tải kết quả bên dưới.")
    except Exception as exc:
        error = str(exc)
        if "FPS" in error or "fps" in error:
            error = "FPS của video không hợp lệ. Hãy xuất lại clip với FPS cố định và metadata chính xác; ứng dụng không tự đoán FPS."
        elif "open video" in error.lower() or "decodable" in error.lower():
            error = "Không đọc được video. File có thể bị lỗi hoặc codec không được hỗ trợ. Hãy chọn một video hợp lệ khác."
        elif "model" in error.lower() and not (ROOT / f"models/pose_landmarker_{variant}.task").is_file():
            error = f"Thiếu model. Chạy python scripts/download_model.py --variant {variant} rồi thử lại."
        st.session_state["analysis_error"] = error
        progress.empty()

if st.session_state.get("analysis_error"):
    st.error("Không thể phân tích video: " + st.session_state["analysis_error"])

analysis = st.session_state.get("analysis")
if analysis:
    result = analysis["result"]
    st.divider()
    st.subheader("Kết quả phân tích")
    st.caption(f"{analysis['name']} · MediaPipe Pose {analysis['model'].title()}")
    a, b, c = st.columns(3)
    a.metric("Cảnh báo nghi ngã", len(result.events))
    b.metric("Thời lượng video", f"{result.duration_seconds:.2f} giây")
    c.metric("Thời gian xử lý", f"{analysis['elapsed_seconds']:.2f} giây")
    for warning in result.warnings:
        st.warning(warning)
    original, annotated = st.columns(2, gap="large")
    with original:
        st.markdown("**Video đầu vào**")
        st.video(str(analysis["input"]))
    with annotated:
        st.markdown("**Video kết quả**")
        st.video(str(analysis["video"]))
    st.subheader("Sự kiện nghi ngã")
    reason_map = {"rapid_drop_and_tilt_confirmed": "Hạ thấp nhanh, thân nghiêng và duy trì tư thế thấp đủ thời gian",
                  "rapid_drop_and_world_tilt_confirmed": "Hạ thấp nhanh, thân nghiêng 3D và duy trì tư thế thấp đủ thời gian"}
    rows = [{"Thời điểm trong video": f"{e['video_timestamp_ms']/1000:.3f} giây",
             "Trạng thái": "CẢNH BÁO NGHI NGÃ", "Lý do": reason_map.get(e["reason"], e["reason"])} for e in result.events]
    import pandas as pd
    st.dataframe(pd.DataFrame(rows, columns=["Thời điểm trong video", "Trạng thái", "Lý do"]), hide_index=True, use_container_width=True)
    if not rows:
        st.info("Không ghi nhận cảnh báo nghi ngã. Kết quả này không khẳng định video không có ngã; hãy kiểm tra chất lượng hiệu chuẩn và landmark.")
    d1, d2 = st.columns(2)
    with d1:
        st.download_button("Tải video kết quả", analysis["video"].read_bytes(), "vinfall-ket-qua.mp4", "video/mp4", on_click="ignore")
    with d2:
        st.download_button("Tải CSV sự kiện", result.csv_path.read_bytes(), "vinfall-su-kien.csv", "text/csv", on_click="ignore")
    st.caption("Có thể phát lại bằng thanh điều khiển video, bấm Phân tích video để chạy mới, hoặc chọn clip khác. File kết quả lưu trong runs/web trên máy này.")
elif payload and not st.session_state.get("analysis_error"):
    st.caption(f"Đã chọn: {selected_name} · {len(payload)/1024/1024:.2f} MB")
    st.markdown("**Video đầu vào**")
    st.caption("Bản xem tương thích trình duyệt sẽ được tạo sau khi phân tích. Không cần cài codec trong trình duyệt.")

st.markdown('<div class="vf-limits">Demo nghiên cứu · Kết quả trên video mô phỏng chưa chứng minh độ tin cậy thực tế.</div>', unsafe_allow_html=True)
