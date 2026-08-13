# EduCheck AI

Ứng dụng Streamlit dùng các model OpenAI chi phí thấp để kiểm tra một bộ học liệu gồm bốn vai trò:

1. **Giáo án**: kế hoạch, mục tiêu và phạm vi bài học.
2. **Tài liệu giảng dạy**: slideshow, handout hoặc tài liệu thực tế đã dùng trên lớp;
   có thể tải nhiều file.
3. **Bài tập học viên**: homework, worksheet hoặc bài kiểm tra cần rà soát.
4. **Đáp án**: đáp án chính thức hoặc hướng dẫn chấm.

AI đọc giáo án và tài liệu giảng dạy trước, sau đó tự giải bài tập khi chưa được xem
đáp án. Sau lượt giải độc lập, file đáp án được trích xuất và trở thành nguồn chuẩn do
giáo viên cung cấp cho các bước kiểm tra còn lại. Cách tách này vừa giảm nguy cơ AI bị
đáp án dẫn dắt khi tự giải, vừa ngăn AI tự kết luận đáp án giáo viên sai.

Mặc định ứng dụng dùng **Kiểm tra nhanh**: xác định đúng Unit/Part/Section của bài tập,
chỉ lấy phần đáp án tương ứng, tự giải độc lập và đối chiếu. Các cặp đáp án trùng chính
xác được kiểm tra bằng quy tắc xác định. Nếu AI trả lời khác, kết quả chỉ được ghi là
“AI chưa đồng thuận”, không tính là lỗi học liệu. Mục chưa trích xuất được đáp án được
ghi là lỗi đọc/ghép cần xác minh, không tự động kết luận file thiếu đáp án.
Chọn **Phân tích toàn diện** khi cần rà thêm tiếng Anh và chất lượng đề. Ứng dụng không
kiểm tra chính tả, ngữ pháp hoặc cách diễn đạt tiếng Việt. Giáo án và tài liệu dạy không
đổi được tái sử dụng trong cùng phiên chạy.
GPT-5 nano đọc và trích xuất; GPT-5 mini tự giải và xác minh những nhóm đối chiếu chưa
thể kết luận bằng quy tắc chắc chắn.

Ứng dụng dành cho một người dùng, không đăng nhập, không dùng cơ sở dữ liệu và
không lưu tài liệu hay lịch sử phân tích trên máy chủ ứng dụng. Mọi request Responses
API đều đặt `store=False`; dữ liệu vẫn chịu chính sách abuse-monitoring của tài khoản
OpenAI, trừ khi tổ chức được bật Zero Data Retention.

## Yêu cầu

- Python 3.12 trở lên
- OpenAI API key

## Cài đặt trên Windows

### Chạy nhanh

Double-click file `run.bat`. Lần đầu chạy, file sẽ tự tạo môi trường Python,
cài thư viện và mở `.env` để nhập `OPENAI_API_KEY`. Các lần sau chỉ cần
double-click `run.bat`.

### Cài đặt thủ công

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Mở `.env` và cấu hình tối thiểu:

```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5-nano
OPENAI_SOLVING_MODEL=gpt-5-mini
OPENAI_ESCALATION_MODEL=gpt-5-mini
OPENAI_REASONING_EFFORT=minimal
OPENAI_SOLVING_REASONING_EFFORT=low
OPENAI_ESCALATION_REASONING_EFFORT=low
OPENAI_TEXT_VERBOSITY=low
```

Chạy ứng dụng:

```powershell
streamlit run app.py
```

Chạy kiểm thử:

```powershell
pytest
```

## Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---:|---|
| `OPENAI_API_KEY` | trống | API key bắt buộc khi phân tích |
| `OPENAI_MODEL` | `gpt-5-nano` | Model đọc và trích xuất |
| `OPENAI_SOLVING_MODEL` | `gpt-5-mini` | Model tự giải bài tập |
| `OPENAI_ESCALATION_MODEL` | `gpt-5-mini` | Model xác minh trường hợp chưa kết luận |
| `OPENAI_REASONING_EFFORT` | `minimal` | Mức suy luận cho đọc/trích xuất |
| `OPENAI_SOLVING_REASONING_EFFORT` | `low` | Mức suy luận khi tự giải bài tập |
| `OPENAI_ESCALATION_REASONING_EFFORT` | `low` | Mức suy luận khi xác minh |
| `OPENAI_TEXT_VERBOSITY` | `low` | Độ dài đầu ra AI: `low`, `medium`, `high` |
| `MAX_FILE_SIZE_MB` | `30` | Dung lượng tối đa |
| `MAX_TEACHING_FILES` | `6` | Số tài liệu giảng dạy tối đa |
| `MAX_PACKAGE_SIZE_MB` | `100` | Tổng dung lượng tối đa của cả bộ |
| `MAX_PDF_PAGES` | `150` | Số trang PDF tối đa |
| `PDF_PAGES_PER_CHUNK` | `10` | Số trang mỗi phần với PDF trên 25 trang |
| `DOCX_CHARS_PER_CHUNK` | `30000` | Ngưỡng ký tự mỗi phần Word |
| `COMPARISON_BATCH_SIZE` | `40` | Số bản ghi câu hỏi/đáp án tối đa mỗi lượt đối chiếu |
| `SOLVING_BATCH_SIZE` | `12` | Số câu tối đa trong một lượt tự giải |
| `RETRIEVAL_TOP_K` | `4` | Số đoạn dẫn chứng tối đa truy xuất cho mỗi câu |
| `RETRIEVAL_MAX_CHARS_PER_QUESTION` | `5000` | Tổng ký tự dẫn chứng tối đa cho mỗi câu |
| `MAX_EXTRACTED_QUESTIONS` | `200` | Tổng số câu hỏi tối đa trong một bài tập |
| `MAX_OUTPUT_TOKENS` | `8000` | Trần token đầu ra cho mỗi request OpenAI |
| `AI_MAX_RETRIES` | `1` | Số lần thử lại khi lỗi/schema không hợp lệ |
| `AI_TIMEOUT_SECONDS` | `180` | Thời gian chờ API |

## Luồng xử lý

1. Chuẩn hóa bốn vai trò DOCX/PDF nhưng luôn giữ số trang, `block_id` và tên nguồn.
2. Xây dựng `LessonPlanProfile` và `TeachingContextProfile` để phân biệt nội dung dự kiến
   với nội dung thực tế đã dạy.
3. GPT-5 nano chỉ tách cấu trúc câu hỏi; chưa tự giải và không nhận dữ liệu đáp án.
4. Code truy xuất các đoạn giáo án/slide/handout liên quan cho từng câu, gắn `evidence_id`;
   không dùng embeddings hoặc gọi thêm API.
5. Gom tối đa `SOLVING_BATCH_SIZE` câu mỗi lượt để GPT-5 mini tự giải độc lập từ các
   dẫn chứng đã truy xuất.
6. Trích xuất riêng phần đáp án cùng Unit/Part/Section thành `AnswerKeyProfile`.
7. Đối chiếu bằng quy tắc trước; phân biệt rõ `AI chưa đồng thuận`, lỗi đọc/ghép đáp án,
   nội dung chưa rõ, ngoài phạm vi và khác phiên bản. Chỉ dữ liệu có căn cứ mới được
   coi là vấn đề cần giáo viên xác minh.
8. Chỉ gửi các nhóm confidence thấp, câu AI giải khác đáp án, trùng số hoặc có dấu hiệu lệch
   phiên bản sang lượt xác minh hai.
9. Ở chế độ toàn diện, rà thêm tiếng Anh, đề bài và độ phù hợp sau khi đã nhận đáp án chính
   thức; không kiểm tra tiếng Việt và nhận xét thuần sở thích diễn đạt hoặc trình bày bị loại.
10. Xuất DOCX/JSON ngắn gọn, có tên file, trang/block, `evidence_id`, lời giải độc lập,
    đáp án chính thức và kết quả đối chiếu.

Ứng dụng ghi token, model, reasoning và chi phí ước tính theo từng công đoạn. PDF có
văn bản được gửi dưới dạng text kèm số trang; chỉ PDF scan mới dùng hình ảnh chất lượng
cao, còn PDF có hình nhưng vẫn có text dùng mức chi tiết thấp để giảm chi phí.

## Giới hạn

- Kết quả AI có thể chưa chính xác; nội dung chuyên môn cần giáo viên xác minh.
- Luồng bốn vai trò cần nhiều lượt gọi API hơn luồng kiểm tra một file.
- Ảnh và đối tượng nhúng trong Word không được phân tích đầy đủ ở MVP.
- PDF scan có thể làm vị trí lỗi kém chính xác.
- Ứng dụng không chỉnh sửa trực tiếp tài liệu gốc và không lưu lịch sử.
- Không có OCR riêng; PDF scan được gửi trực tiếp cho khả năng đọc tài liệu của model.
- `ai_disagreement` chỉ thể hiện AI trả lời khác đáp án giáo viên và không được tính là lỗi.
- `key_extraction_uncertain`, `ambiguous`, `conflict`, `missing_key` và
  `version_mismatch` cần giáo viên xem lại; giao diện không tự kết luận “cần chỉnh sửa”.
