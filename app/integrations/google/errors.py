from dataclasses import dataclass


@dataclass
class OAuthError(Exception):
    code: str
    http_status: int
    reason: str
    extra: dict | None = None

    def as_response(self) -> dict:
        # Public/safe error payload
        return {"error": self.code, "reason": self.reason}

    def __str__(self) -> str:
        return f"{self.code}: {self.reason}"


