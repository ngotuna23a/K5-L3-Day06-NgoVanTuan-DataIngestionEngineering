# Báo cáo cá nhân — Day 6

- Họ và tên: Ngô Văn Tuân
- MSSV: 2A202603630
- Lớp: L3A

## Dữ liệu và pipeline

- Chủ đề: Python cơ bản; OpenStax Introduction to Python Programming, ©2026 Rice University, CC BY-NC-SA 4.0.
- Corpus: chương 1 Statements và chương 2 Expressions; trang PDF 17–76, loại trang 46 chỉ có footer; 59 trang nội dung. Manifest: `data/manifest.json`.
- Chuẩn hóa: Unicode NFC, newline, khoảng trắng cuối dòng; bỏ running footer và giữ attribution riêng cho mỗi trang. Giữ số trang vật lý PDF, trang in và chương.
- Giới hạn: một số công thức không trích xuất được đầy đủ, bảng/code có thể mất bố cục; chưa kiểm tra trực quan toàn bộ PDF.
- Hạ tầng: Qdrant Client 1.20.0 chạy Local lưu bền vững; FastEmbed 0.9.1/ONNX Runtime 1.31.1 chạy CPU, model intfloat/multilingual-e5-small, mean pooling, L2 normalization, 384 chiều; tiền tố `query: ` và `passage: `; cosine distance, exact search. Đã đạt smoke test với vector thật và chạy lại bằng cache.
- Model snapshot: `614241f622f53c4eeff9890bdc4f31cfecc418b3`; SHA-256 trọng số và phiên bản thư viện trong `artifacts/local_setup.json`, dependency lock trong `starter/requirements-local.lock.txt`.
- Collection: `day06_python` trong `.cache/qdrant`; đã ingest 692 bản ghi: A = 212, B = 240, C = 240. Đã kiểm tra dữ liệu sau khi đóng/mở lại và nạp lại không trùng.
- Chạy từ root bằng Python của `starter/.venv`: `python -m starter.src.run --stage ingest`; kiểm tra dữ liệu đã lưu: `python -m starter.src.run --stage verify`.
- Lệnh benchmark đã dùng: `python -m starter.src.run --stage benchmark --split dev`, sau đó `python -m starter.src.run --stage benchmark --split test` khi đã cố định lựa chọn. Giữ nguyên kết quả sau khi đánh giá test.
- Phí API ingest local: 0 USD; chưa đo chi phí điện/phần cứng. Cấu hình, phân bố độ dài, token, thời gian và kết quả kiểm tra: `results/ingestion_summary.json`.
- Metadata: document_id, source, page, chapter, chapter_title, book_page, language. Chapter lấy từ bookmark/mục lục đã đối chiếu; dùng phân biệt chương 1/2 khi câu hỏi yêu cầu.

## Cấu hình và benchmark

- A: fixed-size 500 ký tự, overlap 50; 212 chunk.
- B: theo heading/đoạn, tối đa 1.000 ký tự, không overlap; 240 chunk. PDF không có dòng trống nên ranh giới heading được suy ra bằng heuristic; heading liên tiếp được giữ cùng nội dung.
- C: dùng lại chính chunk và vector của B, chỉ thêm chapter filter khi input yêu cầu; 240 chunk. Thời gian chuẩn bị chung được tính cho cả B/C trong báo cáo, không giả định có lượt embedding C riêng.
- Mỗi chunk giữ nguồn, trang và khoảng ký tự trên trang; không vượt trang. Max input token gồm prefix và special tokens: A = 215, B/C = 291, đều dưới giới hạn 512; không có truncation.
- Benchmark: 20 câu, 15 dev / 5 test; 4 câu có chapter filter, gồm 2 dev và 2 test. Evidence có đối chiếu corpus và text PDF bằng validator.
- Tiêu chí chọn: dev Evidence Hit@3, sau đó Hit@1, thời gian ingest, cuối cùng thứ tự A/B/C. Xem `benchmark/protocol.json`.
- Hạn chế split: câu hỏi được chia theo chủ đề, vẫn cùng sách và có nội dung tổng kết/khái niệm giao nhau.

## Kết quả

Đã chạy 15 câu dev và 5 câu test cho mỗi cấu hình. Dev có 45 trace top-3 tại `results/dev_traces.jsonl`; test có 15 trace top-3 tại `results/test_traces.jsonl`. Tổng hợp tương ứng trong `results/dev_summary.json` và `results/test_summary.json`. Test được chạy sau khi cố định lựa chọn; bộ nhãn audit đã được học viên xem và xác nhận.
Điểm dưới đây là tự động theo đúng nguồn/trang và đủ evidence đã chốt sau chuẩn hóa Unicode/khoảng trắng; evidence tương đương cần adjudication riêng. Thời gian trong bảng là ingest, có tính phần chuẩn bị B dùng chung cho C.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 3/15 | 5/15 | 212 | 13,590 s | 0 USD API |
| B | dev | 7/15 | 10/15 | 240 | 32,037 s | 0 USD API |
| C | dev | 7/15 | 10/15 | 240 | 32,086 s | 0 USD API |
| A | test | 3/5 | 3/5 | 212 | 13,590 s | 0 USD API |
| B | test | 2/5 | 3/5 | 240 | 32,037 s | 0 USD API |
| C | test | 2/5 | 3/5 | 240 | 32,086 s | 0 USD API |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 và trung bình /2 |
|---|---|---|---|---|
| A | 1,00/2 (10) | 15/15 | 0/2 | 0: 1; 1: 1; 2: 3; TB 1,40/2 (5) |
| B | 0,90/2 (10) | 15/15 | 0/2 | 0: 2; 1: 0; 2: 3; TB 1,20/2 (5) |
| C | 0,90/2 (10) | 15/15 | 2/2 | 0: 1; 1: 1; 2: 3; TB 1,40/2 (5) |

