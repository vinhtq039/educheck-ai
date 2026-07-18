from __future__ import annotations

import re
import unicodedata


QUESTION_RE = re.compile(r"^\s*(?:câu\s*)?(\d+(?:[.)]|\b)|[IVXLCDM]+[.)])", re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_question_number(text: str) -> str | None:
    match = QUESTION_RE.match(text)
    if not match:
        return None
    return match.group(1).rstrip(".)")


def similarity_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\W+", " ", normalized).strip()

