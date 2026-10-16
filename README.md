# VinFall

Demo phát hiện nghi té ngã trên video ghi sẵn và webcam, chạy tại **http://127.0.0.1:8501/**. Dashboard tự phát nhiều video phòng mô phỏng và cảnh báo theo thời điểm video. Có chế độ upload một video, phân tích, xem lại skeleton/số đo, tải video kết quả và CSV; chế độ Webcam realtime dùng camera của máy đang chạy VinFall.

Demo còn bỏ sót ngã và nhiều clip không đủ hiệu chuẩn. Video công khai không phải dữ liệu bệnh viện đã kiểm chứng. Kết quả này chưa chứng minh độ tin cậy thực tế.

## Chạy ngay trong workspace

```powershell
cd E:\VinAI\VinFall
.\.venv-demo\Scripts\python.exe run_web.py
```

Chỉ bind `127.0.0.1:8501`, không public/tunnel. Server được giữ chạy khi bàn giao. Model và phân tích chạy local. `.venv-demo` dùng Python 3.9.13 và một số package đã có trên máy; chưa nghiệm thu cài sạch trên máy mới.

Dashboard dùng kết quả đã phân tích trong `runs/dashboard/current.json`. Phân tích lại bốn phòng, tạo model/state/history riêng cho mỗi video:

```powershell
.\.venv-demo\Scripts\python.exe scripts/prepare_dashboard.py
```

Mặc định R01 (bàn ghế), R04 (phòng rộng), R03 (phòng làm việc), URFD-D02 (có giường). Đổi bằng `--clips R01,R02,R03,URFD-D02`. Đây là bối cảnh thay thế để mô phỏng phòng bệnh; không gán nhãn giả là camera bệnh viện. Mỗi video một người.

Dashboard tự phát tắt tiếng, có tạm dừng tất cả, phát lại từ đầu, bật/tắt lặp và điều khiển từng video. Cảnh báo đến từ detector thật, gắn phòng và thời điểm video, giữ đến khi phát lại; lặp không nhân bản cảnh báo/CSV. Phòng thiếu hiệu chuẩn hoặc mất landmark được ghi rõ. Tải video/CSV trong “Tải báo cáo & video các phòng”. Không gửi thông báo ra ngoài localhost.

Giao diện có tổng quan số phòng/video đang phát/cảnh báo, thẻ phòng và nhật ký bên cạnh. Bấm biểu tượng mở rộng để xem lớn một phòng, hoặc “Xem lại tình huống” trong cảnh báo để phát từ khoảng 2 giây trước thời điểm cảnh báo. “Tải báo cáo & video các phòng” chứa các file đầu ra; model/cấu hình nằm trong “Thông tin phiên mô phỏng”. Trạng thái đã cảnh báo được giữ nổi bật tới khi phát lại từ đầu.

Chế độ “Phân tích một video”: upload tối đa 100 MB hoặc chọn thư viện, bấm phân tích, chờ xử lý/mã hóa H.264, xem đầu vào/kết quả và bảng sự kiện. Chọn clip khác hoặc phân tích lại tạo phiên model/state/history mới.

## Thử webcam realtime

1. Mở localhost và chọn **Webcam realtime**.
2. Chọn Camera 0 (mặc định) và model Full; đặt camera cố định thấy toàn thân/sàn.
3. Bấm **Bắt đầu webcam**. Model khởi tạo trước; sau khi sẵn sàng có 5 giây chuẩn bị trước khi camera mở. Đứng rõ toàn thân trong 3 giây đầu có hình để hiệu chuẩn.
4. Xem skeleton/trạng thái, FPS xử lý và cảnh báo trên trang. Nếu thiếu mốc đứng, điều chỉnh vị trí và bấm **Hiệu chuẩn lại** để tạo phiên mới với 5 giây chuẩn bị.
5. Bấm **Dừng webcam** khi xong. Có thể tải CSV của phiên; các phiên trước nằm riêng trong `runs/webcam/`.

Webcam dùng OpenCV trên **máy chạy server**, phù hợp localhost trên cùng laptop. Nó không dùng camera của thiết bị truy cập từ xa. Camera chỉ mở sau nút bắt đầu; chuyển sang chế độ video sẽ dừng camera. Phiên tự dừng sau khoảng 20 giây không có heartbeat giao diện (ví dụ đóng tab). Không ghi video/ảnh webcam ra đĩa; chỉ ghi CSV sự kiện và metadata. Mỗi lần bắt đầu/hiệu chuẩn lại tạo model, baseline và trạng thái mới.

Webcam dùng thời gian monotonic tại lúc đọc khung hình, tính từ khung đầu, không dùng FPS metadata hoặc tốc độ inference. Capture liên tục chỉ giữ khung mới nhất; bộ phát hiện xử lý độc lập, khung xem cập nhật khoảng 5 lần/giây. `video_timestamp_ms` trong CSV webcam là thời gian từ khi camera có hình. Clip ghi sẵn vẫn dùng frame-index/FPS như trước.

Nếu không mở được camera: kiểm tra quyền Camera cho ứng dụng desktop trong Windows, đóng ứng dụng khác đang dùng camera và thử chỉ số camera khác. Có thể chọn Lite để giảm tải. Tính năng hỗ trợ một người; chất lượng phát hiện ngã qua webcam chưa được kiểm chứng thực tế.

