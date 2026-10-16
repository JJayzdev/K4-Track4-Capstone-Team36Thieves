# Nghiệm thu web VinFall — 2026-10-16

## Cập nhật giao diện

Dashboard được thiết kế lại với màu xanh đậm/xanh ngọc, thẻ phòng, tổng quan số
phòng/video đang phát/cảnh báo, nhật ký bên cạnh và trạng thái cảnh báo giữ nổi bật
sau khi video lặp. Bổ sung xem lớn từng phòng và nút xem lại từ khoảng 2 giây trước
thời điểm cảnh báo. Trang upload/phân tích có hướng dẫn, nút thao tác sát vùng chọn
video và cùng theme với dashboard. Thông tin model/cấu hình chuyển vào expander.

Đã kiểm tra trên trình duyệt: 4 video H.264 readyState 4, không lỗi; đúng hai cảnh
báo R01 tại 3,80 s và R03 tại 4,76 s; không tăng số cảnh báo qua nhiều vòng lặp.
Phát lại xóa cảnh báo; pause giữ nguyên thời gian ở khoảng 0,596 s và số video đang
phát về 0. Nút xem lại phòng 03 mở video lớn, phát được và đóng được. Bố cục ở
1280 px và 640 px không tràn ngang. Ngưỡng và các file phân tích nguồn được giữ
nguyên ở cấu hình v3; đây là kiểm tra giao diện, không phải kết quả đánh giá model mới.
Đã bấm phân tích R03 qua thư viện bằng nút ở vị trí mới: hoàn tất 173 frame,
6,92 s, đúng một sự kiện 4,760 s; hai video đầu vào/kết quả đều readyState 4,
không lỗi trình duyệt.

Ảnh/bằng chứng: `logs/frontend/overview.jpg`, `rooms.jpg`, `upload.jpg`,
`narrow.jpg`, `browser.json`, `analysis.json`. Mã HTML/CSS nằm trong
`src/vinfall/templates/dashboard.html`, theme chung trong `src/vinfall/theme.py`.

## Cập nhật v3: sửa bỏ sót phòng 03

Phòng 03 (R03) bắt đầu có toàn thân hợp lệ ở 1960 ms; cutoff 2000 ms của v2
chỉ lấy được hai mẫu, nên không hiệu chuẩn suốt clip. V3 chốt từ 2000 ms nếu
đã đủ mẫu; nếu thiếu thì thu thêm mẫu đứng hợp lệ đến 3000 ms, chốt ngay khi đủ.
Giữ nguyên điều kiện toàn thân/đầu gối/góc đứng, các ngưỡng nghi ngã và xác nhận.
Không lấy mẫu sau deadline, không dùng tên/nhãn clip để tạo cảnh báo.

Đã chạy video thật, audit và kiểm tra trên trình duyệt:

- R03: hiệu chuẩn 2520 ms → SUSPECTED 3560 ms → đúng một ALERT **4760 ms**; chạy lại độc lập cho trace giống hệt từng frame.
- Phòng 01 vẫn cảnh báo 3800 ms; phòng 02 không có cảnh báo (clip chưa có nhãn nguồn); phòng 04 đối chứng bình thường vẫn không cảnh báo.
- Dashboard hiển thị hai cảnh báo, đúng phòng 01 và 03; video H.264 phát được; CSV phòng 03 đúng một dòng 4760 ms.
- 71 tests passed, gồm late entry, hard deadline, không dùng mẫu ngồi/nằm, reset và reason trong grace period.
- Chạy lại bốn clip đánh giá đã biết với cấu hình mới: kết quả vẫn 0/2 clip ngã có cảnh báo; ba clip không hiệu chuẩn. Không coi đây là tập đánh giá mới độc lập.

Web và prepare_dashboard mặc định dùng `configs/hospital_calibration_v3.json`,
SHA-256 `f4b37cc179683dd08d525b2788f71cfe75df7537d169a04498a46853628a88da`.
V2 vẫn giữ nguyên để tái hiện lỗi. Không thay dữ liệu nguồn hoặc chèn frame đứng.

