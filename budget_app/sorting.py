"""JSONL 임시 파일을 병합해 거래를 제한된 메모리로 최신순 정렬한다."""

from __future__ import annotations

import heapq
import json
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import closing
from itertools import islice
from pathlib import Path

from budget_app.models import Transaction
from budget_app.storage import JsonlFile, TransactionRepository


def transaction_key(tx: Transaction) -> tuple[str, int]:
    return tx.date, TransactionRepository.parse_id(tx.id)


def iter_latest(txs: Iterable[Transaction], chunk_size: int = 1000) -> Iterator[Transaction]:
    """청크별 정렬 후 두 파일씩 병합한다. 동시에 여는 입력 파일은 최대 2개다."""
    if chunk_size <= 0:
        raise ValueError("chunk_size는 양수여야 합니다.")
    with tempfile.TemporaryDirectory(prefix="budget-sort-") as tmp:
        serial = 0

        def write_run(rows: Iterable[Transaction]) -> Path:
            nonlocal serial
            path = Path(tmp) / f"{serial}.jsonl"
            serial += 1
            with path.open("w", encoding="utf-8") as fp:
                for tx in rows:
                    fp.write(json.dumps(tx.to_dict(), ensure_ascii=False) + "\n")
            return path

        def merge(left: Path, right: Path) -> Path:
            with closing(JsonlFile(left).iter_rows(Transaction.from_dict)) as a, \
                    closing(JsonlFile(right).iter_rows(Transaction.from_dict)) as b:
                result = write_run(heapq.merge(a, b, key=transaction_key, reverse=True))
            left.unlink()
            right.unlink()
            return result

        # 같은 크기의 정렬 묶음끼리 합쳐 임시 파일 수도 로그 규모로 제한한다.
        levels: list[Path | None] = []
        source = iter(txs)
        while chunk := list(islice(source, chunk_size)):
            run = write_run(sorted(chunk, key=transaction_key, reverse=True))
            level = 0
            while level < len(levels) and levels[level] is not None:
                run = merge(levels[level], run)
                levels[level] = None
                level += 1
            if level == len(levels):
                levels.append(run)
            else:
                levels[level] = run

        result: Path | None = None
        for run in reversed(levels):
            if run is not None:
                result = run if result is None else merge(result, run)
        if result is not None:
            with closing(JsonlFile(result).iter_rows(Transaction.from_dict)) as rows:
                yield from rows
