# VinFall Alert — Kế hoạch demo trong 120 phút

> Cập nhật phạm vi theo yêu cầu trực tiếp của người dùng: web localhost bằng
> Streamlit, upload/phân tích/phát video kết quả, sau đó dashboard nhiều video
> replay tự phát mô phỏng phòng bệnh. Cảnh báo chỉ trên dashboard localhost.
> Yêu cầu tiếp theo của người dùng đã bổ sung webcam realtime để thử trên cùng
> máy localhost: một webcam, một người, cảnh báo trên giao diện. Không mở rộng
> sang nhiều người trong một khung hình hoặc cloud.
> Phần “ngoài phạm vi dashboard” dưới đây là kế hoạch CLI ban đầu, đã được yêu
> cầu mới thay thế. Checklist thực tế mới nhất: WEB_ACCEPTANCE.md.

## Mục tiêu và phạm vi

- Nhân sự: 1 người.
- Đầu vào: video ghi sẵn, một người, camera cố định, thấy toàn thân và sàn.
- Luồng demo: video → landmark tư thế → đặc trưng → nghi ngã → cảnh báo → CSV.
- Công nghệ: Python, OpenCV, MediaPipe Pose Landmarker, CSV; dùng model có sẵn, không train.
- Video có khoảng 2–3 giây đứng đầu clip để hiệu chuẩn.
- Ngoài phạm vi: webcam, nhiều người, nhiều camera, dashboard, triển khai vận hành.
- Kết quả chỉ chứng minh demo trên video mô phỏng, chưa chứng minh độ tin cậy thực tế.

## Chuẩn bị

- [ ] Có Python và khả năng cài thư viện, tải model.
- [ ] Có 2 clip phát triển để chỉnh ngưỡng: ngã mô phỏng và hoạt động bình thường.
- [ ] Có 4 clip đánh giá riêng: 2 ngã mô phỏng, 2 hoạt động bình thường.
- [ ] Có đoạn người bị che hoặc ra khỏi khung để kiểm tra thiếu dữ liệu.
- [ ] Clip ngã dùng động tác mô phỏng có kiểm soát; không yêu cầu ngã thật.

Nếu chưa có clip, tính thời gian tìm/chọn clip vào 15 phút đầu. Không dùng clip đánh giá để chỉnh ngưỡng.

## Tiến độ và nghiệm thu từng phần

| Thời gian | Công việc | Điều kiện qua bước |
|---|---|---|
| 0–15 phút | Tạo môi trường, cài OpenCV/MediaPipe, tải model, chọn clip, đọc video | Hiển thị được frame; lấy được FPS hợp lệ; báo lỗi rõ nếu không mở được video |
| 15–35 phút | Nhận diện tư thế, vẽ landmark, kiểm tra độ rõ vai/hông | Landmark bám người; thiếu dữ liệu chuyển NO_DATA; chạy hết clip không crash |
| 35–55 phút | Hiệu chuẩn từ đoạn đứng, tính góc và độ hạ thấp, lưu lịch sử | Đứng có độ hạ thấp gần 0; hạ người làm giá trị tăng; nghiêng làm góc tăng |
| 55–80 phút | Bộ trạng thái, xác nhận theo thời gian, cảnh báo trên màn hình | Có NORMAL → SUSPECTED → ALERT trên clip ngã; chạy đối chứng bằng clip bình thường |
| 80–95 phút | CSV, pause, replay; âm thanh nếu còn thời gian | Một dòng log mỗi sự kiện; replay xóa lịch sử và lặp lại được kết quả |
| 95–110 phút | Khóa ngưỡng, chạy clip đánh giá, ghi kết quả | Có kết quả từng clip, thời điểm cảnh báo, báo nhầm và ca lỗi |
| 110–120 phút | README, ghi màn hình demo, chạy lại từ đầu | Chạy bằng một lệnh theo README; có video dự phòng |

## Thiết kế tối thiểu

### Thời gian và điều khiển replay

- Dùng thời gian video: `timestamp_ms = frame_index * 1000 / FPS`.
- Kiểm tra FPS lớn hơn 0 trước khi xử lý; nếu không hợp lệ, yêu cầu cấu hình FPS rõ ràng.
- Timestamp gửi vào model phải tăng; khi replay, tạo lại phiên model và đưa chỉ số frame về đầu.
- Tạm dừng không tăng chỉ số frame hoặc bộ đếm thời gian xác nhận.
- Không dùng thời gian xử lý thực tế của máy để tính vận tốc hoặc xác nhận nghi ngã.
- `Space`: tạm dừng/tiếp tục; `R`: phát lại từ đầu; `Q`: thoát.
- Khi hết video: giữ kết quả cuối và cho phép replay hoặc thoát.

### Đặc trưng

- Trung điểm vai S, trung điểm hông H; chuyển tọa độ sang pixel trước khi tính góc.
- Góc thân: góc đường S–H với phương thẳng đứng.
- Tâm thân: trung điểm S và H.
- Hiệu chuẩn: trung vị tâm thân và chiều cao đứng từ các frame hợp lệ đầu clip.
- Độ hạ thấp chuẩn hóa theo chiều cao đứng ban đầu.
- Lưu lịch sử khoảng 1–2 giây bằng deque.
- Chỉ tính đặc trưng khi landmark cần thiết đủ rõ.

### Bộ trạng thái

`CALIBRATING → NORMAL → SUSPECTED → ALERT`, kèm trạng thái `NO_DATA` khi thiếu mốc.

Ngưỡng thử ban đầu, chưa được kiểm chứng:

