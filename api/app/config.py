from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = API_ROOT.parent


def project_path(path: Path) -> Path:
    """Resolve configured relative paths from the repository root."""
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(API_ROOT / ".env", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    model_name: str = "gpt-5"
    chroma_path: Path = Path("data/embeddings")
    chroma_collection: str = "react-docs"
    react_dev_root: Path = Path("../gh/react.dev/src/content")
    retrieval_count: int = 5
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @field_validator("chroma_path", "react_dev_root")
    @classmethod
    def resolve_project_path(cls, value: Path) -> Path:
        return project_path(value)

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
