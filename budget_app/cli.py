"""CLI 계층. 인자 파싱, 대화형 입력, 화면 출력을 담당한다."""

from __future__ import annotations

import argparse
import calendar
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

from budget_app import __version__
from budget_app.decorators import handle_errors, log_call
from budget_app.models import (
    AppError,
    Summary,
    Transaction,
    parse_amount,
    parse_category_name,
    parse_date,
    parse_month,
    parse_tags,
    parse_type,
)
from budget_app.services import BudgetService, SearchFilter

DEFAULT_DATA_DIR = Path("./data")
DEFAULT_LIST_LIMIT = 20
DEFAULT_TOP = 5

T = TypeVar("T")


# ---------------------------------------------------------------- 입력 도우미


def ask(prompt: str, parser: Callable[[str], T], optional: bool = False) -> T | None:
    """유효한 값이 들어올 때까지 반복해서 묻는다. optional이면 빈 입력에 None."""
    while True:
        raw = input(prompt)
        if optional and not raw.strip():
            return None
        try:
            return parser(raw)
        except AppError as exc:
            print(f"[오류] {exc.message}")
            if exc.hint:
                print(f"[힌트] {exc.hint}")


def ask_category(svc: BudgetService, prompt: str = "카테고리: ") -> str:
    def check(text: str) -> str:
        return svc.require_category(parse_category_name(text))

    result = ask(prompt, check)
    assert result is not None
    return result


# ---------------------------------------------------------------- 출력 도우미


def format_table(txs: Sequence[Transaction]) -> str:
    """외부 라이브러리 없이 열 너비를 맞춰 정렬한다."""
    if not txs:
        return "(거래 없음)"
    cat_w = max(len(tx.category) for tx in txs)
    amt_w = max(len(f"{tx.amount:,}") for tx in txs)
    lines = []
    for tx in txs:
        tags = f" #{' #'.join(tx.tags)}" if tx.tags else ""
        lines.append(
            f"{tx.id} | {tx.date} | {tx.type:<7} | {tx.category:<{cat_w}} | "
            f"{tx.amount:>{amt_w},} | {tx.memo}{tags}"
        )
    return "\n".join(lines)


def format_summary(s: Summary) -> str:
    lines = [
        f"[{s.month} 요약] 거래 {s.count}건",
        f"총 수입: {s.total_income:,}원",
        f"총 지출: {s.total_expense:,}원",
        f"잔액: {s.balance:,}원",
    ]
    if s.count == 0:
        lines.insert(1, f"{s.month}: 데이터 없음")
    if s.budget is not None:
        usage = s.budget_usage or 0.0
        lines.append(f"예산: {s.budget:,}원 (사용률 {usage:.1f}%)")
        if s.over_budget:
            lines.append(f"[경고] 예산을 {s.total_expense - s.budget:,}원 초과했습니다!")
    if s.top_expenses:
        lines.append("")
        lines.append(f"지출 TOP {len(s.top_expenses)}")
        for rank, (category, amount) in enumerate(s.top_expenses, start=1):
            lines.append(f"{rank}) {category} {amount:,}원")
    return "\n".join(lines)


# ---------------------------------------------------------------- 명령 처리


def cmd_add(args: argparse.Namespace, svc: BudgetService) -> int:
    date = ask("날짜(YYYY-MM-DD): ", parse_date)
    type_ = ask("타입(income/expense): ", parse_type)
    category = ask_category(svc)
    amount = ask("금액(양수): ", parse_amount)
    memo = input("메모(선택): ").strip()
    tags = parse_tags(input("태그(쉼표로 구분, 없으면 엔터): "))
    assert date and type_ and amount
    tx = svc.add_transaction(date, type_, category, amount, memo, tags)
    print(f"[저장 완료] id={tx.id}")
    return 0


def cmd_list(args: argparse.Namespace, svc: BudgetService) -> int:
    if args.limit <= 0:
        raise AppError("--limit 은 1 이상이어야 합니다.", "예: --limit 10")
    print(format_table(svc.list_latest(args.limit)))
    return 0


def _filter_from_args(args: argparse.Namespace) -> SearchFilter:
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
        flt.date_from = max(flt.date_from or f"{month}-01", f"{month}-01")
        month_end = f"{month}-{last_day:02d}"
        flt.date_to = min(flt.date_to or month_end, month_end)
    if flt.date_from and flt.date_to and flt.date_from > flt.date_to:
        raise AppError("--from 이 --to 보다 늦습니다.", "기간을 다시 확인하세요.")
    return flt


