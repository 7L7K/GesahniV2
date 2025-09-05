from __future__ import annotations

from dataclasses import dataclass

from app import settings


@dataclass(frozen=True)
class Config:
    router_default_model: str
    router_budget_ms: int
    backend_timeout_ms: int
    circuit_breaker_cooldown_s: int
    cache_ttl_s: int
    cache_max_entries: int
    allowlist_models: tuple[str, ...]
    dry_run: bool
    auth_dev_bypass: bool
    skills_version: str
    stream_stall_ms: int
    prompt_backend: str


def _load() -> Config:
    return Config(
        router_default_model=settings.router_default_model(),
        router_budget_ms=settings.router_budget_ms(),
        backend_timeout_ms=settings.backend_timeout_ms(),
        circuit_breaker_cooldown_s=settings.circuit_breaker_cooldown_s(),
        cache_ttl_s=settings.cache_ttl_s(),
        cache_max_entries=settings.cache_max_entries(),
        allowlist_models=tuple(settings.allowlist_models()),
        dry_run=settings.dry_run(),
        auth_dev_bypass=settings.auth_dev_bypass(),
        skills_version=settings.skills_version(),
        stream_stall_ms=settings.stream_stall_ms(),
        prompt_backend=settings.prompt_backend(),
    )


CONFIG = _load()

