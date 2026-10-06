"""대화형 입력 도우미."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from budget_app.errors import AppError
from budget_app.services import BudgetService
from budget_app.validators import parse_category_name

T = TypeVar("T")


def print_error(exc: AppError) -> None:
    print(f"[오류] {exc.message}")
    if exc.hint:
        print(f"[힌트] {exc.hint}")


def ask(prompt: str, parser: Callable[[str], T]) -> T:
    """유효한 값이 들어올 때까지 반복해서 묻는다."""
    while True:
        try:
            return parser(input(prompt))
        except AppError as exc:
            print_error(exc)


def ask_category(svc: BudgetService, prompt: str = "카테고리: ") -> str:
    return ask(prompt, lambda text: svc.require_category(parse_category_name(text)))
