"""사용자에게 보여줄 오류 타입."""


class AppError(Exception):
    """원인(message)과 해결 힌트(hint)를 함께 가진다. 스택트레이스 대신 이 둘을 출력한다."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
