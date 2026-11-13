# Bài làm Day 06 — Qdrant Local + FastEmbed

Ngô Văn Tuân · MSSV **2A202603630** · Lớp **L3A**.

Bài làm dùng Python 3.13.9, Qdrant Local và embedding `intfloat/multilingual-e5-small` chạy CPU, 384 chiều, cosine exact search. Không cần Docker hoặc API key. Các file PostgreSQL trong bộ starter gốc không được dùng cho phương án này.

## Dữ liệu và kết quả đã nộp

- PDF gốc ở thư mục root; corpus 59 trang và nguồn/license trong `data/manifest.json`, `data/pages.jsonl`.
- 20 câu hỏi, chia trước 15 dev / 5 test: `benchmark/questions.json`; quy tắc và vị trí audit: `benchmark/protocol.json`.
- Cấu hình: `starter/config.json`. A: 500 ký tự, overlap 50; B: heading/đoạn tối đa 1.000 ký tự; C dùng cùng chunk/vector với B và thêm filter theo input.
- `results/`: chunks, trace top-3, chỉ số dev/test, lựa chọn trên dev và 90 nhãn audit đã được học viên xem/xác nhận.
- Báo cáo: `report/individual/2A202603630_NgoVanTuan.md`.
- Model/database cache ở `.cache/`, môi trường ở `starter/.venv/`; Git bỏ qua các thư mục này.

## Cài môi trường

Chạy PowerShell từ thư mục gốc của repo. Thư viện đã được kiểm tra trên Windows/Python 3.13; lần tải model cần khoảng 490 MB cho trọng số và tokenizer.

```powershell
python -m venv starter/.venv
& .\starter\.venv\Scripts\python.exe -m pip install -r starter/requirements-local.lock.txt
& .\starter\.venv\Scripts\python.exe starter/scripts/download_model.py
& .\starter\.venv\Scripts\python.exe -m starter.src.check_local_setup
```

Script download giữ đúng snapshot `614241f622f53c4eeff9890bdc4f31cfecc418b3`, kiểm tra SHA-256 trong `artifacts/local_setup.json` và cấu hình cache để FastEmbed đọc offline. Kiểm tra cache đã có bằng cách thêm `--offline` vào lệnh download.

## Tái lập thí nghiệm

Thực hiện trên **bản clone riêng** để giữ bộ kết quả bài nộp. Trước khi chạy lại, dùng Explorer đổi tên thư mục `results` của bản clone thành `results_submitted`; các lệnh dưới sẽ tạo bộ `results` mới.

```powershell
& .\starter\.venv\Scripts\python.exe -m starter.src.prepare_corpus
& .\starter\.venv\Scripts\python.exe -m starter.src.validate_benchmark
& .\starter\.venv\Scripts\python.exe -m starter.src.run --stage ingest
& .\starter\.venv\Scripts\python.exe -m starter.src.run --stage verify
& .\starter\.venv\Scripts\python.exe -m starter.src.run --stage benchmark --split dev
& .\starter\.venv\Scripts\python.exe -m starter.src.run --stage benchmark --split test
```

Kỳ vọng: 59 trang; A = 212 chunk, B/C = 240 chunk; vector B/C khớp trong độ chính xác float32. Nạp lại cùng corpus không tạo bản ghi trùng; chunk cũ của các tài liệu trong batch được thay sau khi ghi thành công.

Benchmark tạo 45 trace dev và 15 trace test. Chọn cấu hình trên dev, cố định snapshot rồi mới chạy test. CLI giữ bộ test đã chạy; không chỉnh cấu hình theo test. Thời gian ingest và thứ tự tiebreak có thể khác theo máy, đặc biệt khi B/C đồng điểm. Bộ bài nộp hiện tại chọn B.

Các kết quả tự động đã đo:

| Cấu hình | Dev Hit@1 | Dev Hit@3 | Test Hit@1 | Test Hit@3 |
|---|---:|---:|---:|---:|
| A | 3/15 | 5/15 | 3/5 | 3/5 |
| B | 7/15 | 10/15 | 2/5 | 3/5 |
| C | 7/15 | 10/15 | 2/5 | 3/5 |

Hit yêu cầu đúng nguồn/trang và đủ evidence chính hoặc alternative; so khớp tự động chuẩn hóa Unicode/khoảng trắng. Grounding/coherence dùng nhãn riêng, không suy từ Hit@3.

## Audit và kiểm tra

Tổng hợp lại các CSV audit đã nộp, không cần tải model hoặc mở database:

```powershell
& .\starter\.venv\Scripts\python.exe -m starter.src.audit --stage summarize
& .\starter\.venv\Scripts\python.exe -m unittest discover -s starter/tests -v
```

Bộ hiện tại có 34 tests. Qdrant Client 1.20.0 có thể in `ResourceWarning` từ kết nối SQLite tạm khi chạy unit test trên Python 3.13; các test vẫn đạt.

Nếu tạo bộ audit mới trong bản tái lập, chạy `python -m starter.src.audit --stage prepare`, sau đó điền `score` hoặc `metadata_ok`, `reason`, `reviewer` rồi summarize. Các đề xuất và kiểm tra tự động không được tự coi là nhãn đã xác nhận. Mỗi cấu hình cần 10 mẫu coherence, 15 bản ghi metadata và 5 mẫu grounding; mẫu được chọn trước trong protocol.

Lỗi runtime của entry point được ghi vào `results/ingestion_errors.jsonl` khi có lỗi. Model/backend lỗi sẽ được báo rõ, không thay bằng vector giả.

## Chốt bài

Thông tin học viên trong `STUDENT.md` dùng tag `day06-2A202603630` làm mốc commit bài nộp. Tạo tag sau commit cuối và push cả branch `main` lẫn tag; nộp link repo theo kênh giảng viên chỉ định. Thời hạn và quy ước tên repo theo thông báo lớp.