A/B không áp dụng filter theo cấu hình; 0/2 là mức tuân thủ phạm vi chương được yêu cầu trong hai câu test có filter, không phải lỗi gán metadata. C áp dụng filter và đạt 2/2. Grounding là mức đủ evidence trong top-3, không phải độ chính xác câu trả lời LLM.

Mẫu chấm: `results/coherence_audit.csv` (30 dòng), `results/metadata_audit.csv` (45 dòng) và `results/grounding_audit.csv` (15 dòng). Coherence dùng đúng 10 vị trí đã chốt trong protocol; nếu nhiều chunk bao phủ thì chọn chunk có vị trí bắt đầu sớm nhất. Mẫu đầu trang có thể chứa credit hình hoặc phần nối từ trang trước, nên có giới hạn về tính đại diện.
Người xem và xác nhận nhãn: **Ngô Văn Tuân — 2A202603630**. Coherence/grounding do Codex (AI) đọc nội dung và đề xuất điểm theo thang 0–2; metadata được đề xuất qua đối chiếu tự động với chunk gốc, text PDF và bookmark chương. Học viên xác nhận đã xem và đồng ý với toàn bộ đề xuất. Các cột `proposed_*` giữ nguồn đề xuất; `score`/`metadata_ok`, `reason`, `reviewer` cùng thời điểm ghi nhận xác nhận lưu nhãn chính thức. Tổng hợp tại `results/manual_audit_summary.json`; tái tổng hợp bằng `python -m starter.src.audit --stage summarize`. Đây là đánh giá có AI hỗ trợ và học viên xác nhận, không độc lập/ẩn cấu hình; có nguy cơ thiên lệch và đồng thuận với đề xuất ban đầu.

## Phân tích và kết luận

- Chọn **B trên dev**, cố định cấu hình và snapshot tại `results/selection.json`. B/C đồng điểm Hit@3 và Hit@1; B thắng theo thời gian ingest đã đo. Chênh lệch B–C khoảng 0,049 giây rất nhỏ, không chứng minh ưu thế hiệu năng tổng quát.
- A–B: B có thêm 5 câu dev đạt Evidence Hit@3, đổi lại ingest lâu hơn và số chunk tăng từ 212 lên 240. Coherence trên 10 vị trí đầu trang là A = 1,00/2, B = 0,90/2; cách chia theo cấu trúc chưa cải thiện trên mẫu này. B có các chunk chỉ chứa credit hình, mảnh `output)` hoặc đáp án thiếu câu hỏi ở trang 17/24/25.
- B–C: filter chưa làm tăng hit trên 2 câu dev có filter. Với q04, B trả các trang 70/65/66 thuộc chương 2; C chuyển sang trang 33/17/31 thuộc chương 1 theo input, nhưng vẫn thiếu gold trang 24. Filter giúp giữ phạm vi mà chưa bảo đảm lấy đúng evidence.
- Ví dụ lỗi q14/A: top-1 và top-3 có trang 59 nhưng chunk chỉ chứa một phần nội dung về phép chia, thiếu toàn bộ evidence so sánh `/`, `//`, `%`. B lấy đủ evidence ở top-1 trang 59.
- Ví dụ lỗi q12/B: top-3 ở trang 52/50/47, thiếu gold trang 51 giải thích `int(5.9)` loại phần thập phân. C cũng chưa khắc phục được vì các kết quả này đã nằm trong chương 2.
- Trên test, A có Hit@1 = 3/5, B/C = 2/5; Evidence Hit@3 đều 3/5. Khác biệt Hit@1 nằm ở q18: A lấy đủ evidence trang 57 tại top-1, B/C lấy tại top-2. Giữ lựa chọn B từ dev, không đổi cấu hình theo test.
- Ví dụ lỗi test q19/B: top-1 đúng trang 70 nhưng chỉ chứa các lựa chọn `Hello,Ada`, `Hello, Ada`, `SyntaxError`, không chứa evidence về implicit line joining. C lọc đúng chương 2 nhưng vẫn không tìm đủ evidence trong top-3.
- Metadata đủ/đúng đạt 15/15 ở cả ba cấu hình, nhưng metadata đúng không bảo đảm nội dung hữu ích. Chapter giúp C giữ đúng phạm vi 2/2 câu test có yêu cầu; không giải quyết được việc thiếu evidence trong chunk.
- Grounding A/C = 1,40/2, B = 1,20/2. Ở q19, C có learning objective trang 67 nhắc implicit line joining nên được mức 1, nhưng thiếu dấu ngoặc đơn; B không có evidence về cơ chế nên mức 0. Phân biệt này không làm thay đổi Evidence Hit@3 vì vẫn chưa đủ để trả lời toàn bộ câu hỏi.
- Kết luận: giữ B theo tiêu chí ưu tiên retrieval trên dev; B không tốt hơn trên mọi khía cạnh. Các nhãn audit không được dùng để điều chỉnh cấu hình sau khi xem test.
- Giới hạn: 15 câu dev và 5 câu test là mẫu nhỏ, query tiếng Việt/corpus tiếng Anh, ranh giới chunk theo heuristic và phép so khớp evidence tự động có thể bỏ sót bằng chứng tương đương. Mẫu coherence đầu trang chưa đại diện toàn corpus; nhãn có AI hỗ trợ và chỉ một học viên xác nhận. Chưa đánh giá độ chính xác câu trả lời LLM.
- Nếu làm lại: bổ sung ngữ cảnh khi nối trang, tránh chunk chỉ có credit/đáp án rời và lấy mẫu coherence đa dạng hơn. Thử trên dev và bộ test độc lập mới; giữ nguyên cấu hình/kết quả test hiện tại.

