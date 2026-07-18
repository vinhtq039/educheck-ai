# KẾ HOẠCH XÂY DỰNG TOOL AI KIỂM TRA HỌC LIỆU WORD VÀ PDF

## 1. Mục tiêu dự án

Xây dựng một web tool cá nhân cho một người sử dụng, cho phép tải lên một tài liệu học liệu định dạng:

* `.docx`
* `.pdf`

Tool sử dụng AI để:

* Kiểm tra lỗi chính tả tiếng Việt.
* Kiểm tra lỗi ngữ pháp tiếng Việt.
* Kiểm tra lỗi chính tả tiếng Anh.
* Kiểm tra lỗi ngữ pháp tiếng Anh.
* Phát hiện câu văn khó hiểu hoặc diễn đạt chưa tự nhiên.
* Phát hiện đề bài mơ hồ.
* Phát hiện đề bài thiếu dữ kiện.
* Phát hiện dữ kiện mâu thuẫn.
* Kiểm tra câu hỏi và đáp án.
* Phát hiện đáp án có khả năng sai.
* Phát hiện câu hỏi có nhiều đáp án đúng hoặc không có đáp án đúng.
* Đánh giá câu hỏi có phù hợp với môn học, khối lớp, chủ đề và mục tiêu bài học không.
* Đề xuất cách sửa.
* Đề xuất câu hỏi thay thế khi câu hỏi hiện tại không phù hợp.

Tool chỉ phân tích tài liệu hiện tại. Khi người dùng chọn tài liệu khác, toàn bộ kết quả cũ được xóa và phân tích lại từ đầu.

---

## 2. Giới hạn phạm vi

### Bắt buộc có

* Chỉ có một người dùng.
* Không cần đăng nhập.
* Không cần đăng ký.
* Không cần phân quyền.
* Không cần cơ sở dữ liệu.
* Không lưu lịch sử tài liệu.
* Không lưu lịch sử phân tích.
* Chỉ hỗ trợ PDF và DOCX.
* Mỗi lần chỉ phân tích một file.
* Kết quả chỉ tồn tại trong phiên làm việc hiện tại.
* Có nút xóa kết quả và phân tích tài liệu khác.
* File tạm phải được xóa sau khi xử lý hoặc khi xảy ra lỗi.

### Không làm trong phiên bản đầu

* Không hỗ trợ `.doc` cũ.
* Không hỗ trợ Excel.
* Không hỗ trợ PowerPoint.
* Không hỗ trợ nhiều người dùng.
* Không có dashboard quản trị.
* Không có thanh toán.
* Không có gói dịch vụ.
* Không chỉnh sửa trực tiếp nội dung tài liệu gốc.
* Không tự động ghi đè file người dùng.
* Không cần lưu tài liệu trên cloud.
* Không xây hệ thống RAG hoặc vector database.
* Không cần Redis.
* Không cần PostgreSQL, MySQL hoặc SQLite.
* Không cần frontend React riêng.
* Không cần backend API riêng.

---

## 3. Công nghệ sử dụng

### Ngôn ngữ

* Python 3.12 trở lên.

### Giao diện

* Streamlit.

### AI

* OpenAI Responses API.
* SDK chính thức: `openai`.
* Model mặc định: `gpt-5.6-sol`.
* Kết quả AI phải trả về Structured Output theo JSON Schema, không xử lý bằng cách cắt chuỗi JSON thủ công.

GPT-5.6 Sol hỗ trợ PDF, đầu vào đa phương thức và Structured Outputs.

### Đọc PDF

* PyMuPDF, import bằng `pymupdf`.

Sử dụng PyMuPDF để:

* Đếm số trang.
* Trích xuất văn bản theo từng trang.
* Trích xuất block văn bản.
* Lưu số trang tương ứng với nội dung.
* Phát hiện PDF có rất ít văn bản, có khả năng là PDF scan.
* Tạo các file PDF nhỏ theo nhóm trang khi tài liệu dài.

PyMuPDF có thể trích xuất word/block cùng tọa độ và hỗ trợ sắp xếp lại thứ tự đọc bằng `sort=True`.

### Đọc và tạo Word

* `python-docx`.

Sử dụng để:

