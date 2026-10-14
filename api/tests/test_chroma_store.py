from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from app.chroma_store import ChromaDefaultEmbeddings, create_chroma_store
from app.config import Settings
from app.ingest import documents_for_file
from app.service import format_context


def test_create_local_chroma_store_uses_persistence_directory() -> None:
    settings = Settings(
        _env_file=None, chroma_path=Path("data/embeddings"), embedding_model="default"
    )
    embeddings = Mock()

    with (
        patch("app.chroma_store.Chroma") as chroma,
        patch("app.chroma_store.DefaultEmbeddingFunction") as default_embeddings,
        patch("app.chroma_store.OpenAIEmbeddings") as openai_embeddings,
    ):
        create_chroma_store(settings, embeddings)

    chroma.assert_called_once_with(
        collection_name="react-docs",
        embedding_function=embeddings,
        persist_directory="data/embeddings",
    )
    default_embeddings.assert_not_called()
    openai_embeddings.assert_not_called()


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


def test_non_default_model_uses_openai_embeddings() -> None:
    settings = Settings(_env_file=None, embedding_model="text-embedding-3-large")

    with (
        patch("app.chroma_store.Chroma") as chroma,
        patch("app.chroma_store.DefaultEmbeddingFunction") as default_embeddings,
        patch("app.chroma_store.OpenAIEmbeddings") as openai_embeddings,
    ):
        create_chroma_store(settings)

    openai_embeddings.assert_called_once_with(model="text-embedding-3-large")
    default_embeddings.assert_not_called()
    assert chroma.call_args.kwargs["embedding_function"] is openai_embeddings.return_value


def test_default_embedding_adapter_converts_native_vectors_and_embeds_queries() -> None:
    native = Mock(return_value=[np.array([1, 2], dtype=np.float32)])
    native.embed_query.return_value = [np.array([3, 4], dtype=np.float32)]

    with patch("app.chroma_store.DefaultEmbeddingFunction", return_value=native):
        embeddings = ChromaDefaultEmbeddings()

    document_vectors = embeddings.embed_documents(["A React document"])
    query_vector = embeddings.embed_query("A React question")

    assert document_vectors == [[1.0, 2.0]]
    assert query_vector == [3.0, 4.0]
    assert all(type(value) is float for value in document_vectors[0] + query_vector)
    native.assert_called_once_with(input=["A React document"])
    native.embed_query.assert_called_once_with(input=["A React question"])


def test_default_embeddings_support_local_ingestion_and_retrieval(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, embedding_model="default", chroma_path=tmp_path / "default-chroma"
    )
    fake = DeterministicFakeEmbedding(size=8)
    native = Mock(side_effect=lambda input: fake.embed_documents(input))
    native.embed_query.side_effect = lambda input: fake.embed_documents(input)
    document = Document(
        page_content="React state belongs to a component.", metadata={"title": "State"}
    )

    with (
        patch("app.chroma_store.DefaultEmbeddingFunction", return_value=native),
        patch("app.chroma_store.OpenAIEmbeddings") as openai_embeddings,
    ):
        store = create_chroma_store(settings)
        store.add_documents([document])
        retrieved = create_chroma_store(settings).similarity_search(document.page_content, k=1)

    openai_embeddings.assert_not_called()
    native.assert_called_once_with(input=[document.page_content])
    native.embed_query.assert_called_once_with(input=[document.page_content])
    assert len(retrieved) == 1
    assert retrieved[0].page_content == document.page_content
    assert retrieved[0].metadata == document.metadata


def test_extracted_metadata_survives_local_chroma_retrieval(tmp_path: Path) -> None:
    root = tmp_path / "reference"
    root.mkdir()
    file = root / "legacy.md"
    snippet = "```js {expectedErrors: {'react-compiler': [5]}}\nlegacy();\n```"
    sandpack = "<Sandpack>\n```js src/App.js active\nexport default App;\n```\n</Sandpack>"
    file.write_text(
        f"<Deprecated>Use the newer API.</Deprecated>\n\n## Usage\n\n{snippet}\n\n{sandpack}\n",
        encoding="utf-8",
    )
    documents = documents_for_file("reference", root, file)
    settings = Settings(_env_file=None, chroma_path=tmp_path / "chroma")
    embeddings = DeterministicFakeEmbedding(size=8)
    store = create_chroma_store(settings, embeddings)
    store.add_documents(documents)

    retrieved = create_chroma_store(settings, embeddings).similarity_search(
        documents[0].page_content, k=1
    )

    assert len(retrieved) == 1
    assert retrieved[0].page_content == documents[0].page_content
    assert retrieved[0].metadata == documents[0].metadata
    context = format_context(retrieved)
    assert snippet in context
    assert sandpack in context
    assert "Deprecation notice:\nUse the newer API." in context
    assert "[CodeSnippet:" not in context
    assert "[Sandpack:" not in context
