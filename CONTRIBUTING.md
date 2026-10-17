# Đóng góp cho VinFall

Mỗi thay đổi nên được thực hiện trên một branch riêng và gửi Pull Request (PR) vào `main` để nhóm xem xét.

## Tạo branch

Sau khi clone repo, kiểm tra và commit hoặc stash các thay đổi đang làm trước khi chuyển branch:

```powershell
git status
git switch main
git pull --ff-only origin main
git switch -c feature/ten-tinh-nang
```

Dùng tên ngắn gọn mô tả công việc, ví dụ `feature/contribution-guide` hoặc `fix/webcam-timeout`.

## Kiểm tra và commit

Thiết lập môi trường theo README. Với thay đổi Python, chạy kiểm thử trước khi gửi PR:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp runtime/test-tmp
git diff --check
git diff
git add duong/dan/file-da-sua
git diff --cached
git commit -m "docs: add contribution guide"
```

Chỉ stage các file thuộc thay đổi. Không commit môi trường Python, dataset, trọng số model, cache, kết quả chạy hoặc thông tin bí mật. Với thay đổi chỉ gồm tài liệu, kiểm tra nội dung và `git diff --check` là đủ.

## Mở Pull Request vào main

```powershell
git push -u origin feature/ten-tinh-nang
```

Trên GitHub, mở **Pull requests → New pull request**, chọn **base: main** và **compare: branch vừa push**. Kiểm tra diff, viết tiêu đề và mô tả rồi bấm **Create pull request**.

Mô tả PR cần nêu vấn đề, thay đổi đã thực hiện và cách kiểm tra. Thêm ảnh nếu sửa giao diện; ghi rõ các kiểm tra chưa chạy và lý do. Chờ nhóm review trước khi merge.
