# Corpus: Python cơ bản

- Nguồn: [Introduction to Python Programming — OpenStax](https://openstax.org/details/books/introduction-python-programming).
- PDF gốc: `Introduction_to_Python_Programming-WEB.pdf` tại thư mục gốc; giữ nguyên file.
- Phạm vi: chương 1 **Statements** và chương 2 **Expressions**, trang PDF 17–76.
- Loại trang PDF 46 vì chỉ có footer; còn **59 trang nội dung**.
- `page` là trang vật lý PDF, đếm từ 1; `metadata.book_page` là số trang in trong sách, nhỏ hơn 10.
- `pages.jsonl`: mỗi dòng là một trang, có text, nguồn, page ID, số ký tự và metadata chương.
- `manifest.json`: nguồn, license, SHA-256, phiên bản PDF, cách đếm và danh sách trang.

## License và attribution

License trong trang PDF 4: **CC BY-NC-SA 4.0**, ©2026 Rice University.
Nội dung trích xuất được chia sẻ theo [cùng license](https://creativecommons.org/licenses/by-nc-sa/4.0/), dành cho mục đích phi thương mại.
Mỗi bản ghi trang giữ attribution: **Access for free at openstax.org.**
Thay đổi: chọn hai chương đầu, trích xuất text, chuẩn hóa Unicode/newline, bỏ footer và thêm metadata.
License này áp dụng cho nội dung sách được trích xuất, không tự động áp dụng cho mã nguồn dự án.

## Tái tạo dữ liệu

Chạy từ thư mục gốc trong PowerShell, sau khi cài `pypdf>=5,<7` vào `starter/.venv`:

```powershell
& .\starter\.venv\Scripts\python.exe -m starter.src.prepare_corpus
```

Lệnh ghi lại hai output, không thêm trùng trang. Script kiểm tra vị trí bookmark và license của PDF trước khi chạy.

## Kiểm tra và giới hạn

Đã đọc mẫu text trích xuất và đối chiếu mục lục/bookmark, chưa kiểm tra trực quan từng trang PDF.
Một số công thức không trích xuất đầy đủ, thấy ở trang PDF 57; bảng và code/output có thể mất bố cục.
Khi tạo benchmark, đối chiếu evidence với PDF gốc và tránh dùng công thức hoặc bảng bị mất nội dung.
Không có OCR hay nội dung được tự bổ sung. Metadata `chapter` có hai giá trị 1/2 để thử filter theo chương.
