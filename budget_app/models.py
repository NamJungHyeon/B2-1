"""데이터 모델. 파일 I/O나 화면 출력은 모른다.

from_dict는 저장 파일에서 읽은 값을 검증한다. 손상된 행이면 ValueError/AppError를
던지고, 저장소 계층이 이를 파일명·줄 번호와 함께 사용자 오류로 바꾼다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from budget_app.validators import parse_category_name, parse_date, parse_month, parse_type

_TX_ID_RE = re.compile(r"TX-[0-9]{6,}")


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
        if not _TX_ID_RE.fullmatch(data["id"]) or int(data["id"][3:]) <= 0:
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