Kiểm tra phần cứng có chủ đích (mở camera vài giây, không lưu ảnh/video): `python scripts/verify_webcam.py`. Trên máy hiện tại đã đọc được 640×480, khoảng 25,8 FPS xử lý với Full qua script. Giao diện đã lên hình, chạy lại khi hiệu chuẩn, tải CSV và dừng khi chuyển chế độ; FPS xử lý quan sát khoảng 6–18 khi chạy giao diện (khung xem cập nhật khoảng 5 lần/giây). Đây là kiểm tra luồng camera/model, không phải nghiệm thu phát hiện ngã thật. Bằng chứng: `logs/webcam/hardware.json`, `browser.json` và `webcam-ui.jpg` (ảnh giao diện khi camera đã tắt).

## Cài trên máy mới

Python 3.9–3.11, CPU. Hướng dẫn này chưa được nghiệm thu cài sạch trong lượt này:

```powershell
python -m venv .venv-clean
.\.venv-clean\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-clean\Scripts\python.exe scripts/download_model.py --variant full
.\.venv-clean\Scripts\python.exe scripts/download_samples.py
.\.venv-clean\Scripts\python.exe scripts/download_room_samples.py
.\.venv-clean\Scripts\python.exe scripts/prepare_dashboard.py
.\.venv-clean\Scripts\python.exe run_web.py
```

Tải model/dữ liệu cần Internet; phân tích/phát lại không dùng cloud. Model/video không đưa vào Git. Nguồn và quyền sử dụng xem [DATA_SOURCES.md](DATA_SOURCES.md). Mirror Le2i chưa xác minh được giấy phép gốc: không xem video là tài sản được phép tái phân phối.

## Model, logic và nguyên nhân bỏ sót

MediaPipe Pose Landmarker có sẵn của Google, không train lại. So sánh Lite/Full/Heavy trên cùng clip phát triển; chọn Full cho demo, Heavy không bảo đảm tốt hơn. Góc thân 2D tính sau khi chuyển landmark sang pixel; thêm góc thân 3D từ world landmarks khi có. Góc 3D là ước lượng của model, không phải phép đo độ sâu đã hiệu chuẩn.

Web hiện dùng `configs/hospital_calibration_v3.json`: nghiêng ≥60°; hạ nhanh ≥15% chiều cao đứng trong 0,7 s; “thấp” là hạ tâm thân ≥20%; hai dấu hiệu trong cửa sổ 1 s; xác nhận thấp/nghiêng 1,2 s. Bản v2 đã khóa giữ tại `configs/hospital_locked.json`; ngưỡng ban đầu 25%/25% giữ trong `configs/locked.json`. Hạ ngưỡng có thể tăng báo nhầm; đây vẫn là ngưỡng thử.

Thời gian = `frame_index * 1000 / FPS`, không phụ thuộc tốc độ máy. FPS metadata lỗi bị từ chối. Cần ít nhất 15 mẫu đứng đủ landmark: chốt từ giây 2 nếu đã đủ; nếu chưa đủ thì tiếp tục thu tới giây 3 và chốt ngay khi đủ. Hết giây 3 không lấy thêm mẫu để tránh dùng tư thế sau ngã làm baseline. Bản sửa này giúp R03 hiệu chuẩn ở 2,52 s và báo ngã ở 4,76 s. Thiếu landmark không cộng thời gian xác nhận; mất quá 0,5 s hủy nghi ngờ đang chờ. ALERT giữ trong lần phân tích, CSV chỉ ghi khi chuyển vào cảnh báo.

Ngã có thể bị bỏ sót vì thiếu đoạn đứng đầu, che khuất/ra khỏi khung, góc camera làm góc 2D nhỏ, mức hạ thấp chưa đủ hoặc mất mốc trước xác nhận. R01 từ bỏ sót với ngưỡng cũ đã có một cảnh báo tại 3,80 s với cấu hình mới. R01 là clip phát triển dùng chỉnh ngưỡng, chưa chứng minh tổng quát hóa. Các clip đánh giá riêng còn thất bại; xem [WEB_ACCEPTANCE.md](WEB_ACCEPTANCE.md).

## Kiểm tra và bằng chứng

```powershell
$env:PYTHONPATH='src'
.\.venv-demo\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-demo\Scripts\python.exe scripts/audit_dashboard.py
.\.venv-demo\Scripts\python.exe scripts/compare_models.py --manifest data/hospital_manifest.json --variants full --split eval --config configs/hospital_calibration_v3.json --output-dir logs/calibration_v3/eval_regression
```

81 kiểm thử đã chạy: cửa sổ hiệu chuẩn 2–3 giây, deadline/reset, thời gian, landmark, chuyển đổi pixel/3D, FPS, CSV, phiên độc lập, H.264 giữ thứ tự frame và vòng đời webcam. Mười test realtime kiểm tra timestamp capture, xác nhận cảnh báo, CSV không lặp, reset, lỗi camera/model, phiên bận, dừng trong lúc khởi tạo và hết heartbeat. Test pose giả lập phân biệt với chạy video thật. Checklist trong [WEB_ACCEPTANCE.md](WEB_ACCEPTANCE.md), báo cáo CLI cũ trong [ACCEPTANCE.md](ACCEPTANCE.md), ma trận bệnh viện trong [HOSPITAL_TEST_MATRIX.md](HOSPITAL_TEST_MATRIX.md).

CLI cũ: `python main.py --source <video> --headless --config configs/hospital_locked.json`. Web không tự đoán/override FPS. Đầu ra lưu trong `runs/web/` và `runs/dashboard/`; lưu bằng chứng trước khi dọn thư mục.
