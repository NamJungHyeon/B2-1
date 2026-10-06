"""argparse 파서 구성. 각 서브커맨드는 commands 모듈의 핸들러에 연결된다."""

from __future__ import annotations

import argparse
from pathlib import Path

from budget_app import __version__
from budget_app.cli import commands as c
from budget_app.validators import TRANSACTION_TYPES

DEFAULT_DATA_DIR = Path("./data")
DEFAULT_LIST_LIMIT = 20
DEFAULT_TOP = 5


class ArgumentParser(argparse.ArgumentParser):
    """argparse 기본 오류 문구 대신 [오류]/[힌트] 형식으로 출력한다."""

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

    _add_transaction_commands(sub)
    _add_report_commands(sub)
    _add_budget_commands(sub)
    _add_category_commands(sub)
    _add_io_commands(sub)
    return parser


def _add_transaction_commands(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("add", help="거래 추가 (대화형)")
    p.set_defaults(func=c.cmd_add)

    p = sub.add_parser("update", help="거래 수정 (옵션 기반)")
    p.add_argument("--id", required=True, help="거래 id")
    p.add_argument("--date", metavar="YYYY-MM-DD")
    p.add_argument("--type", choices=TRANSACTION_TYPES)
    p.add_argument("--category")
    p.add_argument("--amount")
    p.add_argument("--memo")
    p.add_argument("--tags", help="쉼표로 구분")
    p.set_defaults(func=c.cmd_update)

    p = sub.add_parser("delete", help="거래 삭제")
    p.add_argument("--id", required=True, help="거래 id")
    p.set_defaults(func=c.cmd_delete)


def _add_report_commands(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("list", help="최신순 거래 목록")
    p.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT, help=f"출력 건수 (기본 {DEFAULT_LIST_LIMIT})")
    p.set_defaults(func=c.cmd_list)

    p = sub.add_parser("search", help="조건 검색 (최신순)")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="시작일")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="종료일")
    p.add_argument("--category", help="카테고리")
    p.add_argument("--type", choices=TRANSACTION_TYPES, help="타입")
    p.add_argument("--q", metavar="KEYWORD", help="메모 키워드 (대소문자 무시)")
    p.add_argument("--tag", help="태그")
    p.set_defaults(func=c.cmd_search)

    p = sub.add_parser("summary", help="월별 요약")
    p.add_argument("--month", required=True, metavar="YYYY-MM")
    p.add_argument("--top", type=int, default=DEFAULT_TOP, help=f"카테고리 TOP N (기본 {DEFAULT_TOP})")
    p.set_defaults(func=c.cmd_summary)


def _add_budget_commands(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("budget", help="월 예산 설정/조회")
    bsub = p.add_subparsers(dest="subcommand", metavar="<set|show>", required=True)
    q = bsub.add_parser("set", help="예산 설정")
    q.add_argument("--month", required=True, metavar="YYYY-MM")
    q.add_argument("--amount", required=True, metavar="금액")
    q.set_defaults(func=c.cmd_budget_set)
    q = bsub.add_parser("show", help="예산 조회")
    q.add_argument("--month", required=True, metavar="YYYY-MM")
    q.set_defaults(func=c.cmd_budget_show)


def _add_category_commands(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("category", help="카테고리 관리")
    csub = p.add_subparsers(dest="subcommand", metavar="<add|list|remove>", required=True)
    q = csub.add_parser("add", help="카테고리 추가 (이름 생략 시 대화형)")
    q.add_argument("name", nargs="?", help="카테고리명")
    q.set_defaults(func=c.cmd_category_add)
    q = csub.add_parser("list", help="카테고리 목록")
    q.set_defaults(func=c.cmd_category_list)
    q = csub.add_parser("remove", help="카테고리 삭제 (사용 중이면 --replace 필요)")
    q.add_argument("name", nargs="?", help="카테고리명")
    q.add_argument("--replace", metavar="CATEGORY", help="사용 중인 거래를 옮길 대체 카테고리")
    q.set_defaults(func=c.cmd_category_remove)


def _add_io_commands(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("export", help="CSV 내보내기 (--month 또는 --from/--to 필수)")
    p.add_argument("--out", required=True, metavar="CSV", help="출력 파일")
    p.add_argument("--month", metavar="YYYY-MM")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    p.set_defaults(func=c.cmd_export)

    p = sub.add_parser("import", help="CSV 가져오기")
    p.add_argument("--from", dest="src", required=True, metavar="CSV", help="입력 파일")
    p.set_defaults(func=c.cmd_import)

    p = sub.add_parser("backup", help="저장 파일 백업 (data/backups/<timestamp>/)")
    p.set_defaults(func=c.cmd_backup)