- Góc thân trên khoảng 60°.
- Hạ thấp khoảng 25% chiều cao đứng trong 0,7 giây.
- Hai dấu hiệu xảy ra trong cùng cửa sổ khoảng 1 giây, không bắt buộc cùng frame.
- Sau đó tư thế thấp và nghiêng duy trì khoảng 1,2 giây để cảnh báo.
- Trở lại tư thế bình thường trước xác nhận: hủy nghi ngã.
- Thiếu mốc: không cộng thời gian xác nhận; mất mốc quá 0,5 giây thì xóa sự kiện đang chờ.
- Giữ cảnh báo đã phát đến khi replay; thiếu mốc không xóa cảnh báo đã phát.
- Không có mốc đứng hợp lệ: hiển thị chưa hiệu chuẩn, không kết luận vừa ngã.

Định nghĩa và lưu rõ ngưỡng “tư thế thấp” trong cấu hình trước khi khóa ngưỡng. Chọn ngưỡng bằng clip phát triển.

### Hiển thị và log

- Hiển thị: khung xương, trạng thái, góc thân, độ hạ thấp, thời gian video.
- Cảnh báo rõ trên màn hình; âm thanh là tùy chọn.
- CSV: `video_id, event_id, video_timestamp_ms, angle_deg, drop_ratio, reason`.
- Chỉ ghi khi chuyển vào ALERT; không ghi lặp theo từng frame.

## Checklist nghiệm thu chức năng

| ID | Ca kiểm tra | Điều kiện đạt | Kết quả |
|---|---|---|---|
| F01 | Mở và phát hết video | Không crash; hết video dừng rõ ràng | Chưa chạy |
| F02 | Chạy có pause và không pause | Cảnh báo tại cùng thời điểm video, sai lệch tối đa một frame | Chưa chạy |
| F03 | Hiệu chuẩn khi đứng đầu clip | Có mốc hợp lệ | Chưa chạy |
| F04 | Thiếu đoạn đứng hoặc thiếu mốc | Hiển thị chưa hiệu chuẩn, không tự suy ra ngã | Chưa chạy |
| F05 | Clip ngã mô phỏng | Có chuỗi NORMAL → SUSPECTED → ALERT | Chưa chạy |
| F06 | Clip hoạt động bình thường | Ghi nhận rõ có hay không báo nhầm | Chưa chạy |
| F07 | Che người/ra khỏi khung | NO_DATA; không tạo cảnh báo mới từ khoảng thiếu dữ liệu | Chưa chạy |
| F08 | Giữ ALERT nhiều frame | Chỉ một dòng CSV cho sự kiện | Chưa chạy |
| F09 | Nhấn R | Xóa hiệu chuẩn, lịch sử, trạng thái; phát từ đầu và lặp lại kết quả | Chưa chạy |
| F10 | Nhấn Q | Đóng file log và giải phóng video/cửa sổ | Chưa chạy |

## Đánh giá sau khi khóa ngưỡng

Ghi cấu hình đã khóa và mốc bắt đầu động tác được gán nhãn cho từng clip. Độ trễ = thời điểm cảnh báo trừ thời điểm bắt đầu động tác, theo thời gian video.

| Clip | Nhãn kỳ vọng | Cảnh báo thực tế | Thời điểm bắt đầu | Thời điểm cảnh báo | Độ trễ | Đạt/Không đạt, ghi chú |
|---|---|---|---|---|---|---|
| E01 | Ngã mô phỏng | | | | | |
| E02 | Ngã mô phỏng | | | | | |
| E03 | Bình thường | | | | | |
| E04 | Bình thường | | | | | |

Mục tiêu chấp nhận demo:

- [ ] Phát hiện 2/2 clip ngã mô phỏng.
- [ ] Không báo nhầm trong 2 clip bình thường.
- [ ] Độ trễ không quá 3 giây trên các clip ngã phát hiện được.
- [ ] Xử lý đúng ca thiếu dữ liệu.
- [ ] Không crash và replay nhất quán.

Nếu không đạt, báo kết quả thực tế. Nếu sửa code/ngưỡng sau đánh giá, chạy lại các ca bị ảnh hưởng và ghi rõ thay đổi. Phát lại một clip nhiều lần chỉ kiểm tra tính lặp lại, không tăng số mẫu đánh giá.

## Mốc cắt phạm vi

- Phút 35 chưa có landmark: tập trung môi trường/model, bỏ âm thanh và trang trí.
- Phút 80 chưa có cảnh báo: dừng thêm chức năng, tập trung logic và số đo.
- Phút 110: ngừng thêm tính năng; đóng gói và ghi hình, ghi rõ phần chưa đạt.

## Bàn giao cuối

- [ ] Mã nguồn và danh sách thư viện.
- [ ] Model hoặc hướng dẫn tải/đặt model.
- [ ] Cấu hình ngưỡng đã khóa.
- [ ] Danh sách clip phát triển và clip đánh giá.
- [ ] CSV sự kiện và bảng kết quả nghiệm thu.
- [ ] README: một lệnh chạy, phím điều khiển, cách chọn clip, giới hạn.
- [ ] Video ghi màn hình dự phòng.

Kịch bản trình diễn khoảng 2 phút: mở clip → hiệu chuẩn → hoạt động bình thường → nghi ngã/cảnh báo → xem log → replay → nêu kết quả và một giới hạn. Giới thiệu đúng là demo phát hiện nghi ngã trên video ghi sẵn; tốc độ xử lý thực tế cần đo riêng trước khi tuyên bố thời gian thực.
