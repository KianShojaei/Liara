"""Normalised errors for everything that touches the Liara API."""

from __future__ import annotations


class LiaraError(Exception):
    """Base class. `user_message` is safe to show to a non-technical user (Persian)."""

    def __init__(self, message: str, *, user_message: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.user_message = user_message or message


class LiaraAuthError(LiaraError):
    def __init__(self, status: int = 401):
        super().__init__(
            "Liara rejected the API token",
            user_message="توکن لیارا معتبر نیست یا منقضی شده. از کنسول یک کلید جدید بسازید و در فایل .env قرار دهید.",
            status=status,
        )


class LiaraNotFound(LiaraError):
    def __init__(self, what: str):
        super().__init__(f"{what} not found", user_message=f"{what} پیدا نشد.", status=404)


class LiaraConflict(LiaraError):
    def __init__(self, what: str):
        super().__init__(
            f"conflict on {what}", user_message=f"تداخل: {what} از قبل وجود دارد.", status=409
        )


class LiaraRateLimited(LiaraError):
    def __init__(self):
        super().__init__(
            "rate limited by Liara",
            user_message="لیارا موقتاً درخواست‌ها را محدود کرده. چند ثانیه بعد دوباره تلاش می‌کنم.",
            status=429,
        )


class LiaraUnavailable(LiaraError):
    def __init__(self, detail: str):
        super().__init__(
            f"Liara API unavailable: {detail}",
            user_message="ارتباط با API لیارا برقرار نشد. اتصال اینترنت و آدرس پایه را بررسی کنید.",
        )


class CircuitOpen(LiaraError):
    def __init__(self):
        super().__init__(
            "circuit breaker open",
            user_message="به دلیل خطاهای پیاپی، تماس با لیارا موقتاً متوقف شده است.",
        )
