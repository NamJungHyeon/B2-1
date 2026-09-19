"""외부 정렬의 순서, 메모리 상한과 임시 파일 정리를 검증한다."""

from __future__ import annotations

import tempfile
import tracemalloc
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from budget_app.models import Transaction
from budget_app.sorting import iter_latest


class SortingTest(unittest.TestCase):
    def test_merges_multiple_levels_and_handles_empty_input(self) -> None:
        rows = [
            Transaction('TX-000001', 'expense', '2024-01-03', 1, 'food'),
            Transaction('TX-999999', 'expense', '2024-01-01', 1, 'food'),
            Transaction('TX-000003', 'expense', '2024-01-02', 1, 'food'),
            Transaction('TX-1000000', 'expense', '2024-01-01', 1, 'food'),
            Transaction('TX-000005', 'expense', '2024-01-03', 1, 'food'),
        ]
        self.assertEqual([tx.id for tx in iter_latest(rows, chunk_size=1)],
                         ['TX-000005', 'TX-000001', 'TX-000003', 'TX-1000000', 'TX-999999'])
        self.assertEqual(list(iter_latest([])), [])

    def test_temp_files_removed_when_reader_stops_or_source_fails(self) -> None:
        real_directory = tempfile.TemporaryDirectory
        with real_directory() as root:
            def directory(**kwargs: str) -> tempfile.TemporaryDirectory:
                return real_directory(dir=root, **kwargs)

            with patch('budget_app.sorting.tempfile.TemporaryDirectory', side_effect=directory):
                row = Transaction('TX-000001', 'expense', '2024-01-01', 1, 'food')
                result = iter_latest([row, row], chunk_size=1)
                self.assertEqual(next(result).id, 'TX-000001')
                result.close()
                self.assertEqual(list(Path(root).iterdir()), [])

                def broken_source() -> Iterator[Transaction]:
                    yield row
                    raise OSError('read interrupted')

                with self.assertRaises(OSError):
                    list(iter_latest(broken_source(), chunk_size=1))
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_memory_does_not_grow_with_total_result_size(self) -> None:
        def peak_for(count: int) -> int:
            tracemalloc.start()
            try:
                rows = (
                    Transaction(f'TX-{i:06d}', 'expense', '2024-01-01', i, 'food',
                                memo=str(i) + 'x' * 2000)
                    for i in range(1, count + 1)
                )
                consumed = sum(1 for _ in iter_latest(rows, chunk_size=20))
                self.assertEqual(consumed, count)
                return tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()

        small = peak_for(100)
        large = peak_for(1000)
        # 전체 결과를 보관하면 약 2 MB 증가한다. 버퍼와 경로의 소폭 증가는 허용한다.
        self.assertLess(large, small + 500_000)
