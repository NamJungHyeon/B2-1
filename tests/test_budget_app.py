"""핵심 동작 검증. 실행: python3 -m unittest -v"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from budget_app.errors import AppError
from budget_app.validators import parse_amount, parse_date, parse_tags, parse_type
from budget_app.services import BudgetService, SearchFilter


class ValidationTest(unittest.TestCase):
    def test_parse_date(self) -> None:
        self.assertEqual(parse_date(" 2024-01-15 "), "2024-01-15")
        for bad in ("2024-13-40", "20240115", "abc"):
            with self.assertRaises(AppError):
                parse_date(bad)

    def test_parse_amount(self) -> None:
        self.assertEqual(parse_amount("15,000"), 15000)
        for bad in ("0", "-5", "1.5", "abc"):
            with self.assertRaises(AppError):
                parse_amount(bad)

    def test_parse_type_and_tags(self) -> None:
        self.assertEqual(parse_type("Expense"), "expense")
        with self.assertRaises(AppError):
            parse_type("transfer")
        self.assertEqual(parse_tags(" a, b ,,a"), ["a", "b"])
        self.assertEqual(parse_tags(None), [])


class ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "data"
        self.svc = BudgetService(self.data_dir)
        self.svc.initialize()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def add(self, date: str, type_: str, category: str, amount: int, memo: str = "", tags: list[str] | None = None):
        return self.svc.add_transaction(date, type_, category, amount, memo, tags)

    def test_initialize_creates_three_files_and_default_categories(self) -> None:
        for name in ("transactions.jsonl", "categories.jsonl", "budgets.jsonl"):
            self.assertTrue((self.data_dir / name).exists(), name)
        self.assertIn("food", self.svc.list_categories())

    def test_add_assigns_sequential_ids(self) -> None:
        a = self.add("2024-01-01", "expense", "food", 100)
        b = self.add("2024-01-02", "income", "salary", 200)
        self.assertEqual((a.id, b.id), ("TX-000001", "TX-000002"))

    def test_add_rejects_unknown_category(self) -> None:
        with self.assertRaises(AppError):
            self.add("2024-01-01", "expense", "nope", 100)

    def test_list_latest_is_sorted_desc_and_limited(self) -> None:
        self.add("2024-01-05", "expense", "food", 1)
        self.add("2024-01-01", "expense", "food", 2)
        self.add("2024-01-09", "expense", "food", 3)
        self.add("2024-01-09", "expense", "food", 4)  # 같은 날짜면 id가 큰 쪽이 먼저
        latest = self.svc.list_latest(2)
        self.assertEqual([tx.amount for tx in latest], [4, 3])

    def test_update_and_delete_preserve_other_rows(self) -> None:
        a = self.add("2024-01-01", "expense", "food", 100, "a")
        b = self.add("2024-01-02", "expense", "food", 200, "b")
        c = self.add("2024-01-03", "expense", "food", 300, "c")
        self.svc.update_transaction(b.id, amount=250, tags=["x"])
        self.svc.delete_transaction(a.id)
        rows = {tx.id: tx for tx in self.svc.transactions.iter_all()}
        self.assertEqual(set(rows), {b.id, c.id})
        self.assertEqual(rows[b.id].amount, 250)
        self.assertEqual(rows[b.id].tags, ["x"])
        self.assertEqual(rows[c.id].memo, "c")
        # 임시 파일이 남아 있지 않아야 한다
        self.assertEqual([p.name for p in self.data_dir.glob("*.tmp")], [])

    def test_update_delete_missing_id(self) -> None:
        with self.assertRaises(AppError):
            self.svc.update_transaction("TX-000099", amount=1)
        with self.assertRaises(AppError):
            self.svc.delete_transaction("TX-000099")

    def test_search_filters(self) -> None:
        self.add("2024-01-01", "expense", "food", 100, "점심", ["meal"])
        self.add("2024-01-15", "income", "salary", 900, "월급")
        self.add("2024-02-01", "expense", "rent", 500, "월세", ["fixed"])
        self.assertEqual(len(self.svc.search(SearchFilter(date_from="2024-01-10", date_to="2024-01-31"))), 1)
        self.assertEqual(len(self.svc.search(SearchFilter(type="expense"))), 2)
        self.assertEqual(len(self.svc.search(SearchFilter(category="rent"))), 1)
        self.assertEqual(len(self.svc.search(SearchFilter(keyword="월"))), 2)
        self.assertEqual(len(self.svc.search(SearchFilter(tag="meal"))), 1)

    def test_summary_with_budget(self) -> None:
        self.add("2024-01-01", "expense", "food", 30000)
        self.add("2024-01-02", "expense", "rent", 50000)
        self.add("2024-01-03", "income", "salary", 100000)
        self.add("2024-02-01", "expense", "food", 999)
        self.assertEqual(self.svc.summary("2023-12", 3).count, 0)
        s = self.svc.summary("2024-01", 1)
        self.assertEqual((s.total_income, s.total_expense, s.balance), (100000, 80000, 20000))
        self.assertEqual(s.top_expenses, [("rent", 50000)])
        self.assertIsNone(s.budget)
        self.svc.set_budget("2024-01", 60000)
        self.svc.set_budget("2024-01", 70000)  # 덮어쓰기
        s = self.svc.summary("2024-01", 1)
        self.assertEqual(s.budget, 70000)
        self.assertTrue(s.over_budget)
        self.assertAlmostEqual(s.budget_usage or 0, 114.2857, places=3)

    def test_remove_category_in_use_requires_replacement(self) -> None:
        self.add("2024-01-01", "expense", "food", 1)
        with self.assertRaises(AppError):
            self.svc.remove_category("food")
        moved = self.svc.remove_category("food", replace_with="etc")
        self.assertEqual(moved, 1)
        self.assertNotIn("food", self.svc.list_categories())
        self.assertEqual(next(self.svc.transactions.iter_all()).category, "etc")

    def test_export_import_roundtrip(self) -> None:
        self.add("2024-01-01", "expense", "food", 100, "점심", ["a", "b"])
        self.add("2024-01-02", "income", "salary", 200)
        out = self.data_dir / "out.csv"
        self.assertEqual(self.svc.export_csv(out, SearchFilter(date_from="2024-01-01", date_to="2024-01-31")), 2)
        result = self.svc.import_csv(out)
        self.assertEqual((result.imported, result.skipped), (2, 0))
        txs = list(self.svc.transactions.iter_all())
        self.assertEqual(len(txs), 4)
        self.assertEqual(txs[-1].id, "TX-000004")
        self.assertEqual([tx.tags for tx in txs if tx.memo == "점심"], [["a", "b"], ["a", "b"]])

    def test_import_skips_invalid_rows(self) -> None:
        src = self.data_dir / "in.csv"
        src.write_text(
            "date,type,category,amount,memo,tags\n"
            "2024-01-01,expense,food,100,,\n"
            "2024-99-01,expense,food,100,,\n"
            "2024-01-01,expense,ghost,100,,\n",
            encoding="utf-8",
        )
        result = self.svc.import_csv(src)
        self.assertEqual((result.imported, result.skipped), (1, 2))
        self.assertEqual(len(result.errors), 2)

    def test_import_missing_header(self) -> None:
        src = self.data_dir / "in.csv"
        src.write_text("date,amount\n2024-01-01,100\n", encoding="utf-8")
        with self.assertRaises(AppError):
            self.svc.import_csv(src)


if __name__ == "__main__":
    unittest.main()
