"""월별 예산 저장소. 한 줄에 {"month": "YYYY-MM", "amount": N} 하나."""

from __future__ import annotations

from pathlib import Path

from budget_app.models import Budget
from budget_app.storage.jsonl import JsonlFile

BUDGETS_FILE = "budgets.jsonl"


class BudgetStore:
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
        others = [
            item.to_dict()
            for item in self.file.iter_rows(Budget.from_dict)
            if item.month != budget.month
        ]
        others.append(budget.to_dict())
        others.sort(key=lambda r: str(r["month"]))
        self.file.rewrite_rows(others)