@log_call
def cmd_search(args: argparse.Namespace, svc: BudgetService) -> int:
    count = 0
    for tx in svc.iter_search(_filter_from_args(args)):
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
    assert name
    svc.add_category(name)
    print(f"[저장 완료] category={name}")
    return 0


def cmd_category_list(args: argparse.Namespace, svc: BudgetService) -> int:
    for name in svc.list_categories():
        print(f"- {name}")
    return 0


def cmd_category_remove(args: argparse.Namespace, svc: BudgetService) -> int:
    name = parse_category_name(args.name) if args.name else ask("삭제할 카테고리명: ", parse_category_name)
    assert name
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
    count = svc.export_csv(out, _filter_from_args(args))
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


# ---------------------------------------------------------------- 파서 구성


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, f"[오류] {message}\n[힌트] {self.prog} --help로 사용법을 확인하세요.\n")


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
        prog="python -m budget_app",
        description="나만의 용돈 기입장 - 파일 기반 콘솔 가계부",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--data-dir", default=str(DEFAULT_DATA_DIR), metavar="DIR",
        help=f"저장 폴더 (기본: {DEFAULT_DATA_DIR})",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    p = sub.add_parser("add", help="거래 추가 (대화형)")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="최신순 거래 목록")
    p.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT, help=f"출력 건수 (기본 {DEFAULT_LIST_LIMIT})")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="조건 검색 (최신순)")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="시작일")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="종료일")
    p.add_argument("--category", help="카테고리")
    p.add_argument("--type", choices=("income", "expense"), help="타입")
    p.add_argument("--q", metavar="KEYWORD", help="메모 키워드 (대소문자 무시)")
    p.add_argument("--tag", help="태그")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("summary", help="월별 요약")
    p.add_argument("--month", required=True, metavar="YYYY-MM")
    p.add_argument("--top", type=int, default=DEFAULT_TOP, help=f"카테고리 TOP N (기본 {DEFAULT_TOP})")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("budget", help="월 예산 설정/조회")
    bsub = p.add_subparsers(dest="subcommand", metavar="<set|show>", required=True)
    q = bsub.add_parser("set", help="예산 설정")
    q.add_argument("--month", required=True, metavar="YYYY-MM")
    q.add_argument("--amount", required=True, metavar="금액")
    q.set_defaults(func=cmd_budget_set)
    q = bsub.add_parser("show", help="예산 조회")
    q.add_argument("--month", required=True, metavar="YYYY-MM")
    q.set_defaults(func=cmd_budget_show)

    p = sub.add_parser("category", help="카테고리 관리")
    csub = p.add_subparsers(dest="subcommand", metavar="<add|list|remove>", required=True)
    q = csub.add_parser("add", help="카테고리 추가 (이름 생략 시 대화형)")
    q.add_argument("name", nargs="?", help="카테고리명")
    q.set_defaults(func=cmd_category_add)
    q = csub.add_parser("list", help="카테고리 목록")
    q.set_defaults(func=cmd_category_list)
    q = csub.add_parser("remove", help="카테고리 삭제 (사용 중이면 --replace 필요)")
    q.add_argument("name", nargs="?", help="카테고리명")
    q.add_argument("--replace", metavar="CATEGORY", help="사용 중인 거래를 옮길 대체 카테고리")
    q.set_defaults(func=cmd_category_remove)

    p = sub.add_parser("update", help="거래 수정 (옵션 기반)")
    p.add_argument("--id", required=True, help="거래 id")
    p.add_argument("--date", metavar="YYYY-MM-DD")
    p.add_argument("--type", choices=("income", "expense"))
    p.add_argument("--category")
    p.add_argument("--amount")
    p.add_argument("--memo")
    p.add_argument("--tags", help="쉼표로 구분")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", help="거래 삭제")
    p.add_argument("--id", required=True, help="거래 id")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("export", help="CSV 내보내기 (--month 또는 --from/--to 필수)")
    p.add_argument("--out", required=True, metavar="CSV", help="출력 파일")
    p.add_argument("--month", metavar="YYYY-MM")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import", help="CSV 가져오기")
    p.add_argument("--from", dest="src", required=True, metavar="CSV", help="입력 파일")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("backup", help="저장 파일 백업 (data/backups/<timestamp>/)")
    p.set_defaults(func=cmd_backup)

    return parser


def setup_logging(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=data_dir / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


@handle_errors
def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_dir = Path(args.data_dir)
    setup_logging(data_dir)
    svc = BudgetService(data_dir)
    created = svc.initialize()
    if created:
        print(f"[초기화] {data_dir} 에 저장 파일을 생성했습니다: {', '.join(created)}")
    return args.func(args, svc)
