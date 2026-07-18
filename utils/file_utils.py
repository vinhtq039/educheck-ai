from __future__ import annotations

import hashlib
import re
from pathlib import Path


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_report_stem(file_name: str) -> str:
    stem = Path(file_name).stem
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", stem).strip(" .-")
    return cleaned[:100] or "document"


def format_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"

