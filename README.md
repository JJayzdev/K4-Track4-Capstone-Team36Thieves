# VinFall Alert

Prototype hackathon: phát hiện nghi té ngã bằng camera, hỗ trợ người trực tại Vinhomes.

## Hiện trạng

Repo khởi tạo gồm camera/video input và MediaPipe Pose Landmarker để vẽ khung xương một người. **Chưa có thuật toán phát hiện ngã, cảnh báo hoặc log sự kiện.** Không dùng prototype làm hệ thống bảo vệ an toàn.

## Chạy trên Windows PowerShell

Khuyến nghị Python 3.11 trong môi trường ảo riêng. Máy hiện có Python 3.9; nếu pip không tìm được bản MediaPipe phù hợp, dùng Python 3.11.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts/download_model.py
.\.venv\Scripts\python.exe -m vinfall --source 0
```

Thử camera khác bằng `--source 1`; replay bằng `--source data/demo.mp4`. Nhấn Q để thoát. Cần mạng khi cài dependency và tải model; inference chạy cục bộ. Đặt camera cố định, thấy toàn thân và sàn. Chỉ dùng thành viên tự đóng vai; mô phỏng chuyển động có kiểm soát trên đệm.

## Việc cần làm trong 120 phút

| Phút | Công việc |
| --- | --- |
| 0–15 | Cài môi trường, chạy pose baseline, chốt góc quay |
| 15–35 | Tính góc thân, tâm thân, lịch sử timestamp và hiệu chuẩn đứng |
| 35–60 | NORMAL → SUSPECTED → ALERT; xử lý thiếu mốc |
| 60–80 | Âm thanh, reset, log CSV |
| 80–105 | Thử tình huống, chỉnh rồi khóa ngưỡng |
| 105–120 | Đánh giá cuối, quay video dự phòng, chuẩn bị pitch |

## Hợp đồng dữ liệu giữa các phần

`timestamp_ms, angle_deg, normalized_drop, landmarks_valid, state`

- Góc tính trên tọa độ pixel, giữa trục vai–hông và phương đứng.
- Độ dịch chuyển chuẩn hóa theo chiều cao người lúc hiệu chuẩn đứng.
- Ngưỡng khởi đầu: nghiêng >60°, hạ tâm 20–30% chiều cao trong 0,7s, duy trì thấp/nghiêng 1–1,5s. Đây là giả thuyết cần chỉnh và đo.
- Thiếu mốc: UNKNOWN; không cộng thời gian xác nhận. Cảnh báo đã phát giữ đến khi xác nhận.
- Người nằm sẵn khi xuất hiện: chưa đủ bằng chứng về quá trình ngã.

## Đánh giá

Sau khi khóa ngưỡng: 4 lượt mô phỏng ngã, 6 lượt bình thường (đi, ngồi, cúi, squat, nằm chậm, đứng lên), 2 lượt che khuất/ra khỏi hình. Báo số phát hiện đúng, cảnh báo nhầm, độ trễ và ít nhất một ca lỗi. Tách lượt chỉnh ngưỡng khỏi lượt đánh giá.

## Phân công gợi ý

- Camera + pose.
- Hình học + state machine.
- Kịch bản + nhãn + đánh giá.
- Giao diện + log + tích hợp + pitch.

## Cấu trúc

- `src/vinfall/`: mã ứng dụng.
- `scripts/download_model.py`: tải model chính thức.
- `models/`: model cục bộ, không commit.
- `data/`: video đóng vai cục bộ, không commit.
- `logs/`: log cục bộ, không commit.

Tài liệu API: https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python
