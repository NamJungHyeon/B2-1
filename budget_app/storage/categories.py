"""카테고리 저장소. 한 줄에 {"name": "..."} 하나."""

from __future__ import annotations

from pathlib import Path

from budget_app.errors import AppError
from budget_app.storage.jsonl import JsonlFile
from budget_app.validators import parse_category_name

CATEGORIES_FILE = "categories.jsonl"
DEFAULT_CATEGORIES: tuple[str, ...] = ("food", "transport", "rent", "salary", "etc")


class CategoryStore:
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
