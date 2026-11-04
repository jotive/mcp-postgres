from __future__ import annotations

import json

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TargetConfig(BaseModel):
    name: str
    dsn: str
    max_rows: int = Field(default=1000, gt=0)
    statement_timeout_ms: int = Field(default=5000, gt=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCPPG_", env_file=".env", extra="ignore")

    targets: str = Field(default="[]")
    default_target: str | None = None
    audit_path: str = "audit.log.jsonl"

    def target_map(self) -> dict[str, TargetConfig]:
        raw = json.loads(self.targets)
        targets = {t["name"]: TargetConfig(**t) for t in raw}
        if not targets:
            raise ValueError("MCPPG_TARGETS is empty; configure at least one read-only target")
        return targets

    def resolve_default(self, targets: dict[str, TargetConfig]) -> str:
        if self.default_target:
            if self.default_target not in targets:
                raise ValueError(f"default_target '{self.default_target}' not in targets")
            return self.default_target
        return next(iter(targets))