* Đọc paragraph.
* Đọc heading.
* Đọc bảng.
* Tạo báo cáo kết quả dạng DOCX.

`python-docx` hỗ trợ mở và thao tác với tài liệu DOCX.

### Kiểm tra schema

* Pydantic.

### Cấu hình môi trường

* `python-dotenv`.

### Kiểm thử

* `pytest`.

---

## 4. Kiến trúc tổng thể

```text
Người dùng
    ↓
Streamlit UI
    ↓
Kiểm tra file đầu vào
    ↓
Document Parser
    ├── PDF Parser
    └── DOCX Parser
    ↓
Chuẩn hóa nội dung
    ↓
Chia nội dung thành các phần nhỏ
    ↓
OpenAI Analysis Service
    ↓
Kiểm tra JSON bằng Pydantic
    ↓
Gộp và loại bỏ lỗi trùng
    ↓
Hiển thị kết quả
    ↓
Tải báo cáo DOCX hoặc JSON
```

Không sử dụng database.

Trạng thái tạm thời được lưu bằng `st.session_state`.

---

## 5. Cấu trúc thư mục

Tạo project theo cấu trúc:

```text
learning-material-checker/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
│
├── config/
│   ├── __init__.py
│   └── settings.py
│
├── schemas/
│   ├── __init__.py
│   ├── analysis.py
│   └── document.py
│
├── services/
│   ├── __init__.py
│   ├── document_service.py
│   ├── pdf_parser.py
│   ├── docx_parser.py
│   ├── chunk_service.py
│   ├── openai_service.py
│   ├── analysis_service.py
│   ├── result_merge_service.py
│   ├── report_service.py
│   └── cleanup_service.py
│
├── prompts/
│   ├── system_prompt.py
│   ├── document_analysis_prompt.py
│   └── summary_prompt.py
│
├── utils/
│   ├── __init__.py
│   ├── file_utils.py
│   ├── text_utils.py
│   └── validators.py
│
└── tests/
    ├── test_pdf_parser.py
    ├── test_docx_parser.py
    ├── test_result_merge.py
    └── test_validators.py
```

Không tạo thêm microservice hoặc project frontend riêng.

---

## 6. Biến môi trường

