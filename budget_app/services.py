"""서비스 계층. 저장소를 조합해 실제 기능(CRUD/검색/요약/입출력)을 수행한다.

화면 출력은 하지 않고 값만 돌려준다. 출력은 cli.py가 담당한다.
"""

from __future__ import annotations

import csv
import heapq
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from budget_app.decorators import log_call
from budget_app.models import (
    AppError,
    Budget,
    Summary,
    Transaction,
    parse_amount,
    parse_date,
    parse_tags,
    parse_type,
)
from budget_app.storage import (
    BudgetStore,
    CategoryStore,
    TransactionRepository,
    backup_files,
    atomic_text_writer,
)

from budget_app.sorting import iter_latest, transaction_key

CSV_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount", "memo", "tags")


@dataclass
class SearchFilter:
    date_from: str | None = None
    date_to: str | None = None
    category: str | None = None
    type: str | None = None
    keyword: str | None = None
    tag: str | None = None

    def matches(self, tx: Transaction) -> bool:
        if self.date_from and tx.date < self.date_from:
            return False
        if self.date_to and tx.date > self.date_to:
            return False
        if self.category and tx.category != self.category:
            return False
        if self.type and tx.type != self.type:
            return False
        if self.keyword and self.keyword.lower() not in tx.memo.lower():
            return False
        if self.tag and self.tag not in tx.tags:
            return False
        return True


@dataclass
class ImportResult:
    imported: int
    skipped: int
    errors: list[str]


