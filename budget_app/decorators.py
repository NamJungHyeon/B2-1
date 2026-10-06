"""공통 관심사를 분리한 데코레이터.

- handle_errors : 스택트레이스 대신 원인 + 힌트를 출력하고 종료 코드를 돌려준다.
- log_call      : 함수 실행과 소요 시간을 로그 파일에 남긴다.
"""

from __future__ import annotations

import csv
import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from budget_app.errors import AppError

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger("budget_app")


def handle_errors(func: Callable[P, int]) -> Callable[P, int]:
    """CLI 진입점용. 예외를 사용자 메시지로 바꾸고 exit code를 반환한다."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return func(*args, **kwargs)
        except AppError as exc:
            print(f"[오류] {exc.message}")
            if exc.hint:
                print(f"[힌트] {exc.hint}")
            logger.warning("AppError: %s", exc.message)
            return 1
        except (UnicodeError, csv.Error) as exc:
            print(f"[오류] 파일 형식이 올바르지 않습니다: {exc}")
            print("[힌트] UTF-8 인코딩과 CSV 헤더·따옴표 형식을 확인하세요.")
            logger.warning("파일 형식 오류: %s", exc)
            return 1
        except (KeyboardInterrupt, EOFError):
            print("\n[취소] 입력이 중단되었습니다.")
            return 130
        except OSError as exc:
            print(f"[오류] 파일 처리 중 문제가 발생했습니다: {exc}")
            print("[힌트] 저장 폴더 권한과 디스크 공간을 확인하세요.")
            logger.error("OSError: %s", exc)
            return 2

    return wrapper


def log_call(func: Callable[P, R]) -> Callable[P, R]:
    """서비스 메서드용. 호출 이름과 실행 시간을 로그로 남긴다."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info("%s 완료 (%.1f ms)", func.__name__, elapsed_ms)

    return wrapper