Tạo file `.env.example`:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-sol
OPENAI_REASONING_EFFORT=medium
MAX_FILE_SIZE_MB=30
MAX_PDF_PAGES=150
PDF_PAGES_PER_CHUNK=10
DOCX_CHARS_PER_CHUNK=30000
AI_MAX_RETRIES=2
AI_TIMEOUT_SECONDS=180
```

Không hard-code API key trong source code.

File `.env` phải nằm trong `.gitignore`.

---

## 7. Giao diện chính

Tool chỉ cần một trang.

### 7.1. Tiêu đề

```text
AI kiểm tra học liệu
Kiểm tra lỗi ngôn ngữ, đề bài, câu hỏi và đáp án trong tài liệu Word/PDF.
```

### 7.2. Khu vực tải file

Dùng:

```python
st.file_uploader(
    "Tải tài liệu Word hoặc PDF",
    type=["pdf", "docx"],
    accept_multiple_files=False
)
```

Kiểm tra:

* Chỉ nhận `.pdf` và `.docx`.
* Chỉ nhận một file.
* Không nhận file rỗng.
* Giới hạn dung lượng theo cấu hình.
* Không chỉ kiểm tra extension; cần kiểm tra định dạng thực tế ở mức cơ bản.
* Hiển thị tên file và dung lượng.

Streamlit lưu file upload trong bộ nhớ backend trong phiên ứng dụng; chỉ ghi file xuống thư mục tạm khi thư viện hoặc API cần đường dẫn vật lý.

### 7.3. Thông tin bổ sung

Các trường:

* Môn học: text input.
* Khối lớp: text input.
* Chủ đề bài học: text input.
* Mục tiêu bài học: text area.
* Yêu cầu kiểm tra riêng: text area.

Chỉ file là bắt buộc. Các trường còn lại có thể để trống.

Ví dụ yêu cầu riêng:

```text
Kiểm tra xem câu hỏi có phù hợp với học sinh lớp 6 không.
Chú ý các câu hỏi về thì hiện tại đơn.
```

### 7.4. Các loại kiểm tra

Hiển thị checkbox:

* Chính tả tiếng Việt.
* Ngữ pháp và diễn đạt tiếng Việt.
* Chính tả tiếng Anh.
* Ngữ pháp và diễn đạt tiếng Anh.
* Kiểm tra đề bài.
* Kiểm tra câu hỏi và đáp án.
* Kiểm tra mức độ phù hợp.
* Đề xuất câu hỏi thay thế.

Mặc định chọn tất cả.

### 7.5. Nút hành động

* `Bắt đầu phân tích`
* `Xóa kết quả`
* `Phân tích tài liệu khác`

Không tự động gọi AI ngay khi tải file. Chỉ gọi khi người dùng bấm `Bắt đầu phân tích`.

---

## 8. Trạng thái giao diện

Sử dụng `st.session_state` với các khóa:

```python
uploaded_file_hash
analysis_status
analysis_result
analysis_error
current_file_name
```

Các trạng thái:

```text
IDLE
VALIDATING
EXTRACTING
ANALYZING
MERGING
COMPLETED
FAILED
```

Khi tải file mới có hash khác:

* Xóa kết quả cũ.
* Đặt trạng thái về `IDLE`.
* Không hiển thị kết quả của file trước.

Khi nhấn `Phân tích tài liệu khác`:

* Xóa toàn bộ session state liên quan.
* Xóa file tạm.
* Chạy `st.rerun()`.

---

## 9. Xử lý PDF

### 9.1. Kiểm tra PDF

Kiểm tra:

* File mở được bằng PyMuPDF.
* Không bị hỏng.
* Không được mã hóa hoặc yêu cầu mật khẩu.
* Không vượt quá số trang cấu hình.
* Có ít nhất một trang.

Nếu PDF cần mật khẩu, hiển thị:

```text
Tài liệu PDF đang được bảo vệ bằng mật khẩu. Vui lòng bỏ mật khẩu rồi tải lại.
```

### 9.2. Trích xuất

Với mỗi trang, lấy:

```python
{
    "page_number": 1,
    "text": "...",
    "blocks": [
        {
            "text": "...",
            "bbox": [x0, y0, x1, y1]
        }
    ]
}
```

Sử dụng:

```python
page.get_text("blocks", sort=True)
```

Chuẩn hóa:

* Loại bỏ header/footer lặp lại nếu phát hiện rõ ràng.
* Không xóa số câu hỏi.
* Không xóa ký hiệu A, B, C, D.
* Không tự sửa nội dung trước khi gửi AI.
* Giữ số trang.

### 9.3. Phát hiện PDF scan

Tính số ký tự trích xuất trung bình trên mỗi trang.

Nếu phần lớn trang có rất ít hoặc không có văn bản:

```text
is_scanned_pdf = True
```

Không tự kết luận file lỗi.

Hiển thị cảnh báo:

```text
Tài liệu có thể là PDF scan. AI sẽ phân tích trực tiếp nội dung hiển thị trên trang, nhưng vị trí lỗi có thể không chính xác tuyệt đối.
```

### 9.4. Gửi PDF cho OpenAI

Với PDF, gửi cả:

* File PDF hoặc PDF chunk.
* Metadata người dùng nhập.
* Yêu cầu phân tích.
* Schema kết quả.

Không chỉ gửi plain text vì cần giữ ngữ cảnh bố cục, bảng và hình ảnh. GPT-5.6 Sol hỗ trợ phân tích PDF theo ngữ cảnh tài liệu và khả năng nhìn nội dung trên trang.

### 9.5. Chia PDF

Quy tắc:

* Từ 1 đến 25 trang: có thể phân tích trong một lần.
* Trên 25 trang: chia thành các PDF nhỏ, mặc định 10 trang mỗi chunk.
* Tên file tạm không chứa trực tiếp tên file người dùng.
* Mỗi chunk phải biết:

  * Trang bắt đầu.
  * Trang kết thúc.
  * Offset số trang gốc.

Ví dụ:

```python
{
    "chunk_index": 2,
    "start_page": 11,
    "end_page": 20,
    "page_offset": 10
}
```

Sau khi AI trả kết quả, chuyển số trang trong chunk về số trang tài liệu gốc.

---

## 10. Xử lý DOCX

### 10.1. Nội dung cần đọc

Đọc theo đúng thứ tự:

* Paragraph.
* Heading.
* List.
* Table.

Không chỉ đọc `document.paragraphs` rồi đọc bảng sau cùng vì cách đó làm sai thứ tự nội dung.

Viết hàm duyệt XML body để trả paragraph và table theo thứ tự xuất hiện.

### 10.2. Dữ liệu chuẩn hóa

Mỗi block có dạng:

```python
{
    "block_id": "block-0012",
    "block_type": "paragraph",
    "section_title": "Bài tập 2",
    "text": "Nội dung...",
    "order": 12
}
```

Với bảng:

```python
{
    "block_id": "block-0013",
    "block_type": "table",
    "section_title": "Bài tập 2",
    "rows": [
        ["Câu hỏi", "Đáp án"],
        ["...", "..."]
    ],
    "text": "Câu hỏi | Đáp án\n..."
}
```

Giữ lại:

* Heading gần nhất.
* Số thứ tự block.
* Số câu hỏi nếu nhận diện được.
* Nội dung bảng.

### 10.3. Hình ảnh trong DOCX

Trong MVP:

* Không bắt buộc phân tích toàn bộ ảnh nhúng trong Word.
* Nếu tài liệu có nhiều ảnh hoặc câu hỏi phụ thuộc vào hình, hiển thị cảnh báo.
* Không tự kết luận thiếu hình nếu parser không đọc được ảnh.
* Có thể bổ sung chuyển DOCX sang PDF ở giai đoạn sau.

Cảnh báo:

```text
Tài liệu Word có thể chứa hình ảnh hoặc đối tượng không được trích xuất đầy đủ. Các câu hỏi phụ thuộc vào hình cần được kiểm tra lại.
```

### 10.4. Chia DOCX

Chia theo:

1. Heading.
2. Nhóm câu hỏi.
3. Giới hạn số ký tự.

Không cắt giữa một câu hỏi và các phương án A/B/C/D nếu có thể tránh.

Mỗi chunk cần có:

```python
{
    "chunk_index": 1,
    "start_block": 1,
    "end_block": 30,
    "content": "..."
}
```

---

## 11. Schema kết quả AI

Tạo các enum:

```python
class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"
```

```python
class IssueCategory(str, Enum):
    VIETNAMESE_SPELLING = "vietnamese_spelling"
    VIETNAMESE_GRAMMAR = "vietnamese_grammar"
    VIETNAMESE_EXPRESSION = "vietnamese_expression"

    ENGLISH_SPELLING = "english_spelling"
    ENGLISH_GRAMMAR = "english_grammar"
    ENGLISH_EXPRESSION = "english_expression"

    AMBIGUOUS_QUESTION = "ambiguous_question"
    MISSING_INFORMATION = "missing_information"
    CONFLICTING_INFORMATION = "conflicting_information"

    INCORRECT_ANSWER = "incorrect_answer"
    NO_CORRECT_ANSWER = "no_correct_answer"
    MULTIPLE_CORRECT_ANSWERS = "multiple_correct_answers"
    DUPLICATE_QUESTION = "duplicate_question"
    DUPLICATE_OPTION = "duplicate_option"
    QUESTION_ANSWER_MISMATCH = "question_answer_mismatch"

    OUT_OF_SCOPE = "out_of_scope"
    GRADE_LEVEL_MISMATCH = "grade_level_mismatch"
    LEARNING_OBJECTIVE_MISMATCH = "learning_objective_mismatch"

    UNCERTAIN_CONTENT = "uncertain_content"
