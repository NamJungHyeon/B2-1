"""파일 저장소 계층 (JSONL).

각 저장소는 파일 하나를 책임진다. 읽기는 제너레이터로 한 줄씩 스트리밍하고,
전체 재작성이 필요한 경우(update/delete)는 임시 파일에 쓴 뒤 os.replace로
원자적으로 교체한다.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO, TypeVar

from budget_app.models import DEFAULT_CATEGORIES, AppError, Budget, Transaction, parse_category_name

T = TypeVar("T")

TRANSACTIONS_FILE = "transactions.jsonl"
CATEGORIES_FILE = "categories.jsonl"
BUDGETS_FILE = "budgets.jsonl"


@contextmanager
def atomic_text_writer(path: Path) -> Iterator[TextIO]:
    """쓰기 성공 시에만 대상 파일을 교체하고 실패 시 임시 파일을 정리한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fp:
            yield fp
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class JsonlFile:
    """JSONL 파일 하나에 대한 저수준 읽기/쓰기."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure(self) -> bool:
        """파일이 없으면 빈 파일을 만든다. 새로 만들었으면 True."""
        if self.path.exists():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        return True

    def iter_rows(self, decode: Callable[[dict[str, Any]], T] = dict) -> Iterator[T]:
        """한 줄씩 읽고 변환하며, 손상된 행은 파일명과 줄 번호로 알린다."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fp:
            for line_no, line in enumerate(fp, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("JSON 객체가 필요합니다.")
                    value = decode(row)
                except (ValueError, TypeError, KeyError, AppError):
                    raise AppError(
                        f"{self.path.name} {line_no}번째 줄이 손상되었습니다.",
                        "해당 줄을 직접 수정하거나 백업에서 복구하세요.",
                    ) from None
                yield value

    def append_row(self, row: dict[str, Any]) -> None:
        self.ensure()
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    def rewrite_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        """임시 파일에 모두 쓴 뒤 rename으로 교체한다 (원자적 쓰기)."""
        with atomic_text_writer(self.path) as fp:
            for row in rows:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")


class TransactionRepository:
    """거래 내역 저장소."""

    ID_PREFIX = "TX-"
    ID_WIDTH = 6

    def __init__(self, data_dir: Path) -> None:
        self.file = JsonlFile(data_dir / TRANSACTIONS_FILE)

    def ensure(self) -> bool:
        return self.file.ensure()

    def iter_all(self) -> Iterator[Transaction]:
        yield from self.file.iter_rows(Transaction.from_dict)

    def next_id(self) -> str:
        last = 0
        for tx in self.iter_all():
            last = max(last, int(tx.id[len(self.ID_PREFIX):]))
        return f"{self.ID_PREFIX}{last + 1:0{self.ID_WIDTH}d}"

    def add(self, tx: Transaction) -> None:
        self.file.append_row(tx.to_dict())

    def add_many(self, txs: Iterable[Transaction]) -> int:
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
        self.file.rewrite_rows(
            tx.to_dict() for tx in self.iter_all() if tx.id != tx_id
        )
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


class CategoryStore:
    """카테고리 저장소. 한 줄에 {"name": "..."} 하나."""

    def __init__(self, data_dir: Path) -> None:
        self.file = JsonlFile(data_dir / CATEGORIES_FILE)

    def ensure(self) -> bool:
        """파일이 없거나 비어 있으면 기본 카테고리를 채운다. 초기화했으면 True."""
        created = self.file.ensure()
        if created or not self.load():
            self.file.rewrite_rows({"name": name} for name in DEFAULT_CATEGORIES)
            return True
        return False

    def load(self) -> list[str]:
        return list(self.file.iter_rows(lambda row: parse_category_name(row["name"])))

    def exists(self, name: str) -> bool:
        return name in self.load()

    def add(self, name: str) -> None:
        if self.exists(name):
            raise AppError(f"이미 존재하는 카테고리입니다: {name}", "category list로 확인하세요.")
        self.file.append_row({"name": name})

    def remove(self, name: str) -> None:
        names = self.load()
        if name not in names:
            raise AppError(f"존재하지 않는 카테고리입니다: {name}", "category list로 확인하세요.")
        self.file.rewrite_rows({"name": n} for n in names if n != name)


class BudgetStore:
    """월별 예산 저장소. 한 줄에 {"month": "YYYY-MM", "amount": N} 하나."""

    def __init__(self, data_dir: Path) -> None:
        self.file = JsonlFile(data_dir / BUDGETS_FILE)

    def ensure(self) -> bool:
        return self.file.ensure()

    def get(self, month: str) -> Budget | None:
        for budget in self.file.iter_rows(Budget.from_dict):
            if budget.month == month:
                return budget
        return None

    def set(self, budget: Budget) -> None:
        """같은 달이 있으면 덮어쓰고, 없으면 추가한다."""
        others = [item.to_dict() for item in self.file.iter_rows(Budget.from_dict)
                  if item.month != budget.month]
        others.append(budget.to_dict())
        others.sort(key=lambda r: str(r["month"]))
        self.file.rewrite_rows(others)


def backup_files(data_dir: Path, backup_dir: Path) -> list[Path]:
    """저장 파일 3개를 타임스탬프 폴더에 복사하고 복사된 경로를 돌려준다."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix=f"{stamp}-", dir=backup_dir))
    copied: list[Path] = []
    for name in (TRANSACTIONS_FILE, CATEGORIES_FILE, BUDGETS_FILE):
        src = data_dir / name
        if src.exists():
            dst = target / name
            shutil.copy2(src, dst)
            copied.append(dst)
    return copied