Bằng chứng: `logs/calibration_v3/timing.json`, `tests_final.txt`, `before.json`,
`after_R03/`, `dev/`, `eval_regression/`, `logs/web/dashboard_audit.json` và manifest
hiện tại `runs/dashboard/current.json`; `repeat.json`, `browser.json` và ảnh
`logs/calibration_v3/dashboard-r03.jpg`. R03 không có annotation nguồn trong mirror;
người dùng xác nhận quan sát ngã. Không đưa clip này vào thống kê accuracy của tập
có annotation nguồn. Chỉ nghiệm thu sửa lỗi cụ thể này, chưa nghiệm thu độ tin cậy
bệnh viện.

## Báo cáo v2 trước khi sửa phòng 03

Checklist và số liệu dưới đây thuộc v2, giữ làm lịch sử; nội dung v3 ở trên là
trạng thái bàn giao hiện tại.

## Cập nhật mới nhất: webcam realtime

Đã bổ sung chế độ webcam theo yêu cầu mở rộng phạm vi của người dùng. Chạy
trên cùng máy localhost, một camera/một người. Không ghi ảnh hoặc video camera.
Server vẫn chạy ở `http://127.0.0.1:8501/`; camera đã dừng khi bàn giao.

| Hạng mục webcam | Trạng thái thực tế |
|---|---|
| Camera và model thật | Đạt: Integrated Webcam, 640×480, Full; script xử lý 109 frame trong 4,187 giây capture, khoảng 25,8 FPS, đóng/giải phóng thành công |
| Hình realtime qua browser | Đạt: ảnh 640×480 tải hoàn chỉnh; metrics tăng theo capture; FPS inference quan sát khoảng 6–18 khi có giao diện, preview khoảng 5 lần/giây |
| Thời gian | Camera metadata trả FPS 0: dùng monotonic capture elapsed, không đoán FPS. Test kiểm tra timestamp truyền nguyên vẹn vào pipeline, khung trùng không xử lý lại |
| Bắt đầu/dừng | Đạt trên UI thật: bắt đầu mở camera sau model + 5 giây, dừng ẩn hình camera; bắt đầu lại được |
| Hiệu chuẩn lại | Đạt về vòng đời phiên: nút bật sau RUNNING, tạo UUID/CSV mới, thời gian từ đầu, model/state mới. Chưa kiểm chứng baseline tư thế đứng trên người toàn thân thật |
| Chuyển chế độ | Đạt: đang chạy webcam → dashboard → quay lại webcam ở trạng thái đã dừng, không còn ảnh, nút bắt đầu bật |
| Tải CSV | Đạt qua trình duyệt: hash khớp file phiên, chỉ header vì không có cảnh báo thực trong lần thử này |
| Cảnh báo và reset logic | Đạt qua test Observation giả lập với detector thật: đúng một cảnh báo/CSV, phiên kế tiếp không lẫn sự kiện. Không tính là kiểm chứng ngã qua camera vật lý |
| Lỗi và cleanup | Đã test bằng nguồn/model giả: lỗi đọc, lỗi model không mở camera, phiên bận, stop khi khởi tạo, hết heartbeat trước/sau mở camera; giải phóng và thử lại được |
| Đóng tab | Cơ chế lease 20 giây đã test logic; chưa đo riêng bằng thao tác đóng tab với camera vật lý |
| Phát hiện ngã qua webcam thật | **Chưa nghiệm thu**: chưa có thử động tác với người toàn thân; lần phần cứng/UI này không đủ mốc đứng và không có cảnh báo |

81 tests đã qua, bao gồm 10 test realtime. Bằng chứng:
`logs/webcam/tests_final.txt`, `hardware.json`, `browser.json`, `webcam-ui.jpg`.
Ảnh giao diện được chụp sau khi camera tắt, không chứa khung camera.