```

Tạo model lỗi:

```python
class AnalysisIssue(BaseModel):
    issue_id: str
    category: IssueCategory
    severity: IssueSeverity

    page_number: int | None = None
    block_id: str | None = None
    section_title: str | None = None
    question_number: str | None = None

    original_text: str
    explanation: str
    suggested_text: str | None = None

    replacement_question: str | None = None
    suggested_answer: str | None = None

    confidence: float = Field(ge=0, le=1)
    requires_human_review: bool = False
```

Tạo model tổng:

```python
class DocumentSummary(BaseModel):
    document_type: str
    detected_languages: list[str]
    detected_subject: str | None = None
    detected_grade_level: str | None = None
    total_questions: int | None = None
    summary: str
```

```python
class AnalysisResult(BaseModel):
    document_summary: DocumentSummary
    issues: list[AnalysisIssue]
    general_recommendations: list[str]
    limitations: list[str]
```

Không cho phép AI trả thêm markdown bên ngoài JSON.

---

## 12. Nguyên tắc prompt AI

System prompt phải yêu cầu AI:

1. Đóng vai trò trợ lý kiểm tra học liệu.
2. Phân tích tiếng Việt và tiếng Anh.
3. Không tự ý viết lại toàn bộ tài liệu.
4. Chỉ báo lỗi khi có lý do cụ thể.
5. Không biến mọi khác biệt về văn phong thành lỗi.
6. Phân biệt:

   * Lỗi chắc chắn.
   * Nội dung cần xem xét.
   * Gợi ý cải thiện.
7. Không khẳng định kiến thức chuyên môn sai nếu không đủ dữ kiện.
8. Khi không chắc chắn:

   * Đặt `requires_human_review = true`.
   * Giảm confidence.
   * Dùng giải thích trung lập.
9. Không tạo nội dung không có trong tài liệu rồi nói rằng tài liệu có nội dung đó.
10. Không đánh giá phạm vi khối lớp nếu người dùng không nhập khối lớp và tài liệu không cung cấp đủ thông tin.
11. Không nhận xét câu hỏi ngoài chủ đề nếu chủ đề chưa được cung cấp hoặc không thể suy ra.
12. Luôn trích lại đúng đoạn gốc trong `original_text`.
13. Đề xuất sửa phải giữ nguyên ý nghĩa ban đầu, trừ trường hợp câu hỏi ban đầu sai hoặc không phù hợp.
14. Câu hỏi thay thế phải:

    * Phù hợp môn học.
    * Phù hợp khối lớp.
    * Bám chủ đề.
    * Có đáp án gợi ý khi có thể.
15. Trả đúng JSON Schema.

---

## 13. Nội dung kiểm tra chi tiết

### 13.1. Tiếng Việt

Kiểm tra:

* Chính tả.
* Dấu câu.
* Viết hoa.
* Khoảng trắng.
* Lặp từ.
* Sai cấu trúc câu.
* Câu thiếu thành phần.
* Dùng từ không phù hợp.
* Diễn đạt khó hiểu.
* Thuật ngữ không thống nhất.
* Cách xưng hô không thống nhất.

Không báo lỗi với:

* Tên riêng hợp lệ.
* Thuật ngữ chuyên môn.
* Cách viết cố ý trong ví dụ.
* Câu sai được đưa vào bài tập để học sinh sửa, trừ khi đáp án cũng sai.

### 13.2. Tiếng Anh

Kiểm tra:

* Spelling.
* Grammar.
* Subject–verb agreement.
* Tense.
* Article.
* Preposition.
* Singular/plural.
* Word order.
* Capitalization.
* Punctuation.
* Natural expression.

Phải phân biệt:

* Câu tiếng Anh sai do lỗi tài liệu.
* Câu tiếng Anh cố ý sai vì là bài tập tìm lỗi.
* Phương án nhiễu cố ý trong câu trắc nghiệm.

Không báo từng phương án nhiễu là lỗi nếu đó là thiết kế hợp lệ của câu hỏi.

### 13.3. Đề bài

Kiểm tra:

* Yêu cầu không rõ.
* Thiếu đối tượng cần thực hiện.
* Thiếu dữ kiện.
* Nhắc đến hình hoặc đoạn văn không tồn tại.
* Dữ kiện tự mâu thuẫn.
* Câu hỏi không thể trả lời từ dữ liệu đã cho.
* Yêu cầu một đáp án nhưng có thể có nhiều cách hiểu.

### 13.4. Câu hỏi và đáp án

Kiểm tra:

* Đáp án được đánh dấu có khả năng sai.
* Không có phương án đúng.
* Có nhiều phương án đúng ngoài ý muốn.
* Phương án trùng nhau.
* Câu hỏi trùng nhau.
* Câu hỏi và đáp án không khớp.
* Đáp án sử dụng dữ kiện không có trong đề.
* Câu hỏi yêu cầu chọn một nhưng nội dung cho phép chọn nhiều.

Không khẳng định đáp án sai chỉ dựa trên suy đoán yếu.

### 13.5. Phù hợp học liệu

Chỉ kiểm tra khi có đủ thông tin:

* Môn học.
* Khối lớp.
* Chủ đề.
* Mục tiêu bài học.

Đánh giá:

* Có đúng chủ đề không.
* Có vượt quá trình độ không.
* Có quá đơn giản không.
* Có kiểm tra đúng mục tiêu không.
* Ngôn ngữ có phù hợp lứa tuổi không.

---

## 14. Chiến lược gọi AI

### Tài liệu ngắn

Với tài liệu nhỏ:

* Thực hiện một lần phân tích chính.
* Validate bằng Pydantic.
* Nếu JSON không hợp lệ, retry tối đa hai lần.

### Tài liệu dài

Với nhiều chunk:

1. Phân tích từng chunk.
2. Validate từng kết quả.
3. Gộp lỗi.
4. Loại bỏ lỗi trùng.
5. Sắp xếp theo trang hoặc block.
6. Có thể gọi thêm một lượt tổng hợp nhẹ để tìm:

   * Câu hỏi trùng giữa các chunk.
   * Thuật ngữ không thống nhất.
   * Dữ kiện mâu thuẫn toàn tài liệu.

Không gửi lại toàn bộ nội dung tài liệu trong bước tổng hợp. Chỉ gửi:

* Summary từng chunk.
* Danh sách lỗi đã phát hiện.
* Danh sách câu hỏi hoặc thuật ngữ cần đối chiếu.

---

## 15. Gộp và loại bỏ lỗi trùng

Hai lỗi được xem là có khả năng trùng khi:

* Cùng category.
* Cùng page hoặc block.
* `original_text` giống hoặc gần giống.
* Giải thích có cùng ý nghĩa.

Ưu tiên giữ lỗi:

1. Confidence cao hơn.
2. Có vị trí cụ thể hơn.
3. Có đề xuất sửa rõ ràng hơn.
4. Có severity nghiêm trọng hơn nếu cùng một vấn đề.

Không gộp hai lỗi khác loại chỉ vì nằm cùng một câu.

Sắp xếp:

1. Critical.
2. Warning.
3. Suggestion.
4. Theo số trang hoặc block.

---

## 16. Hiển thị kết quả

### 16.1. Tổng quan

Hiển thị:

* Tên tài liệu.
* Loại tài liệu.
* Ngôn ngữ phát hiện.
* Tổng số câu hỏi nếu xác định được.
* Tổng số vấn đề.
* Số lỗi critical.
* Số warning.
* Số suggestion.
* Tóm tắt chung.

### 16.2. Bộ lọc

Cho phép lọc theo:

* Mức độ.
* Nhóm lỗi.
* Trang.
* Từ khóa.
* Chỉ hiển thị lỗi cần người dùng kiểm tra lại.

### 16.3. Thẻ lỗi

Mỗi lỗi hiển thị:

```text
Trang hoặc phần
Câu số
Loại lỗi
Mức độ
Độ tin cậy

