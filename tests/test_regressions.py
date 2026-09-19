import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from budget_app.models import AppError, parse_amount, parse_month
from budget_app.services import BudgetService, SearchFilter


class InputRegressionTest(unittest.TestCase):
    def test_invalid_amounts_are_application_errors(self):
        for value in ('²', '1,2', ',100', '100,'):
            with self.subTest(value=value[:20]), self.assertRaises(AppError):
                parse_amount(value)

    @unittest.skipUnless(getattr(sys, "get_int_max_str_digits", lambda: 0)(),
                         "런타임 정수 변환 길이 제한이 없는 환경")
    def test_runtime_integer_limit_is_application_error(self):
        with self.assertRaises(AppError):
            parse_amount('9' * (sys.get_int_max_str_digits() + 1))

    def test_month_requires_real_year(self):
        with self.assertRaises(AppError):
            parse_month('0000-01')
        self.assertEqual(parse_month(' 2024-02 '), '2024-02')


class FileRegressionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.svc = BudgetService(self.root)
        self.svc.initialize()
        self.tx = self.svc.add_transaction('2024-01-01', 'expense', 'food', 100)

    def test_cli_reports_corrupt_storage_without_traceback(self):
        self.svc.transactions.file.path.write_text('{}\n', encoding='utf-8')
        result = subprocess.run(
            [sys.executable, '-m', 'budget_app', '--data-dir', str(self.root), 'list'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('transactions.jsonl', result.stdout)
        self.assertNotIn('Traceback', result.stderr)

    def test_rewrite_failure_preserves_original_and_cleans_temp(self):
        file = self.svc.transactions.file
        original = file.path.read_bytes()

        def rows():
            yield self.tx.to_dict()
            raise OSError('write interrupted')

        with self.assertRaises(OSError):
            file.rewrite_rows(rows())
        self.assertEqual(file.path.read_bytes(), original)
        self.assertEqual(list(self.root.glob('.*.tmp')), [])

    def test_export_cannot_overwrite_storage_or_aliases(self):
        for name in ('transactions.jsonl', 'categories.jsonl', 'budgets.jsonl', 'app.log'):
            source = self.root / name
            source.touch(exist_ok=True)
            alias = self.root / (name + '.csv')
            alias.symlink_to(source)
            before = source.read_bytes()
            for target in (source, alias):
                with self.subTest(target=target), self.assertRaises(AppError):
                    self.svc.export_csv(target, SearchFilter())
                self.assertEqual(source.read_bytes(), before)

    def test_failed_export_preserves_existing_output(self):
        out = self.root / 'out.csv'
        out.write_text('previous export', encoding='utf-8')
        self.svc.transactions.file.path.write_text('{broken\n', encoding='utf-8')
        with self.assertRaises(AppError):
            self.svc.export_csv(out, SearchFilter())
        self.assertEqual(out.read_text(), 'previous export')
        self.assertEqual(list(self.root.glob('.*.tmp')), [])

    def test_backups_at_same_time_are_independent(self):
        with patch('budget_app.storage.datetime') as clock:
            clock.now.return_value = datetime(2024, 1, 1)
            first = self.svc.backup()
            original = first[0].read_bytes()
            self.svc.add_transaction('2024-01-02', 'expense', 'food', 200)
            second = self.svc.backup()
        self.assertNotEqual(first[0].parent, second[0].parent)
        self.assertEqual(first[0].read_bytes(), original)
        self.assertNotEqual(second[0].read_bytes(), original)

    def test_sorting_handles_ids_above_six_digits(self):
        row = self.tx.to_dict()
        self.svc.transactions.file.rewrite_rows(
            dict(row, id=identifier) for identifier in ('TX-999999', 'TX-1000000')
        )
        self.assertEqual(self.svc.list_latest(1)[0].id, 'TX-1000000')
        self.assertEqual(self.svc.search(SearchFilter())[0].id, 'TX-1000000')

    def test_malformed_storage_has_filename_and_line_number(self):
        for name, values, read in (
            ('transactions.jsonl', [[], {}, *(dict(self.tx.to_dict(), **change) for change in (
                 {'amount': None}, {'amount': -1}, {'amount': 1.5}, {'amount': True},
                 {'id': 'bad'}, {'date': '2024-02-30'}, {'type': 'bad'},
                 {'tags': 'abc'}, {'tags': [1]}, {'memo': None}))],
             lambda: self.svc.list_latest(10)),
            ('categories.jsonl', [[], {}, {'name': None}, {'name': ''}], self.svc.list_categories),
            ('budgets.jsonl', [[], {'month': '2024-01', 'amount': None},
                               {'month': '2024-01', 'amount': -1}],
             lambda: self.svc.budgets.get('2024-01')),
        ):
            for value in values:
                with self.subTest(name=name, value=value):
                    (self.root / name).write_text('\n' + json.dumps(value) + '\n')
                    with self.assertRaises(AppError) as caught:
                        read()
                    self.assertIn(name, str(caught.exception))
                    self.assertIn('2', str(caught.exception))
