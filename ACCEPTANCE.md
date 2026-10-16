# Báo cáo CLI lịch sử — 16/10/2026

Bản web/dashboard và checklist mới nhất nằm trong [WEB_ACCEPTANCE.md](WEB_ACCEPTANCE.md).
Các kết quả dưới đây thuộc cấu hình CLI ban đầu, được giữ làm lịch sử thất bại.

**Đã triển khai và chạy xuyên suốt; chưa đạt mục tiêu demo phát hiện ngã.**
Thời gian thực hiện khoảng 35 phút, trong giới hạn 120 phút. Không sử dụng hết
thời gian để chỉnh ngưỡng theo tập đánh giá. Không có cảnh báo từ video thật;
ALERT/CSV chỉ được chứng minh bằng kiểm thử dữ liệu pose/Observation giả lập.

## Môi trường và cấu hình

- Môi trường đã chạy: `.venv-demo`, Python 3.9.13, dùng system site-packages
  hiện có; protobuf 4.25.3 được cài riêng trong venv, không thay package toàn cục.
- Phiên bản đối chiếu thực tế: MediaPipe 0.10.21, OpenCV contrib 4.11.0.86,
  NumPy 1.26.4, JAX/JAXlib 0.4.30. Đây là bộ khóa trong requirements.txt.
- Python 3.11.9 trong `.venv` có sẵn nhưng lượt cài sạch tải quá chậm và đã dừng.
  Không nghiệm thu khả năng cài sạch từ README trên môi trường mới.
- Model Lite tải từ Google, kiểm tra ZIP thành công; SHA-256:
  `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`.
- Cấu hình `configs/locked.json` khóa trước evaluation; SHA-256:
  `f8dd583a79466a38bb3797f7ac598703a708004a671cbd5a369944f571d50f4d`.
- Ngưỡng giữ nguyên giả thuyết PLAN.md; chưa chứng minh độ tin cậy thực tế.
  Chặn mốc torso ngoài khung được bổ sung sau lượt evaluation đầu, rồi chạy lại
  toàn bộ clip phát triển/đánh giá và control trên mã cuối; kết quả dưới đây dùng
  thư mục `logs/acceptance/`, không dùng các lượt thử trước.

## Bằng chứng chạy cuối

35/35 test pass, không skip: [tests.txt](logs/acceptance/tests.txt).
Test tích hợp dùng video I/O OpenCV thật và pose giả lập: hiệu chuẩn 2000 ms,
SUSPECTED 3000 ms, ALERT 4200 ms, replay/pause giữ cùng thời điểm cảnh báo.

Harness dùng **model thật, video thật và cửa sổ OpenCV thật** pass:
[result.json](logs/acceptance/controls/result.json). Baseline và hai phiên có
pause/R/Q được so sánh trace từng frame, bằng nhau ở cả Observation và Detection.
Đã kiểm tra hiển thị cửa sổ; phím được bơm tự động, chưa kiểm tra bàn phím vật lý.

Tất cả 7 video overlay phát triển/đánh giá được mở lại và decode đủ số frame,
khớp summary: 160, 150, 96, 110, 215, 180, 180 frame. Cả 7 SHA-256 video đầu
vào khớp manifest. Đã xem frame overlay tại 3566,7 ms để kiểm tra chữ/skeleton.

Đầu vào không tồn tại và FPS override bằng 0 đều được thử thực tế: báo lỗi rõ
`Could not open video source` / `fps_override must be ... greater than zero`.

## Kết quả phát triển

| Clip | Kết quả thực tế | Bằng chứng |
|---|---|---|
| D01 fall-01 | Baseline 2000 ms; NORMAL → SUSPECTED 3566,7 ms → NO_DATA 3900 ms; không ALERT | [summary](logs/acceptance/dev/D01.json), [video dự phòng](logs/acceptance/dev/D01.mp4) |
| D02 adl-01 | Baseline 2000 ms; không cảnh báo, 150 frame | [summary](logs/acceptance/dev/D02.json) |
| D03 fall-04 | Bắt đầu ngồi; không baseline, không cảnh báo, 96 frame | [summary](logs/acceptance/dev/D03.json) |

D01 mất các mốc cần thiết khi người xuống sát/ngoài mép hình; không đủ dữ liệu
cho 1200 ms xác nhận. Không giảm yêu cầu xác nhận hoặc suy diễn từ khoảng mất mốc.
Các ứng viên khác đã xem được ghi tại DATA_SOURCES.md; không tính là mẫu đánh giá.

## Đánh giá sau khi khóa ngưỡng

Các onset gán thủ công theo chuyển động hạ người, độ bất định khoảng ±167 ms;
không phải annotation chính thức. Độ trễ không có giá trị khi không phát cảnh báo.

