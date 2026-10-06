"""JSONL 파일 하나에 대한 저수준 읽기/쓰기와 원자적 교체."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO, TypeVar

from budget_app.errors import AppError

T = TypeVar("T")


@contextmanager
def atomic_text_writer(path: Path) -> Iterator[TextIO]:
    """쓰기 성공 시에만 대상 파일을 교체하고 실패 시 임시 파일을 정리한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fp:
            yield fp
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class JsonlFile:
    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure(self) -> bool:
        """파일이 없으면 빈 파일을 만든다. 새로 만들었으면 True."""
        if self.path.exists():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        return True

    def iter_rows(self, decode: Callable[[dict[str, Any]], T] = dict) -> Iterator[T]:
        """한 줄씩 읽고 변환하며, 손상된 행은 파일명과 줄 번호로 알린다."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fp:
            for line_no, line in enumerate(fp, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("JSON 객체가 필요합니다.")
                    value = decode(row)
                except (ValueError, TypeError, KeyError, AppError):
                    raise AppError(
                        f"{self.path.name} {line_no}번째 줄이 손상되었습니다.",
                        "해당 줄을 직접 수정하거나 백업에서 복구하세요.",
                    ) from None
                yield value

    def append_row(self, row: dict[str, Any]) -> None:
        self.ensure()
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    def rewrite_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        """임시 파일에 모두 쓴 뒤 rename으로 교체한다 (원자적 쓰기)."""
        with atomic_text_writer(self.path) as fp:
            for row in rows:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
