from __future__ import annotations

import io
import zipfile


class FileValidationError(ValueError):
    """Friendly validation error safe to show in the UI."""


def detect_document_type(data: bytes, file_name: str) -> str:
    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if extension not in {"pdf", "docx"}:
        raise FileValidationError("File không đúng định dạng PDF hoặc DOCX.")
    if not data:
        raise FileValidationError("Tài liệu không được để trống.")

    if extension == "pdf":
        if not data.startswith(b"%PDF-"):
            raise FileValidationError("File không đúng định dạng PDF hoặc DOCX.")
        return "pdf"

    if not data.startswith(b"PK"):
        raise FileValidationError("File không đúng định dạng PDF hoặc DOCX.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise FileValidationError("File không đúng định dạng PDF hoặc DOCX.")
    except (zipfile.BadZipFile, OSError) as exc:
        raise FileValidationError(
            "Không thể đọc tài liệu Word. File có thể bị hỏng hoặc không đúng định dạng DOCX."
        ) from exc
    return "docx"


def validate_upload(data: bytes, file_name: str, max_size_bytes: int) -> str:
    if len(data) > max_size_bytes:
        raise FileValidationError("Tài liệu vượt quá dung lượng cho phép.")
    return detect_document_type(data, file_name)

