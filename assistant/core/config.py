"""Loads config.yaml and secrets from .env. Code reads every setting through get_settings()."""

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # repo root
PKG = ROOT / "assistant"


class ConfigError(RuntimeError):
    pass


class ModelCfg(BaseModel):
    id: str
    fallbacks: list[str] = []
    rpm: int = 30
    max_in_flight: int = 4
    max_tokens: int | None = None
    temperature: float | None = None
    batch_size: int | None = None
    endpoint: str | None = None
    function_id: str | None = None  # Riva (phases 4, 6)
    system_prefix: str | None = None
    extra: dict = {}


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")
    nvidia_api_key: str | None = None


class Settings(BaseModel):
    raw: dict
    models: dict[str, ModelCfg]
    secrets: Secrets

    @property
    def data_dir(self) -> Path:
        override = os.environ.get("ASSISTANT_DATA_DIR")
        path = Path(override) if override else ROOT / self.raw["paths"]["data_dir"]
        return path.resolve()

    @property
    def api_key(self) -> str:
        key = self.secrets.nvidia_api_key
        if not key or key.startswith("nvapi-xxxx"):
            raise ConfigError(
                f"NVIDIA_API_KEY is missing. Copy assistant/.env.example to {ROOT / '.env'} "
                "and put your key from build.nvidia.com in it."
            )
        return key

    @property
    def qdrant_url(self) -> str:
        """QDRANT_URL overrides config.yaml (docker compose sets it to http://qdrant:6333)."""
        return os.environ.get("QDRANT_URL") or self.section("qdrant")["url"]

    def section(self, name: str) -> dict:
        return self.raw.get(name) or {}

    def model(self, role: str) -> ModelCfg:
        if role not in self.models:
            raise ConfigError(f"No model configured for role '{role}' in config.yaml")
        return self.models[role]


@lru_cache
def get_settings() -> Settings:
    path = Path(os.environ.get("ASSISTANT_CONFIG", PKG / "config.yaml"))
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    models = {k: ModelCfg(**v) for k, v in (raw.get("models") or {}).items()}
    return Settings(raw=raw, models=models, secrets=Secrets())