Nội dung gốc
Giải thích
Đề xuất sửa
Câu hỏi thay thế
Đáp án gợi ý
Cần người dùng xác minh hay không
```

Dùng `st.expander` cho từng lỗi để giao diện không quá dài.

Không cần chức năng chấp nhận hoặc từ chối lỗi vì không lưu trạng thái.

---

## 17. Xuất báo cáo

Cho phép tải xuống:

### Báo cáo DOCX

Báo cáo gồm:

1. Tên tài liệu.
2. Thời điểm phân tích.
3. Thông tin môn học, khối lớp và chủ đề.
4. Tóm tắt.
5. Thống kê lỗi.
6. Danh sách lỗi theo thứ tự.
7. Đề xuất chung.
8. Giới hạn của kết quả AI.

### Báo cáo JSON

Dùng chính kết quả đã được Pydantic validate.

Tên file:

```text
<ten-file>-analysis-report.docx
<ten-file>-analysis-result.json
```

Không lưu báo cáo trên server sau khi người dùng tải.

---

## 18. Quản lý file tạm

Sử dụng `tempfile.TemporaryDirectory`.

Luồng:

```python
with TemporaryDirectory() as temp_dir:
    # lưu file tạm
    # tạo PDF chunk nếu cần
    # gọi AI
    # tạo kết quả
