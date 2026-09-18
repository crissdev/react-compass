from pathlib import Path
from unittest.mock import Mock, patch

from app.chroma_store import create_chroma_store
from app.config import Settings


def test_create_local_chroma_store_uses_persistence_directory() -> None:
    settings = Settings(_env_file=None, chroma_path=Path("data/embeddings"))
    embeddings = Mock()

    with patch("app.chroma_store.Chroma") as chroma:
        create_chroma_store(settings, embeddings)

    chroma.assert_called_once_with(
        collection_name="react-docs",
        embedding_function=embeddings,
        persist_directory="data/embeddings",
    )


def test_create_cloud_chroma_store_uses_cloud_credentials() -> None:
    settings = Settings(
        _env_file=None,
        chroma_api_key="secret",
        chroma_tenant="tenant-id",
        chroma_database="react-docs",
    )
    embeddings = Mock()

    with patch("app.chroma_store.Chroma") as chroma:
        create_chroma_store(settings, embeddings)

    chroma.assert_called_once_with(
        collection_name="react-docs",
        embedding_function=embeddings,
        chroma_cloud_api_key="secret",
        tenant="tenant-id",
        database="react-docs",
    )
