from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = Field(default=2048, ge=256, le=8192)
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    chunk_size: int = Field(default=110, ge=40, le=110)
    chunk_overlap: int = Field(default=20, ge=0, le=39)
    top_k: int = Field(default=5, ge=1, le=10)
    min_similarity: float = Field(default=0.45, ge=0, le=1)
    max_tool_rounds: int = Field(default=3, ge=1, le=5)
    llm_timeout: float = Field(default=180, ge=5, le=600)


@lru_cache(maxsize=1)
def _read_settings(env_version: int) -> Settings:
    return Settings(_env_file=ROOT / ".env")


def settings() -> Settings:
    path = ROOT / ".env"
    return _read_settings(path.stat().st_mtime_ns if path.exists() else 0)
