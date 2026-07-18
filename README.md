# EduCheck AI

Ứng dụng Streamlit dùng OpenAI GPT-5.6 Sol để kiểm tra học liệu PDF và DOCX: chính tả,
ngữ pháp, diễn đạt, độ rõ ràng của đề bài, tính hợp lý của câu hỏi/đáp án và mức
độ phù hợp với môn học, khối lớp, chủ đề, mục tiêu bài học.

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
| `MAX_FILE_SIZE_MB` | `30` | Dung lượng tối đa |
| `MAX_PDF_PAGES` | `150` | Số trang PDF tối đa |
| `PDF_PAGES_PER_CHUNK` | `10` | Số trang mỗi phần với PDF trên 25 trang |
| `DOCX_CHARS_PER_CHUNK` | `30000` | Ngưỡng ký tự mỗi phần Word |
| `AI_MAX_RETRIES` | `2` | Số lần thử lại khi lỗi/schema không hợp lệ |
| `AI_TIMEOUT_SECONDS` | `180` | Thời gian chờ API |

## Luồng xử lý

1. Kiểm tra dung lượng, phần mở rộng và chữ ký thực tế của PDF/DOCX.
2. Trích xuất trang/block và cảnh báo PDF scan hoặc Word có ảnh.
3. Chia tài liệu dài; với PDF, OpenAI nhận cả dữ liệu PDF để giữ bố cục và hình.
4. Yêu cầu OpenAI Responses API trả structured output theo schema Pydantic.
5. Chuẩn hóa số trang, loại lỗi trùng và sắp xếp theo mức độ/vị trí.
6. Hiển thị bộ lọc và cho tải báo cáo DOCX/JSON ngay trong phiên.

## Giới hạn

- Kết quả AI có thể chưa chính xác; nội dung chuyên môn cần giáo viên xác minh.
- Ảnh và đối tượng nhúng trong Word không được phân tích đầy đủ ở MVP.
- PDF scan có thể làm vị trí lỗi kém chính xác.
- Ứng dụng không chỉnh sửa trực tiếp tài liệu gốc và không lưu lịch sử.
- Không có OCR riêng; PDF scan được gửi trực tiếp cho khả năng đọc tài liệu của GPT-5.6 Sol.