| Clip | Nhãn | Onset video | Cảnh báo | Độ trễ | Kết quả và nguyên nhân |
|---|---|---:|---|---|---|
| E01 fall-02 | Ngã | 1500 ms | Không | N/A | FAIL; bắt đầu ngồi, không baseline đứng, 110 frame |
| E02 fall-03 | Ngã | 5500 ms | Không | N/A | FAIL; có baseline, góc thân chiếu 2D sau onset tối đa 25,83°, không đạt ngưỡng 60°, 215 frame |
| E03 adl-02 | Bình thường | N/A | Không | N/A | INCONCLUSIVE; không baseline trong hai giây đầu, 180 frame |
| E04 adl-03 | Bình thường | N/A | Không | N/A | PASS trên clip này; baseline 2000 ms, 180 frame |

[CSV kết quả](logs/acceptance/eval/results.csv),
[provenance JSON](logs/acceptance/eval/results.json).
Mỗi clip có CSV sự kiện, JSON summary, JSONL trace, stdout/stderr và MP4 cùng ID.
Không có sự kiện nên CSV video thật chỉ có header; đó là kết quả thực tế.

Phát hiện ngã: **0/2**. Cảnh báo nhầm quan sát: **0 trên 2 clip bình thường**,
nhưng chỉ **1/2 có detector đã hiệu chuẩn**, nên không kết luận đạt 2/2 đối chứng.
Không có số đo độ trễ cảnh báo; không đạt mục tiêu phát hiện với độ trễ <=3 giây.
Một lượt replay không làm tăng số mẫu đánh giá.

## Checklist F01–F10

| ID | Kết quả | Bằng chứng / giới hạn |
|---|---|---|
| F01 mở/phát hết | Đạt | 7 clip chạy hết; summary/MP4 decode đủ frame; EOF giữ trên cửa sổ thật |
| F02 pause | Đạt bằng harness | Model thật cho trace bằng nhau; test pose giả lập có ALERT tại cùng 4200 ms |
| F03 hiệu chuẩn đứng | Đạt trên D01/D02/E02/E04 | Baseline tại 2000 ms |
| F04 thiếu đoạn đứng/mốc | Đạt trên các ca đã chạy | D03/E01 không baseline, không cảnh báo; test lying và missing |
| F05 ngã ra ALERT | **Không đạt trên video thật** | D01 có SUSPECTED; không có clip thật đạt ALERT; giả lập không thay thế nghiệm thu này |
| F06 đối chứng bình thường | Đạt E04; E03 chưa kết luận | Không cảnh báo ở cả hai; E03 không hiệu chuẩn |
| F07 mất dữ liệu | Đạt trên ca kiểm soát | Video D02 tô đen frame 80–109: NO_DATA 2666,7 ms → NORMAL 3666,7 ms; không ALERT. Test logic có pending gap ngắn/dài |
| F08 CSV một dòng/event | Đạt ở logic/giả lập | [events.csv](logs/acceptance/synthetic_logic/events.csv) có một dòng sự kiện ở 4200 ms dù ALERT duy trì; chưa có sự kiện video thật |
| F09 replay | Đạt bằng harness | Model tạo lại, trace hai phiên bằng baseline; test ALERT giả lập lặp lại cùng thời điểm |
| F10 Q/cleanup | Đạt với phím bơm tự động | Hàm trả về, đóng cửa sổ/file/model/video; MP4 và CSV mở lại được; chưa thử bàn phím vật lý |

Ca F07 là video biến đổi từ D02, không tính thêm một mẫu đánh giá độc lập.
Ca F08 được ghi nhãn `SYNTHETIC_OBSERVATIONS_NOT_VIDEO` trong CSV; tái tạo bằng
`python scripts/verify_logic.py`. [Kết quả logic](logs/acceptance/synthetic_logic/result.json).

## Bàn giao và phần chưa nghiệm thu

Đã có mã nguồn, interfaces, cấu hình khóa, requirements, model cục bộ, downloader,
manifest split/nhãn/hash, README một lệnh chạy, log và video overlay dự phòng.
Các video/model/log nằm ngoài Git theo .gitignore nhưng hiện có trong workspace.

Chưa đạt: phát hiện ngã trên video thật, độ trễ phát hiện <=3 giây, hai đối chứng
đều hiệu chuẩn, cài sạch trên máy mới, thao tác bàn phím vật lý. Không quay màn
hình desktop hai phút; file MP4 bàn giao là video inference có overlay, không
phải bản ghi màn hình. Âm thanh tùy chọn chưa làm.

Kịch bản trình diễn trung thực: mở D01 → baseline → SUSPECTED/mất mốc → xem CSV
không sự kiện → replay → mở kết quả evaluation → giải thích điểm chưa đạt. Nếu
trình bày ALERT/CSV từ synthetic_logic phải nói rõ đó là kiểm thử logic giả lập.

Bước tiếp theo để nghiệm thu F05: thu clip đúng điều kiện (đứng khoảng 2–3 giây,
người và sàn còn trọn khung khi nằm, giữ nằm ít nhất 1,2 giây có mốc), tách clip
phát triển/đánh giá mới trước khi chỉnh ngưỡng, rồi chạy lại. Không thay số liệu
hiện có bằng kết quả từ clip lặp hoặc dữ liệu giả lập.

