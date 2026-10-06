"""진입점. 파서를 만들고 서비스를 초기화한 뒤 명령 핸들러에 넘긴다."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from budget_app.cli.parser import build_parser
from budget_app.decorators import handle_errors
from budget_app.services import BudgetService


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
