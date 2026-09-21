"""import/export CSV 스키마와 행 변환.

| column   | required | 설명                    |
| date     | Y        | YYYY-MM-DD              |
| type     | Y        | income / expense        |
| category | Y        | 등록된 카테고리          |
| amount   | Y        | 양수 정수                |
| memo     | N        | 문자열                   |
| tags     | N        | 쉼표(,) 구분 문자열       |
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from budget_app.errors import AppError
from budget_app.models import Transaction
from budget_app.validators import parse_amount, parse_date, parse_tags, parse_type

CSV_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount", "memo", "tags")
REQUIRED_COLUMNS: tuple[str, ...] = CSV_COLUMNS[:4]


def transaction_to_row(tx: Transaction) -> dict[str, str | int]:
    return {
        "date": tx.date,
        "type": tx.type,
        "category": tx.category,
        "amount": tx.amount,
        "memo": tx.memo,
        "tags": ",".join(tx.tags),
    }


def row_to_transaction(row: dict[str, str | None], tx_id: str, known_categories: set[str]) -> Transaction:
    """CSV 한 행을 검증해 Transaction으로. 잘못된 값이면 AppError."""
    category = (row.get("category") or "").strip()
    if category not in known_categories:
        raise AppError(f"등록되지 않은 카테고리: {category}")
    return Transaction(
        id=tx_id,
        type=parse_type(row.get("type") or ""),
        date=parse_date(row.get("date") or ""),
        amount=parse_amount(row.get("amount") or ""),
        category=category,
        memo=(row.get("memo") or "").strip(),
        tags=parse_tags(row.get("tags")),
    )


def open_csv_writer(fp: TextIO) -> csv.DictWriter:
    writer = csv.DictWriter(fp, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    return writer


def iter_csv_rows(src: Path) -> Iterator[tuple[int, dict[str, str | None]]]:
    """헤더를 검증한 뒤 (줄 번호, 행)을 한 줄씩 넘긴다."""
    if not src.exists():
        raise AppError(f"파일을 찾을 수 없습니다: {src}", "경로를 확인하세요.")
    with src.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp, strict=True)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise AppError(
                f"CSV 헤더에 필수 컬럼이 없습니다: {', '.join(missing)}",
                f"필수 컬럼: {', '.join(REQUIRED_COLUMNS)}",
            )
        for line_no, row in enumerate(reader, start=2):
            yield line_no, row
