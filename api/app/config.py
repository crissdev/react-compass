from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        validate_default=True,
    )

    model_name: str = "gpt-5-nano"
    model_args: dict[str, Any] = Field(default_factory=dict)
    embedding_model: str = "text-embedding-3-small"
    chroma_path: Path | None = Path("../data/embeddings")
    chroma_collection: str = "react-docs"
    chroma_api_key: SecretStr | None = None
    chroma_tenant: str | None = None
    chroma_database: str = "react-docs"
    react_dev_root: Path = Path("../react.dev/src/content")
    retrieval_count: int = 5
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @model_validator(mode="after")
    def validate_chroma_configuration(self) -> "Settings":
        if self.chroma_api_key and not self.chroma_tenant:
            raise ValueError("CHROMA_TENANT is required when CHROMA_API_KEY is configured")
        if not self.chroma_api_key and not self.chroma_path:
            raise ValueError("CHROMA_PATH is required when Chroma Cloud is not configured")
        return self

    @property
    def uses_chroma_cloud(self) -> bool:
        return self.chroma_api_key is not None

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def react_docs_reference_path(self) -> Path:
        return self.react_dev_root / "reference"

    @property
    def react_docs_learn_path(self) -> Path:
        return self.react_dev_root / "learn"

    @property
    def react_docs_blog_path(self) -> Path:
        return self.react_dev_root / "blog"


@lru_cache
def get_settings() -> Settings:
    return Settings()
