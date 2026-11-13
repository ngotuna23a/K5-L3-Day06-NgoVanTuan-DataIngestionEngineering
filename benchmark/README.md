# Benchmark Python cơ bản

`questions.json` có **20 câu hỏi tiếng Việt**, đáp án tiếng Việt và evidence tiếng Anh từ corpus OpenStax.
Mỗi câu ghi ID, split, loại câu, chủ đề, gold source/trang PDF, evidence và filter đầu vào.
`alternative_gold` ghi nguồn bằng chứng tương đương đã xác định cho q01 và q17.

| Split | Số câu | Có filter |
|---|---:|---:|
| Dev — q01–q15 | 15 | 2 |
| Test — q16–q20 | 5 | 2 |

## Cách chia và sử dụng

- Chốt split trước khi chạy retrieval; giữ riêng các mục 1.4, 1.7, 2.4, 2.7 và 2.8 cho câu hỏi test.
- Đây là chia theo chủ đề câu hỏi, không phải chia độc lập tài liệu. Các khái niệm, trang chuyển mục và phần tổng kết vẫn có thể trùng nội dung; xem giới hạn trong `protocol.json`.
- Filter chỉ có `chapter`, lấy từ yêu cầu chương được ghi ngay trong câu hỏi; không dùng gold source/trang/đáp án làm filter.
- A và B không filter; C lọc theo input được cung cấp, và không lọc khi input filter rỗng. B/C dùng cùng chunks để so sánh riêng tác động metadata.
- Khi gọi retrieval chỉ truyền `id`, `split`, `question`, `filter`; gold, đáp án và topic chỉ dành cho đánh giá.
- Tinh chỉnh và chọn cấu hình trên dev theo thứ tự: Evidence Hit@3 cao nhất, Hit@1 cao nhất, thời gian ingest thấp nhất, rồi A/B/C nếu vẫn bằng nhau.
- Sau khi cố định cấu hình, chạy cả ba trên cùng 5 câu test và báo riêng kết quả. Không dùng test để điều chỉnh; nếu đã dùng thì ghi rõ và cần tập test mới để kiểm tra độc lập.

`protocol.json` lưu SHA-256 của benchmark/corpus/PDF, quy tắc chọn cấu hình và 10 vị trí nguồn để chấm coherence.
Chưa chạy embedding, retrieval hay tạo số liệu benchmark. Việc đọc câu test hiện tại phục vụ xây dựng và xác minh evidence.

## Kiểm tra

Chạy từ thư mục gốc:

```powershell
& .\starter\.venv\Scripts\python.exe -m starter.src.validate_benchmark
```

Validator kiểm tra schema, split, filter, SHA-256, vị trí audit và evidence trong corpus lẫn text trích xuất từ PDF gốc.
Evidence được đối chiếu sau chuẩn hóa khoảng trắng. Đây không phải kiểm tra trực quan PDF hoặc thay thế nhãn thủ công.
Công cụ AI hỗ trợ soạn câu và rà soát nội dung; học viên cần đọc, hiểu và xác minh lại trước khi nộp.

Khi đánh giá, một hit phải có đúng nguồn/trang và đủ evidence chính hoặc alternative đã ghi.
Exact substring chỉ là proxy tự động; ghi nhận evidence tương đương qua adjudication và lưu lý do.
Không suy nhãn grounding/coherence từ việc có substring, không gọi grounding là độ chính xác câu trả lời LLM.

## Attribution

Evidence là nội dung trích từ **Introduction to Python Programming**, ©2026 Rice University/OpenStax.
**Access for free at openstax.org.** Nguồn: https://openstax.org/details/books/introduction-python-programming

Nội dung trích xuất theo **CC BY-NC-SA 4.0**, dùng phi thương mại và giữ attribution/license khi chia sẻ.
Không thay đổi license của mã nguồn dự án.
