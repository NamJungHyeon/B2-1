"""거래 내역 저장소."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from budget_app.models import Transaction
from budget_app.storage.jsonl import JsonlFile

TRANSACTIONS_FILE = "transactions.jsonl"


class TransactionRepository:
    ID_PREFIX = "TX-"
    ID_WIDTH = 6

    def __init__(self, data_dir: Path) -> None:
        self.file = JsonlFile(data_dir / TRANSACTIONS_FILE)

    @classmethod
    def format_id(cls, number: int) -> str:
        return f"{cls.ID_PREFIX}{number:0{cls.ID_WIDTH}d}"

    @classmethod
    def parse_id(cls, tx_id: str) -> int:
        return int(tx_id.removeprefix(cls.ID_PREFIX))

    def ensure(self) -> bool:
        return self.file.ensure()

    def iter_all(self) -> Iterator[Transaction]:
        yield from self.file.iter_rows(Transaction.from_dict)

    def next_number(self) -> int:
        """다음에 발급할 id 번호. 파일을 끝까지 훑어 최댓값 + 1을 돌려준다."""
        last = 0
        for tx in self.iter_all():
            last = max(last, self.parse_id(tx.id))
        return last + 1

    def next_id(self) -> str:
        return self.format_id(self.next_number())

    def add(self, tx: Transaction) -> None:
        self.file.append_row(tx.to_dict())

    def add_many(self, txs: Iterable[Transaction]) -> int:
        """기존 행 뒤에 여러 건을 붙인다. 도중에 실패하면 원본은 그대로 남는다."""
        count = 0

        def rows() -> Iterator[dict[str, Any]]:
            nonlocal count
            for existing in self.iter_all():
                yield existing.to_dict()
            for tx in txs:
                yield tx.to_dict()
                count += 1

        self.file.rewrite_rows(rows())
        return count

    def find(self, tx_id: str) -> Transaction | None:
        for tx in self.iter_all():
            if tx.id == tx_id:
                return tx
        return None

    def update(self, updated: Transaction) -> bool:
        """id가 같은 거래를 교체한다. 없으면 False."""
        if self.find(updated.id) is None:
            return False
        self.file.rewrite_rows(
            (updated if tx.id == updated.id else tx).to_dict() for tx in self.iter_all()
        )
        return True

    def delete(self, tx_id: str) -> bool:
        if self.find(tx_id) is None:
            return False
        self.file.rewrite_rows(tx.to_dict() for tx in self.iter_all() if tx.id != tx_id)
        return True

    def count_category(self, category: str) -> int:
        return sum(1 for tx in self.iter_all() if tx.category == category)

    def replace_category(self, old: str, new: str) -> int:
        """old 카테고리를 쓰는 모든 거래를 new로 바꾸고 바꾼 건수를 돌려준다."""
        changed = 0

        def rows() -> Iterator[dict[str, Any]]:
            nonlocal changed
            for tx in self.iter_all():
                if tx.category == old:
                    tx.category = new
                    changed += 1
                yield tx.to_dict()

        self.file.rewrite_rows(rows())
        return changed
