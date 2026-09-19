"""데이터 모델과 입력 검증.

여기에는 파일 I/O나 화면 출력이 없다. 순수하게 값의 형태와 규칙만 정의한다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

TRANSACTION_TYPES: tuple[str, ...] = ("income", "expense")
DEFAULT_CATEGORIES: tuple[str, ...] = ("food", "transport", "rent", "salary", "etc")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class AppError(Exception):
    """사용자에게 보여줄 오류. 원인(message)과 해결 힌트(hint)를 함께 가진다."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


# ---------------------------------------------------------------- 검증 함수


def parse_date(text: str) -> str:
    """YYYY-MM-DD 형식인지 검사하고 정규화한 문자열을 돌려준다."""
    text = text.strip()
    if not _DATE_RE.match(text):
        raise AppError("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).", "예: 2024-01-15")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise AppError("존재하지 않는 날짜입니다.", "예: 2024-01-15")


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
        if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", text):
            raise ValueError
        amount = int(text.replace(",", ""))
        if amount <= 0:
            raise ValueError
        return amount
    except ValueError:
        raise AppError("금액은 양수 정수여야 합니다.", "예: 15000 또는 15,000") from None


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


# ---------------------------------------------------------------- 데이터 모델


@dataclass
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def month(self) -> str:
        return self.date[:7]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        for key in ("id", "type", "date", "category"):
            if not isinstance(data[key], str):
                raise ValueError(f"{key}: 문자열이 필요합니다.")
        if not re.fullmatch(r"TX-[0-9]{6,}", data["id"]) or int(data["id"][3:]) <= 0:
            raise ValueError("잘못된 거래 ID입니다.")
        if type(data["amount"]) is not int or data["amount"] <= 0:
            raise ValueError("금액은 양수 정수여야 합니다.")
        memo, tags = data.get("memo", ""), data.get("tags", [])
        if not isinstance(memo, str) or not isinstance(tags, list):
            raise ValueError("메모 또는 태그 형식이 올바르지 않습니다.")
        if any(not isinstance(tag, str) for tag in tags):
            raise ValueError("태그는 문자열이어야 합니다.")
        return cls(
            id=data["id"],
            type=parse_type(data["type"]),
            date=parse_date(data["date"]),
            amount=data["amount"],
            category=parse_category_name(data["category"]),
            memo=memo,
            tags=tags,
        )


@dataclass
class Budget:
    month: str
    amount: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Budget":
        if not isinstance(data["month"], str):
            raise ValueError("월은 문자열이어야 합니다.")
        if type(data["amount"]) is not int or data["amount"] <= 0:
            raise ValueError("예산은 양수 정수여야 합니다.")
        return cls(month=parse_month(data["month"]), amount=data["amount"])


@dataclass
class Summary:
    """summary 명령의 결과. 출력은 CLI가 담당한다."""

    month: str
    count: int
    total_income: int
    total_expense: int
    top_expenses: list[tuple[str, int]]
    budget: int | None

    @property
    def balance(self) -> int:
        return self.total_income - self.total_expense

    @property
    def budget_usage(self) -> float | None:
        if self.budget is None or self.budget == 0:
            return None
        return self.total_expense / self.budget * 100

    @property
    def over_budget(self) -> bool:
        return self.budget is not None and self.total_expense > self.budget
