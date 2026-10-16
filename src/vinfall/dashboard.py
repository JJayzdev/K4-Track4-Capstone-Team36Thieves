"""Local replay monitoring view. Alerts originate only from analyzed events."""
import base64
import json
from pathlib import Path


def dashboard_html(manifest):
    rooms = []
    for room in manifest["rooms"]:
        item = dict(room)
        item["video"] = "data:video/mp4;base64," + base64.b64encode(Path(room["video_path"]).read_bytes()).decode("ascii")
        rooms.append(item)
    payload = json.dumps(rooms, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    template = Path(__file__).with_name("templates") / "dashboard.html"
    return template.read_text(encoding="utf-8").replace("__ROOM_DATA__", payload)


def render_dashboard(root):
    import streamlit as st
    import streamlit.components.v1 as components
    root = Path(root)
    path = root / "runs/dashboard/current.json"
    if not path.is_file():
        st.info("Chưa có bộ kết quả nhiều phòng. Chạy scripts/prepare_dashboard.py để phân tích video bằng detector trước khi phát mô phỏng.")
        st.caption("Có thể chọn chế độ Phân tích một video để bắt đầu với clip của bạn.")
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    components.html(dashboard_html(manifest), height=920, scrolling=True)
    with st.expander("Tải báo cáo & video các phòng"):
        st.caption("Kết quả của lần phân tích đã chuẩn bị. Phát lại video không tạo thêm dòng CSV.")
        st.download_button("Tải CSV tổng hợp", Path(manifest["combined_csv"]).read_bytes(), "vinfall-cac-phong.csv", "text/csv", on_click="ignore")
        for room in manifest["rooms"]:
            a, b, c = st.columns([2, 1, 1])
            a.write(room["name"] + " · " + room["clip_id"])
            b.download_button("CSV sự kiện", Path(room["csv_path"]).read_bytes(), f"{room['clip_id']}-su-kien.csv", "text/csv", key="csv_" + room["id"], on_click="ignore")
            c.download_button("Video kết quả", Path(room["video_path"]).read_bytes(), f"{room['clip_id']}-ket-qua.mp4", "video/mp4", key="video_" + room["id"], on_click="ignore")
    with st.expander("Thông tin phiên mô phỏng"):
        st.caption(f"Pose {manifest['model_variant'].title()} · {manifest['config_name']} · {len(manifest['rooms'])} video ghi sẵn, một người mỗi video.")
        st.caption("Mỗi video đã được phân tích bằng model và trạng thái riêng. Dữ liệu công khai chưa thay thế kiểm chứng tại bệnh viện.")
