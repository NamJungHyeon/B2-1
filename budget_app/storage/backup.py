"""저장 파일 백업."""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from budget_app.storage.budgets import BUDGETS_FILE
from budget_app.storage.categories import CATEGORIES_FILE
from budget_app.storage.transactions import TRANSACTIONS_FILE

DATA_FILES: tuple[str, ...] = (TRANSACTIONS_FILE, CATEGORIES_FILE, BUDGETS_FILE)


def backup_files(data_dir: Path, backup_dir: Path) -> list[Path]:
    """저장 파일 3개를 타임스탬프 폴더에 복사하고 복사된 경로를 돌려준다."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix=f"{stamp}-", dir=backup_dir))
    copied: list[Path] = []
    for name in DATA_FILES:
        src = data_dir / name
        if src.exists():
            dst = target / name
            shutil.copy2(src, dst)
            copied.append(dst)
    return copied
