"""과제 요구사항을 실제 CLI와 파일 입출력으로 검증한다."""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from budget_app.models import Transaction
from budget_app.services import BudgetService, SearchFilter


class RequirementsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data'

    def cli(self, *args: str, input: str = '', code: int = 0) -> str:
        result = subprocess.run(
            [sys.executable, '-m', 'budget_app', '--data-dir', str(self.data), *args],
            input=input, capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, code, output)
        self.assertNotIn('Traceback', output)
        return output

    def add(self, date: str = '2024-01-01', amount: int = 100) -> str:
        return self.cli('add', input=f'{date}\nexpense\nfood\n{amount}\n점심\nmeal\n')

    def test_all_commands_provide_help(self) -> None:
        commands = [(), ('add',), ('list',), ('search',), ('summary',), ('budget',),
                    ('budget', 'set'), ('budget', 'show'), ('category',),
                    ('category', 'add'), ('category', 'list'), ('category', 'remove'),
                    ('update',), ('delete',), ('import',), ('export',), ('backup',)]
        for command in commands:
            with self.subTest(command=command):
                self.assertIn('usage:', self.cli(*command, '--help'))
        self.assertFalse(self.data.exists())

    def test_interactive_validation_and_persistence(self) -> None:
        output = self.cli('add', input=(
            '2024-02-30\n2024-01-01\ninvalid\nexpense\nghost\nfood\n'
            '0\n-1\n100\n점심\nmeal,meal,lunch\n'
        ))
        self.assertIn('TX-000001', output)
        self.assertGreaterEqual(output.count('[오류]'), 5)
        self.assertGreaterEqual(output.count('[힌트]'), 5)
        for name in ('transactions.jsonl', 'categories.jsonl', 'budgets.jsonl'):
            self.assertTrue((self.data / name).is_file())
        output = self.cli('list', '--limit', '1')
        self.assertIn('점심 #meal #lunch', output)
        self.assertIn('100', output)
        self.assertIn('add_transaction', (self.data / 'app.log').read_text())

    def test_crud_search_category_and_budget(self) -> None:
        self.add()
        self.add('2024-01-02', 200)
        self.cli('category', 'add', input='snack\n')
        self.assertIn('snack', self.cli('category', 'list'))
        self.cli('update', '--id', 'TX-000001', '--amount', '150', '--memo', '수정',
                 '--category', 'snack', '--tags', 'changed')
        output = self.cli('search', '--from', '2024-01-01', '--to', '2024-01-31',
                          '--category', 'snack', '--type', 'expense', '--q', '수정',
                          '--tag', 'changed')
        self.assertIn('TX-000001', output)
        self.assertNotIn('TX-000002', output)
        output = self.cli('search')
        self.assertLess(output.index('TX-000002'), output.index('TX-000001'))
        self.cli('budget', 'set', '--month', '2024-01', '--amount', '100')
        self.assertIn('100', self.cli('budget', 'show', '--month', '2024-01'))
        output = self.cli('summary', '--month', '2024-01', '--top', '1')
        for text in ('총 지출: 350원', '잔액: -350원', '350.0%', '[경고]', 'food 200원'):
            self.assertIn(text, output)
        self.cli('category', 'remove', 'snack', code=1)
        self.cli('category', 'remove', 'snack', '--replace', 'etc')
        self.assertIn('etc', self.cli('search', '--q', '수정'))
        self.cli('delete', '--id', 'TX-000001')
        self.assertNotIn('TX-000001', self.cli('list'))
        self.cli('delete', '--id', 'TX-000001', code=1)
        self.cli('update', '--id', 'TX-000001', '--amount', '1', code=1)

    def test_empty_month_still_shows_budget_usage(self) -> None:
        self.cli('budget', 'set', '--month', '2024-02', '--amount', '500')
        output = self.cli('summary', '--month', '2024-02')
        for text in ('데이터 없음', '총 수입: 0원', '총 지출: 0원', '잔액: 0원', '0.0%'):
            self.assertIn(text, output)
        self.assertNotIn('[경고]', output)

    def test_export_requires_month_or_complete_range(self) -> None:
        out = str(self.root / 'out.csv')
        for filters in ((), ('--from', '2024-01-01'), ('--to', '2024-01-31')):
            with self.subTest(filters=filters):
                output = self.cli('export', '--out', out, *filters, code=1)
                self.assertIn('[힌트]', output)
                self.assertFalse(Path(out).exists())

    def test_export_combined_filters_are_intersected(self) -> None:
        self.add('2024-02-01')
        self.add('2024-02-29', 200)
        self.add('2024-03-01', 300)
        out = self.root / 'out.csv'
        self.cli('export', '--out', str(out), '--month', '2024-02',
                 '--from', '2024-02-15', '--to', '2024-03-01')
        with out.open(encoding='utf-8', newline='') as fp:
            rows = list(csv.DictReader(fp))
        self.assertEqual([row['date'] for row in rows], ['2024-02-29'])
        self.assertIn('imported=1', self.cli('import', '--from', str(out)))
        self.cli('export', '--out', str(out), '--month', '2024-02',
                 '--from', '2024-03-01', code=1)

    def test_argument_errors_include_reason_and_hint(self) -> None:
        output = self.cli('list', '--limit', 'abc', code=2)
        self.assertIn('[오류]', output)
        self.assertIn('[힌트]', output)

    def test_invalid_utf8_is_reported_without_traceback(self) -> None:
        src = self.root / 'bad.csv'
        src.write_bytes(b'\xff')
        output = self.cli('import', '--from', str(src), code=1)
        self.assertIn('[오류]', output)
        self.assertIn('[힌트]', output)

    def test_fatal_csv_error_does_not_partially_import(self) -> None:
        self.add()
        before = (self.data / 'transactions.jsonl').read_bytes()
        src = self.root / 'bad.csv'
        # 앞 행은 버퍼에 쓰일 만큼 크지만 CSV 필드 길이 제한 이내다.
        src.write_text('date,type,category,amount,memo\n'
                       '2024-01-01,expense,food,100,' + 'x' * 10000 + '\n'
                       '2024-01-02,expense,food,100,"unterminated\n', encoding='utf-8')
        output = self.cli('import', '--from', str(src), code=1)
        self.assertIn('[힌트]', output)
        self.assertEqual((self.data / 'transactions.jsonl').read_bytes(), before)

    def test_streamed_search_large_result_is_sorted(self) -> None:
        svc = BudgetService(self.data)
        svc.initialize()
        svc.transactions.add_many(
            Transaction(f'TX-{i:06d}', 'expense', '2024-01-01', i, 'food')
            for i in range(1, 2501)
        )
        output = self.cli('search', '--category', 'food')
        ids = [line.split(' | ')[0] for line in output.splitlines() if line.startswith('TX-')]
        self.assertEqual(len(ids), 2500)
        self.assertEqual(ids[0], 'TX-002500')
        self.assertEqual(ids[-1], 'TX-000001')
        self.assertIn('(2500건)', output)
        self.assertEqual(next(svc.iter_search(SearchFilter())).id, 'TX-002500')

    def test_invalid_import_rows_report_nonzero_status_and_hint(self) -> None:
        self.add()
        src = self.root / 'mixed.csv'
        src.write_text('date,type,category,amount\n'
                       '2024-01-01,expense,food,100\n'
                       '2024-01-01,expense,ghost,100\n', encoding='utf-8')
        output = self.cli('import', '--from', str(src), code=1)
        self.assertIn('imported=1, skipped=1', output)
        self.assertIn('[힌트]', output)
        self.assertIn('3행', output)
