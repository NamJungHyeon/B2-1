"""입력 문자열을 검증하고 정규화한다. 실패하면 AppError."""

from __future__ import annotations

import re
from datetime import date

from budget_app.errors import AppError

TRANSACTION_TYPES: tuple[str, ...] = ("income", "expense")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_AMOUNT_RE = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)")


def parse_date(text: str) -> str:
    """YYYY-MM-DD 형식인지 검사하고 정규화한 문자열을 돌려준다."""
    text = text.strip()
    if not _DATE_RE.match(text):
        raise AppError("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).", "예: 2024-01-15")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise AppError("존재하지 않는 날짜입니다.", "예: 2024-01-15") from None


def parse_month(text: str) -> str:
    text = text.strip()
    if not _MONTH_RE.match(text):
        raise AppError("월 형식이 올바르지 않습니다 (YYYY-MM).", "예: 2024-01")
    month = int(text[5:7])
    if not 1 <= month <= 12:
        raise AppError("월은 01~12 사이여야 합니다.", "예: 2024-01")
    parse_date(f"{text}-01")
    return text


def parse_type(text: str) -> str:
    text = text.strip().lower()
    if text not in TRANSACTION_TYPES:
        raise AppError(
            f"타입은 {'/'.join(TRANSACTION_TYPES)} 중 하나여야 합니다.",
            "예: expense",
        )
    return text


def parse_amount(text: str) -> int:
    text = text.strip()
    try:
        # int()는 자릿수가 너무 많으면 ValueError를 던지므로 같은 경로로 처리한다.
        amount = int(text.replace(",", "")) if _AMOUNT_RE.fullmatch(text) else 0
    except ValueError:
        amount = 0
    if amount <= 0:
        raise AppError("금액은 양수 정수여야 합니다.", "예: 15000 또는 15,000")
    return amount


def parse_tags(text: str | None) -> list[str]:
    """쉼표로 구분된 문자열을 태그 목록으로. 빈 값과 중복은 제거한다."""
    if not text:
        return []
    seen: list[str] = []
    for raw in text.split(","):
        tag = raw.strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def parse_category_name(text: str) -> str:
    if not isinstance(text, str):
        raise AppError("카테고리명은 문자열이어야 합니다.")
    text = text.strip()
    if not text:
        raise AppError("카테고리명은 비어 있을 수 없습니다.", "예: food")
    if "," in text:
        raise AppError("카테고리명에 쉼표(,)는 쓸 수 없습니다.", "예: food")
    return text