class BudgetService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.transactions = TransactionRepository(data_dir)
        self.categories = CategoryStore(data_dir)
        self.budgets = BudgetStore(data_dir)

    def initialize(self) -> list[str]:
        """저장 파일이 없으면 만든다. 새로 만든 파일 이름 목록을 돌려준다."""
        created: list[str] = []
        if self.transactions.ensure():
            created.append(self.transactions.file.path.name)
        if self.categories.ensure():
            created.append(self.categories.file.path.name)
        if self.budgets.ensure():
            created.append(self.budgets.file.path.name)
        return created

    # ------------------------------------------------------------ 거래 CRUD

    def require_category(self, name: str) -> str:
        categories = self.categories.load()
        if name not in categories:
            raise AppError(
                f"등록되지 않은 카테고리입니다: {name}",
                f"category add 로 먼저 등록하세요. 현재: {', '.join(categories)}",
            )
        return name

    @log_call
    def add_transaction(
        self,
        date: str,
        type_: str,
        category: str,
        amount: int,
        memo: str = "",
        tags: list[str] | None = None,
    ) -> Transaction:
        self.require_category(category)
        tx = Transaction(
            id=self.transactions.next_id(),
            type=type_,
            date=date,
            amount=amount,
            category=category,
            memo=memo,
            tags=tags or [],
        )
        self.transactions.add(tx)
        return tx

    @log_call
    def update_transaction(self, tx_id: str, **changes: object) -> Transaction:
        """changes에 담긴 필드만 바꾼다. 값은 이미 검증된 것이어야 한다."""
        tx = self.transactions.find(tx_id)
        if tx is None:
            raise AppError(f"존재하지 않는 id입니다: {tx_id}", "list 명령으로 id를 확인하세요.")
        if "category" in changes:
            self.require_category(str(changes["category"]))
        for key, value in changes.items():
            setattr(tx, key, value)
        self.transactions.update(tx)
        return tx

    @log_call
    def delete_transaction(self, tx_id: str) -> None:
        if not self.transactions.delete(tx_id):
            raise AppError(f"존재하지 않는 id입니다: {tx_id}", "list 명령으로 id를 확인하세요.")

    # ------------------------------------------------------------ 조회

    @log_call
    def list_latest(self, limit: int) -> list[Transaction]:
        """스트리밍으로 읽으면서 최신 N건만 힙에 유지한다 (메모리는 N에 비례)."""
        return heapq.nlargest(limit, self.transactions.iter_all(), key=transaction_key)

    def iter_search(self, flt: SearchFilter) -> Iterator[Transaction]:
        matches = (tx for tx in self.transactions.iter_all() if flt.matches(tx))
        yield from iter_latest(matches)

    @log_call
    def search(self, flt: SearchFilter) -> list[Transaction]:
        return list(self.iter_search(flt))

    @log_call
    def summary(self, month: str, top: int) -> Summary:
        income = expense = count = 0
        by_category: Counter[str] = Counter()
        for tx in self.transactions.iter_all():
            if tx.month != month:
                continue
            count += 1
            if tx.type == "income":
                income += tx.amount
            else:
                expense += tx.amount
                by_category[tx.category] += tx.amount
        budget = self.budgets.get(month)
        return Summary(
            month=month,
            count=count,
            total_income=income,
            total_expense=expense,
            top_expenses=by_category.most_common(top),
            budget=budget.amount if budget else None,
        )

    # ------------------------------------------------------------ 예산 / 카테고리

    @log_call
    def set_budget(self, month: str, amount: int) -> Budget:
        budget = Budget(month=month, amount=amount)
        self.budgets.set(budget)
        return budget

    def list_categories(self) -> list[str]:
        return self.categories.load()

    @log_call
    def add_category(self, name: str) -> None:
        self.categories.add(name)

    @log_call
    def remove_category(self, name: str, replace_with: str | None = None) -> int:
        """카테고리를 삭제한다. 사용 중이면 대체 카테고리가 있어야 하며, 옮긴 건수를 돌려준다."""
        if not self.categories.exists(name):
            raise AppError(f"존재하지 않는 카테고리입니다: {name}", "category list로 확인하세요.")
        in_use = self.transactions.count_category(name)
        moved = 0
        if in_use:
            if replace_with is None:
                raise AppError(
                    f"'{name}' 카테고리를 사용하는 거래가 {in_use}건 있어 삭제할 수 없습니다.",
                    f"category remove {name} --replace <대체카테고리> 로 옮긴 뒤 삭제하세요.",
                )
            if replace_with == name:
                raise AppError("대체 카테고리가 삭제 대상과 같습니다.", "다른 카테고리를 지정하세요.")
            self.require_category(replace_with)
            moved = self.transactions.replace_category(name, replace_with)
        self.categories.remove(name)
        return moved

    # ------------------------------------------------------------ import / export

    @log_call
    def export_csv(self, out: Path, flt: SearchFilter) -> int:
        count = 0
        protected = (
            self.transactions.file.path, self.categories.file.path,
            self.budgets.file.path, self.data_dir / "app.log",
        )
        for path in protected:
            if out.resolve() == path.resolve() or (
                out.exists() and path.exists() and out.samefile(path)
            ):
                raise AppError("저장 파일에는 CSV를 내보낼 수 없습니다.", "다른 출력 경로를 지정하세요.")
        with atomic_text_writer(out) as fp:
            writer = csv.DictWriter(fp, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for tx in self.iter_search(flt):
                writer.writerow(
                    {
                        "date": tx.date,
                        "type": tx.type,
                        "category": tx.category,
                        "amount": tx.amount,
                        "memo": tx.memo,
                        "tags": ",".join(tx.tags),
                    }
                )
                count += 1
        return count

    @log_call
    def import_csv(self, src: Path) -> ImportResult:
        """CSV를 한 줄씩 읽어 검증하고, 유효한 것만 일괄 저장한다. 잘못된 줄은 건너뛴다."""
        if not src.exists():
            raise AppError(f"파일을 찾을 수 없습니다: {src}", "경로를 확인하세요.")
        known = set(self.categories.load())
        errors: list[str] = []

        def valid_rows() -> Iterator[Transaction]:
            with src.open("r", encoding="utf-8-sig", newline="") as fp:
                reader = csv.DictReader(fp, strict=True)
                missing = [c for c in CSV_COLUMNS[:4] if c not in (reader.fieldnames or [])]
                if missing:
                    raise AppError(
                        f"CSV 헤더에 필수 컬럼이 없습니다: {', '.join(missing)}",
                        f"필수 컬럼: {', '.join(CSV_COLUMNS[:4])}",
                    )
                next_no = int(self.transactions.next_id()[len(TransactionRepository.ID_PREFIX):])
                for line_no, row in enumerate(reader, start=2):
                    try:
                        category = (row.get("category") or "").strip()
                        if category not in known:
                            raise AppError(f"등록되지 않은 카테고리: {category}")
                        tx = Transaction(
                            id=f"{TransactionRepository.ID_PREFIX}{next_no:0{TransactionRepository.ID_WIDTH}d}",
                            type=parse_type(row.get("type") or ""),
                            date=parse_date(row.get("date") or ""),
                            amount=parse_amount(row.get("amount") or ""),
                            category=category,
                            memo=(row.get("memo") or "").strip(),
                            tags=parse_tags(row.get("tags")),
                        )
                    except AppError as exc:
                        errors.append(f"{line_no}행: {exc.message}")
                        continue
                    next_no += 1
                    yield tx

        imported = self.transactions.add_many(valid_rows())
        return ImportResult(imported=imported, skipped=len(errors), errors=errors)

    # ------------------------------------------------------------ 백업

    @log_call
    def backup(self) -> list[Path]:
        return backup_files(self.data_dir, self.data_dir / "backups")
