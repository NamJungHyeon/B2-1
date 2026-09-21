"""화면 출력 포맷. 외부 라이브러리 없이 문자열 정렬로 표를 만든다."""

from __future__ import annotations

from collections.abc import Sequence

from budget_app.models import Summary, Transaction


def format_table(txs: Sequence[Transaction]) -> str:
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