Cấu hình hiện tại là `configs/hospital_calibration_v3.json`. Phòng 03 đã sửa
hiệu chuẩn ở 2,52 s và báo tại 4,76 s; bằng chứng chạy/so sánh trong
`logs/calibration_v3/`. Dashboard hiện có cảnh báo R01 tại 3,80 s và R03 tại
4,76 s. Các bảng/log 64 test bên dưới ghi lại giai đoạn web trước bản sửa này.
Kết quả bỏ sót tập đánh giá riêng vẫn là hạn chế chưa giải quyết.

## Kết luận

Luồng web localhost và dashboard 4 video replay đã chạy trên trình duyệt thật.
**Chưa nghiệm thu chất lượng phát hiện ngã hoặc sử dụng tại bệnh viện.**
Cấu hình mới phát hiện một clip phát triển từng bị bỏ sót; tập đánh giá riêng
vẫn không có cảnh báo ở cả hai clip ngã, ba trong bốn clip không hiệu chuẩn.

## Checklist đã chạy

| Hạng mục | Trạng thái và bằng chứng |
|---|---|
| Một lệnh khởi động | Đạt trên môi trường hiện tại: `.venv-demo\Scripts\python.exe run_web.py` |
| Chỉ localhost | Đạt: listen 127.0.0.1:8501, health HTTP 200; không public/tunnel |
| Upload → phân tích → phát | Đạt: URFD fall-01, 160 frame, 30 FPS, 5,333 s; video đầu vào/kết quả readyState 4, không lỗi; kết quả phát hết |
| Cảnh báo thật qua web | Đạt cho R01: 157 frame, 25 FPS, 6,28 s; đúng 1 sự kiện tại 3800 ms; bảng UI 3.800 giây; video kết quả phát hết |
| Tải video/CSV | Đạt: video và CSV tải từ trình duyệt khớp byte với đầu ra; CSV R01 có đúng một dòng sự kiện tại 3800 ms |
| Phân tích lại | Đạt: hai lượt URFD có trace giống nhau; hai lượt chuẩn bị dashboard R01 giống từng frame; R01 chạy web cũng trùng trace batch độc lập |
| Không lẫn phiên | Đạt: model/state/history mới mỗi analyze_video, test phiên/reset; chạy các clip trong thư mục riêng; no-person qua UI không mang cảnh báo trước đó |
| Không có người | Đạt qua UI: clip đen 90 frame/3 s, 0 pose, 0 hiệu chuẩn, 0 sự kiện; thông báo tiếng Việt và video vẫn phát được |
| Thiếu hiệu chuẩn | Đạt: cảnh báo rõ qua pipeline; R03 dashboard ghi Không đủ mốc đứng/CHƯA HIỆU CHUẨN, không coi là an toàn |
| File lỗi/FPS lỗi | Backend đã chạy test: từ chối file không giải mã và FPS 0 trước khởi tạo model. Chưa nghiệm thu thao tác upload file lỗi qua trình duyệt |
| Nhiều phòng tự phát | Đạt: R01/R04/R03/URFD-D02, H.264, 4 video readyState 4, không lỗi, cùng tự chạy; kiểm tra phát hết từng clip |
| Cảnh báo đúng phòng/thời gian | Đạt: phòng 01, R01, 00:03.80 từ detector; trạng thái lấy trace; requestVideoFrameCallback dùng mediaTime của frame đang trình bày |
| Pause/reset/lặp | Đạt: dừng cả 4 giữ currentTime ~0,632 s và count 0 qua thời gian chờ; phát lại xóa latch; phát tiếp có 1 cảnh báo; nhiều vòng lặp vẫn count 1 |
| CSV không lặp | Đạt: audit frame/trace/CSV tất cả phòng, đúng 1 dòng tổng hợp, event ID duy nhất |
| Codec/thứ tự/thời gian | Đạt: test mã hóa H.264 thực tế giữ thứ tự frame, FPS 29,97; audit video dashboard giải mã đủ 157/259/173/150 frame, FPS 25/25/25/30 |
| Laptop và cửa sổ hẹp | Đã xem UI ở 1366×768 và cửa sổ hẹp mặc định; lưới video + bảng cảnh báo; cần cuộn để xem hết ở cửa sổ thấp |
| Cài sạch | Chưa nghiệm thu; requirements và hướng dẫn có trong README |
| Bệnh viện/camera trực tiếp | Replay chưa chứng minh chất lượng bệnh viện; webcam mới chỉ nghiệm thu luồng camera/UI ở bảng cập nhật phía trên |

