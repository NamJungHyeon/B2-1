"""파일 저장소 계층 (JSONL).

각 저장소는 파일 하나를 책임진다. 읽기는 제너레이터로 한 줄씩 스트리밍하고,
전체 재작성이 필요한 경우(update/delete)는 임시 파일에 쓴 뒤 os.replace로
원자적으로 교체한다.
"""

from budget_app.storage.backup import backup_files
from budget_app.storage.budgets import BUDGETS_FILE, BudgetStore
from budget_app.storage.categories import CATEGORIES_FILE, DEFAULT_CATEGORIES, CategoryStore
from budget_app.storage.jsonl import JsonlFile, atomic_text_writer
from budget_app.storage.transactions import TRANSACTIONS_FILE, TransactionRepository

__all__ = [
    "BUDGETS_FILE",
    "CATEGORIES_FILE",
    "DEFAULT_CATEGORIES",
    "TRANSACTIONS_FILE",
    "BudgetStore",
    "CategoryStore",
    "JsonlFile",
    "TransactionRepository",
    "atomic_text_writer",
    "backup_files",
]
