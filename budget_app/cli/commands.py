"""명령 핸들러. 각 함수는 (args, svc)를 받아 종료 코드를 돌려준다."""

from __future__ import annotations

import argparse
import calendar
from pathlib import Path

from budget_app.cli.formatting import format_summary, format_table
from budget_app.cli.prompts import ask, ask_category
from budget_app.decorators import log_call
from budget_app.errors import AppError
from budget_app.filters import SearchFilter
from budget_app.services import BudgetService
from budget_app.validators import (
    parse_amount,
    parse_category_name,
    parse_date,
    parse_month,
    parse_tags,
    parse_type,
)


def cmd_add(args: argparse.Namespace, svc: BudgetService) -> int:
    date = ask("날짜(YYYY-MM-DD): ", parse_date)
    type_ = ask("타입(income/expense): ", parse_type)
    category = ask_category(svc)
    amount = ask("금액(양수): ", parse_amount)
    memo = input("메모(선택): ").strip()
    tags = parse_tags(input("태그(쉼표로 구분, 없으면 엔터): "))
    tx = svc.add_transaction(date, type_, category, amount, memo, tags)
    print(f"[저장 완료] id={tx.id}")
    return 0


def cmd_list(args: argparse.Namespace, svc: BudgetService) -> int:
    if args.limit <= 0:
        raise AppError("--limit 은 1 이상이어야 합니다.", "예: --limit 10")
    print(format_table(svc.list_latest(args.limit)))
    return 0


def filter_from_args(args: argparse.Namespace) -> SearchFilter:
    """search/export 옵션을 SearchFilter로. --month는 --from/--to 범위를 그 달로 좁힌다."""
    flt = SearchFilter(
        date_from=parse_date(args.date_from) if args.date_from else None,
        date_to=parse_date(args.date_to) if args.date_to else None,
        category=getattr(args, "category", None),
        type=parse_type(args.type) if getattr(args, "type", None) else None,
        keyword=getattr(args, "q", None),
        tag=getattr(args, "tag", None),
    )
    if getattr(args, "month", None):
        month = parse_month(args.month)
        last_day = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
        month_start, month_end = f"{month}-01", f"{month}-{last_day:02d}"
        flt.date_from = max(flt.date_from or month_start, month_start)
        flt.date_to = min(flt.date_to or month_end, month_end)
    if flt.date_from and flt.date_to and flt.date_from > flt.date_to:
        raise AppError("--from 이 --to 보다 늦습니다.", "기간을 다시 확인하세요.")
    return flt


@log_call
def cmd_search(args: argparse.Namespace, svc: BudgetService) -> int:
    count = 0
    for tx in svc.iter_search(filter_from_args(args)):
        print(format_table([tx]))
        count += 1
    print(f"({count}건)" if count else "(거래 없음)")
    return 0


def cmd_summary(args: argparse.Namespace, svc: BudgetService) -> int:
    if args.top <= 0:
        raise AppError("--top 은 1 이상이어야 합니다.", "예: --top 3")
    print(format_summary(svc.summary(parse_month(args.month), args.top)))
    return 0


def cmd_budget_set(args: argparse.Namespace, svc: BudgetService) -> int:
    budget = svc.set_budget(parse_month(args.month), parse_amount(args.amount))
    print(f"[저장 완료] {budget.month} 예산 {budget.amount:,}원")
    return 0


def cmd_budget_show(args: argparse.Namespace, svc: BudgetService) -> int:
    month = parse_month(args.month)
    budget = svc.budgets.get(month)
    if budget is None:
        print(f"{month}: 예산 없음")
    else:
        print(f"{month} 예산: {budget.amount:,}원")
    return 0


def cmd_category_add(args: argparse.Namespace, svc: BudgetService) -> int:
    name = parse_category_name(args.name) if args.name else ask("카테고리명: ", parse_category_name)
    svc.add_category(name)
    print(f"[저장 완료] category={name}")
    return 0


def cmd_category_list(args: argparse.Namespace, svc: BudgetService) -> int:
    for name in svc.list_categories():
        print(f"- {name}")
    return 0


def cmd_category_remove(args: argparse.Namespace, svc: BudgetService) -> int:
    name = parse_category_name(args.name) if args.name else ask("삭제할 카테고리명: ", parse_category_name)
    moved = svc.remove_category(name, args.replace)
    if moved:
        print(f"[완료] {moved}건을 '{args.replace}'로 옮기고 '{name}'을(를) 삭제했습니다.")
    else:
        print(f"[삭제 완료] category={name}")
    return 0


def cmd_update(args: argparse.Namespace, svc: BudgetService) -> int:
    changes: dict[str, object] = {}
    if args.date is not None:
        changes["date"] = parse_date(args.date)
    if args.type is not None:
        changes["type"] = parse_type(args.type)
    if args.category is not None:
        changes["category"] = parse_category_name(args.category)
    if args.amount is not None:
        changes["amount"] = parse_amount(args.amount)
    if args.memo is not None:
        changes["memo"] = args.memo.strip()
    if args.tags is not None:
        changes["tags"] = parse_tags(args.tags)
    if not changes:
        raise AppError("수정할 필드가 없습니다.", "예: update --id TX-000001 --amount 20000")
    tx = svc.update_transaction(args.id, **changes)
    print(f"[수정 완료] {format_table([tx])}")
    return 0


def cmd_delete(args: argparse.Namespace, svc: BudgetService) -> int:
    svc.delete_transaction(args.id)
    print(f"[삭제 완료] id={args.id}")
    return 0


def cmd_export(args: argparse.Namespace, svc: BudgetService) -> int:
    if not args.month and not (args.date_from and args.date_to):
        raise AppError(
            "export 는 --month 또는 --from과 --to가 모두 필요합니다.",
            "예: export --out out.csv --month 2024-01",
        )
    out = Path(args.out)
    count = svc.export_csv(out, filter_from_args(args))
    print(f"[완료] {out} ({count} records)")
    return 0


def cmd_import(args: argparse.Namespace, svc: BudgetService) -> int:
    result = svc.import_csv(Path(args.src))
    print(f"[완료] imported={result.imported}, skipped={result.skipped}")
    for err in result.errors:
        print(f"[오류] {err}")
    if result.skipped:
        print("[힌트] 표시된 행의 날짜·타입·카테고리·금액을 CSV 스키마에 맞게 수정하세요.")
    return 1 if result.skipped else 0


def cmd_backup(args: argparse.Namespace, svc: BudgetService) -> int:
    copied = svc.backup()
    if not copied:
        print("[완료] 백업할 파일이 없습니다.")
        return 0
    print(f"[완료] {copied[0].parent} 에 {len(copied)}개 파일 백업")
    return 0