64 tests passed. Test pose/Observation giả lập dùng kiểm chứng logic, không tính
vào số clip thực tế hoặc độ chính xác phát hiện.

## Cấu hình và mô hình

- Model Full SHA-256: `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`.
- `configs/hospital_locked.json` SHA-256: `826164d73aebb6c20989886b4d6d073db52217d9ff642e0136dea06341c22cca`.
- Chọn Full sau so sánh Lite/Full/Heavy trên cùng tập phát triển. Heavy có coverage kém trên R01; không chọn theo tên hoặc nhãn clip.
- Bổ sung góc thân world 3D khi có; hạ nhanh 15%, thấp 20%, nghiêng 60°, xác nhận 1,2 s. Các ngưỡng dùng chung cho mọi phòng.
- R01 hạ khoảng 21%, không vượt ngưỡng thấp 25% cũ. Ngưỡng mới phát cảnh báo 3,80 s, sau onset 1,88 s là 1,92 s. Đây là kết quả phát triển dùng chỉnh ngưỡng.
- Cấu hình khóa trước đánh giá R05–R08; không chỉnh theo các thất bại đánh giá.

## Tập đánh giá riêng đã chạy

| Clip | Nhãn nguồn | Kết quả |
|---|---|---|
| R05 | Ngã, onset 2,12 s | Bỏ sót dù đã hiệu chuẩn. SUSPECTED tại 2,48–2,52 s rồi góc không giữ ≥60°; không đủ 1,2 s xác nhận |
| R06 | Ngã, onset 5,417 s | Không có pose hợp lệ, không hiệu chuẩn; không tạo cảnh báo |
| R07 | Bình thường | 50/168 frame có pose, không hiệu chuẩn; không đủ kết luận về báo nhầm |
| R08 | Bình thường | 93/336 frame có pose, không hiệu chuẩn; không đủ kết luận về báo nhầm |

Raw alert ở clip ngã: **0/2**. Có 3 clip không hiệu chuẩn; không được gọi đó là
3 dự đoán âm đúng. Không suy ra recall/specificity lâm sàng từ mẫu này. Các
thất bại URFD trước đây cũng được giữ trong ACCEPTANCE.md và logs.

## Bằng chứng trên máy

- `logs/web/tests_final.txt`: 64 tests, OK.
- `logs/web/dashboard_audit.json`: frame, timestamp, sự kiện/CSV của cả 4 phòng.
- `logs/web/dashboard_repeat.json`: trace R01 giống nhau ở hai pipeline độc lập.
- `logs/web/browser_positive.json`: R01 chạy qua UI, CSV tải khớp byte, trace trùng batch.
- `logs/web/browser_repeat.json`: hai lượt upload URFD độc lập.
- `logs/web/browser-paused-before-alert.json`, `browser-still-paused.json`: currentTime không tiến, count 0.
- `logs/web/dashboard-laptop.jpg`: màn hình bốn phòng và cảnh báo thực.
- `logs/hospital_holdout_final/comparison.csv` và JSON: bốn clip đánh giá, hash config/model/manifest.
- `logs/hospital_dev_v2/`, `logs/hospital_controls_v2/`, `logs/hospital_r04_v2/`: phát triển/đối chứng, phân biệt tập đánh giá.
- `runs/dashboard/current.json`: phân bổ phòng, nguồn video, trace và CSV hiện tại.

Video/model/log lớn chỉ lưu local, không gộp vào Git. Nguồn Le2i mirror chưa
xác minh giấy phép gốc; video công khai không được mô tả là dữ liệu bệnh viện.
