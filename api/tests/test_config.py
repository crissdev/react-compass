from pathlib import Path

from app.config import PROJECT_ROOT, Settings


def test_relative_data_paths_are_resolved_from_project_root() -> None:
    settings = Settings(
        _env_file=None,
        chroma_path=Path("data/test-embeddings"),
        react_dev_root=Path("vendor/react.dev/src/content"),
    )

    assert settings.chroma_path == PROJECT_ROOT / "data/test-embeddings"
    assert settings.react_docs_reference_path == (
        PROJECT_ROOT / "vendor/react.dev/src/content/reference"
    )
    assert settings.react_docs_learn_path == PROJECT_ROOT / "vendor/react.dev/src/content/learn"
    assert settings.react_docs_blog_path == PROJECT_ROOT / "vendor/react.dev/src/content/blog"


def test_allowed_origins_are_trimmed_and_empty_values_are_ignored() -> None:
    settings = Settings(
        _env_file=None,
        allowed_origins="http://localhost:3000, http://127.0.0.1:3000, ",
    )

    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
