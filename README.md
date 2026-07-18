# EduCheck AI

Ứng dụng Streamlit dùng OpenAI GPT-5.6 Sol để kiểm tra một bộ gồm **giáo án và học liệu**.
AI đọc giáo án trước để xác định môn học, khối lớp, chủ đề, mục tiêu, phạm vi kiến thức
và tiêu chí đánh giá; sau đó mới kiểm tra học liệu PDF/DOCX theo đúng căn cứ đó.

Ứng dụng dành cho một người dùng, không đăng nhập, không dùng cơ sở dữ liệu và
không lưu tài liệu hay lịch sử phân tích.

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
OPENAI_MODEL=gpt-5.6-sol
OPENAI_REASONING_EFFORT=medium
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
| `OPENAI_MODEL` | `gpt-5.6-sol` | Model OpenAI |
| `OPENAI_REASONING_EFFORT` | `medium` | Mức suy luận: `none` đến `max` |
| `OPENAI_TEXT_VERBOSITY` | `low` | Độ dài đầu ra AI: `low`, `medium`, `high` |
| `MAX_FILE_SIZE_MB` | `30` | Dung lượng tối đa |
| `MAX_PDF_PAGES` | `150` | Số trang PDF tối đa |
| `PDF_PAGES_PER_CHUNK` | `10` | Số trang mỗi phần với PDF trên 25 trang |
| `DOCX_CHARS_PER_CHUNK` | `30000` | Ngưỡng ký tự mỗi phần Word |
| `AI_MAX_RETRIES` | `2` | Số lần thử lại khi lỗi/schema không hợp lệ |
| `AI_TIMEOUT_SECONDS` | `180` | Thời gian chờ API |

## Luồng xử lý

1. Tải một giáo án và một học liệu; cả hai có thể là DOCX hoặc PDF.
2. Kiểm tra, trích xuất và chia giáo án nếu cần.
3. OpenAI chuẩn hóa giáo án thành `LessonPlanProfile`.
4. Kiểm tra, trích xuất và chia học liệu.
5. Phân tích từng phần học liệu với `LessonPlanProfile` làm căn cứ đối chiếu.
6. Khóa nguyên văn vào trang/block thật và loại vị trí không tồn tại.
7. Chạy lượt AI kiểm duyệt cuối: chỉ được giữ, sửa hoặc loại ứng viên; không được tạo
   lỗi mới hay thay đổi vị trí/nguyên văn.
8. Tạo một tóm tắt cô đọng, tối đa năm đề xuất chung và sắp xếp kết quả.
9. Hiển thị học liệu được đánh dấu, giáo án đối chiếu và báo cáo trong ba khu vực rõ ràng.
10. Báo cáo DOCX/JSON chứa tên cả hai file và căn cứ đã trích xuất từ giáo án.

## Giới hạn

- Kết quả AI có thể chưa chính xác; nội dung chuyên môn cần giáo viên xác minh.
- Lượt kiểm duyệt cuối làm tăng thêm một lần gọi API cho mỗi bộ tài liệu.
- Ảnh và đối tượng nhúng trong Word không được phân tích đầy đủ ở MVP.
- PDF scan có thể làm vị trí lỗi kém chính xác.
- Ứng dụng không chỉnh sửa trực tiếp tài liệu gốc và không lưu lịch sử.
- Không có OCR riêng; PDF scan được gửi trực tiếp cho khả năng đọc tài liệu của GPT-5.6 Sol.
