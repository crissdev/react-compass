from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    model_name: str
    chroma_path: Path
    chroma_collection: str = "react-docs"
    react_dev_root: Path
    retrieval_count: int = 5
    allowed_origins: str

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
