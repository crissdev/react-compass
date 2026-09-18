from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_configured_paths_are_used_without_repository_layout_assumptions() -> None:
    settings = Settings(
        _env_file=None,
        model_name="test-model",
        embedding_model="test-embedding-model",
        chroma_path=Path("data/test-embeddings"),
        react_dev_root=Path("vendor/react.dev/src/content"),
        allowed_origins="http://localhost:3000",
    )

    assert settings.chroma_path == Path("data/test-embeddings")
    assert settings.embedding_model == "test-embedding-model"
    assert settings.react_docs_reference_path == Path("vendor/react.dev/src/content/reference")
    assert settings.react_docs_learn_path == Path("vendor/react.dev/src/content/learn")
    assert settings.react_docs_blog_path == Path("vendor/react.dev/src/content/blog")
    assert settings.uses_chroma_cloud is False


def test_allowed_origins_are_trimmed_and_empty_values_are_ignored() -> None:
    settings = Settings(
        _env_file=None,
        model_name="test-model",
        embedding_model="test-embedding-model",
        chroma_path=Path("data/test-embeddings"),
        react_dev_root=Path("vendor/react.dev/src/content"),
        allowed_origins="http://localhost:3000, http://127.0.0.1:3000, ",
    )

    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_chroma_cloud_requires_a_tenant() -> None:
    with pytest.raises(ValidationError, match="CHROMA_TENANT"):
        Settings(_env_file=None, chroma_api_key="secret")


def test_chroma_cloud_configuration_is_detected() -> None:
    settings = Settings(
        _env_file=None,
        chroma_api_key="secret",
        chroma_tenant="tenant-id",
        chroma_database="react-docs",
    )

    assert settings.uses_chroma_cloud is True
    assert settings.chroma_api_key is not None
    assert settings.chroma_api_key.get_secret_value() == "secret"