# tự động xóa khi thoát context
```

Ngoài ra:

* Dùng `try/finally`.
* Không dùng tên file gốc trực tiếp làm đường dẫn.
* Tạo UUID cho file tạm.
* Không ghi nội dung tài liệu vào log.
* Không log API key.
* Không lưu response đầy đủ vào file ngoài chế độ debug.
* Chế độ debug mặc định tắt.

---

## 19. Xử lý lỗi

Tạo thông báo thân thiện cho các trường hợp:

### File không hợp lệ

```text
File không đúng định dạng PDF hoặc DOCX.
```

### File quá lớn

```text
Tài liệu vượt quá dung lượng cho phép.
```

### PDF hỏng

```text
Không thể đọc tài liệu PDF. File có thể bị hỏng.
```

### PDF có mật khẩu

```text
PDF đang được bảo vệ bằng mật khẩu.
```

### Word hỏng

```text
Không thể đọc tài liệu Word. File có thể bị hỏng hoặc không đúng định dạng DOCX.
```

### Không trích xuất được nội dung

```text
Không tìm thấy đủ nội dung để phân tích.
```

### Thiếu API key

```text
Chưa cấu hình OPENAI_API_KEY.
```

### Hết quota

```text
Không thể gọi AI do đã vượt giới hạn sử dụng API. Vui lòng kiểm tra quota OpenAI.
```

### AI trả sai schema

* Retry tối đa theo cấu hình.
* Nếu vẫn sai, hiển thị lỗi.
* Không cố parse bằng regex nguy hiểm.
* Không hiển thị traceback cho người dùng.

---

## 20. Progress khi phân tích

Hiển thị tiến trình:

```text
1. Đang kiểm tra tài liệu
2. Đang trích xuất nội dung
3. Đang chia tài liệu
4. Đang phân tích phần 1/4
5. Đang phân tích phần 2/4
6. Đang tổng hợp kết quả
7. Hoàn tất
```

Sử dụng:

* `st.status`
* `st.progress`
* Placeholder trạng thái.

Không hiển thị thời gian hoàn thành giả.

---

## 21. README

README cần có:

### Giới thiệu

Tool dùng AI kiểm tra học liệu Word và PDF.

### Yêu cầu

* Python 3.12+
* OpenAI API key.

### Cài đặt

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Cài thư viện:

```bash
pip install -r requirements.txt
```

Tạo `.env`:

```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5.6-sol
OPENAI_REASONING_EFFORT=medium
```

Chạy:

```bash
streamlit run app.py
```

### Giới hạn

* AI có thể nhận xét chưa chính xác.
* Câu hỏi chuyên môn cần người dùng xác minh.
* Word có hình ảnh phức tạp có thể không được phân tích đầy đủ.
* Tool không lưu lịch sử.
* Kết quả không thay thế việc thẩm định của giáo viên.

---

## 22. Requirements dự kiến

Tạo `requirements.txt` với các thư viện chính:

```text
streamlit
openai
pymupdf
python-docx
pydantic
python-dotenv
pytest
```

Khóa phiên bản tương thích sau khi chạy thử thành công.

Không thêm thư viện không sử dụng.

---

## 23. Kiểm thử bắt buộc

### PDF

* PDF một trang có văn bản.
* PDF nhiều trang.
* PDF scan.
* PDF rỗng.
* PDF hỏng.
* PDF có mật khẩu.
* PDF vượt quá giới hạn trang.

### DOCX

* DOCX chỉ có paragraph.
* DOCX có heading.
* DOCX có bảng.
* DOCX có câu hỏi trắc nghiệm.
* DOCX rỗng.
* DOCX hỏng.
* DOCX có hình ảnh.

### AI result

* JSON hợp lệ.
* JSON thiếu trường.
* Confidence ngoài khoảng 0–1.
* Category không hợp lệ.
* AI trả hai lỗi trùng.
* AI timeout.
* API hết quota.

### Giao diện

* Tải file mới phải xóa kết quả file cũ.
* Nút xóa kết quả hoạt động.
* Không thể bấm phân tích khi chưa có file.
* Không tự gọi lại AI khi thay đổi bộ lọc kết quả.
* Tải báo cáo không làm mất kết quả đang hiển thị.

---

## 24. Tiêu chí nghiệm thu

Tool được xem là hoàn thành khi đáp ứng đầy đủ:

1. Chạy được bằng `streamlit run app.py`.
2. Nhận đúng file PDF và DOCX.
3. Không nhận định dạng khác.
4. Không có đăng nhập.
5. Không có database.
6. Không lưu lịch sử.
7. Phân tích được tiếng Việt và tiếng Anh.
8. Phát hiện được lỗi đề bài cơ bản.
9. Phát hiện được vấn đề câu hỏi và đáp án.
10. Trả về vị trí trang hoặc block khi có thể.
11. Kết quả AI được validate bằng Pydantic.
12. Có phân loại mức độ lỗi.
13. Có confidence.
14. Có cảnh báo khi AI không chắc chắn.
15. Có đề xuất sửa.
16. Có thể đề xuất câu hỏi thay thế.
17. Có thể xuất báo cáo DOCX và JSON.
18. Khi tải file khác, kết quả cũ bị xóa.
19. File tạm được dọn trong mọi trường hợp.
20. API key không xuất hiện trong source code.
21. Có xử lý lỗi thân thiện.
22. Có README hướng dẫn chạy trên Windows.
23. Có test cho parser và merge kết quả.
24. Không tạo chức năng ngoài phạm vi.

---

## 25. Thứ tự triển khai

Thực hiện theo từng giai đoạn.

### Giai đoạn 1: Khởi tạo

* Tạo cấu trúc thư mục.
* Tạo requirements.
* Tạo settings.
* Tạo `.env.example`.
* Tạo UI upload cơ bản.

### Giai đoạn 2: Parser

* Viết PDF parser.
* Viết DOCX parser.
* Chuẩn hóa block dữ liệu.
* Viết validator file.
* Viết test parser.

### Giai đoạn 3: AI

* Tạo Pydantic schema.
* Viết system prompt.
* Kết nối OpenAI.
* Cấu hình Structured Output.
* Retry khi lỗi.
* Test bằng tài liệu nhỏ.

### Giai đoạn 4: Tài liệu dài

* Chia PDF theo trang.
* Chia DOCX theo section/block.
* Phân tích từng chunk.
* Gộp lỗi.
* Loại lỗi trùng.

### Giai đoạn 5: Giao diện kết quả

* Thống kê.
* Bộ lọc.
* Issue cards.
* Progress.
* Error state.
* Reset tài liệu.

### Giai đoạn 6: Báo cáo và hoàn thiện

* Xuất DOCX.
* Xuất JSON.
* Cleanup file.
* README.
* Test toàn bộ luồng.
* Sửa lỗi giao diện và xử lý ngoại lệ.

---

## 26. Yêu cầu đối với AI code

Trước khi kết thúc công việc, AI code phải:

1. Hoàn thành toàn bộ luồng chạy thực tế, không chỉ tạo giao diện giả.
2. Không để dữ liệu mẫu thay cho kết quả OpenAI.
3. Không hard-code kết quả.
4. Không bỏ trống các service quan trọng.
5. Không tạo TODO cho chức năng bắt buộc.
6. Chạy kiểm tra import.
7. Chạy test.
8. Kiểm tra ứng dụng có thể khởi động.
9. Sửa toàn bộ lỗi phát hiện được.
10. Báo cáo:

    * Danh sách file đã tạo.
    * Cách cài đặt.
    * Cách chạy.
    * Các biến môi trường cần cấu hình.
    * Những giới hạn còn tồn tại.

Ưu tiên code rõ ràng, có type hint, chia module hợp lý và xử lý ngoại lệ đầy đủ. Không xây dựng quá phức tạp so với phạm vi tool cá nhân.
