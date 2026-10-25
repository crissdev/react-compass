from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import chromadb
import pytest
from langchain_core.documents import Document

from app import ingest_cloud


def _env_file(tmp_path: Path, **overrides: str | None) -> Path:
    values = {
        "CHROMA_API_KEY": "file-cloud-secret",
        "CHROMA_TENANT": "file-tenant",
        "EMBEDDING_MODEL": "default",
        "REACT_DEV_ROOT": "sources",
    }
    values.update(overrides)
    path = tmp_path / ".env.cloud"
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items() if value is not None),
        encoding="utf-8",
    )
    return path


def _source_files(tmp_path: Path) -> None:
    for source in ("reference", "learn", "blog"):
        root = tmp_path / "sources" / source
        root.mkdir(parents=True)
        (root / "example.md").write_text(
            f"---\ntitle: {source.title()}\n---\n## Usage\n\n{source} content.\n",
            encoding="utf-8",
        )


def _documents(count: int = 5) -> list[Document]:
    return [
        Document(
            page_content=f"Documentation section {index}",
            metadata={"source_url": f"https://react.dev/learn/page-{index}", "title": "Learn"},
        )
        for index in range(count)
    ]


class _FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 2.0] for text in texts]


class _FakeCollection:
    def __init__(self, client: "_FakeClient", name: str) -> None:
        self.client = client
        self.name = name
        self.records: dict[str, tuple[str, dict, list[float]]] = {}
        self.fail_backup = False
        self.corrupt_backup = False
        self.fail_upload_at: int | None = None
        self.corrupt_readback: str | None = None
        self.upload_count = 0

    def count(self) -> int:
        return len(self.records)

    def get(
        self,
        ids: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        include: list[str] | None = None,
    ) -> dict:
        selected = (
            list(self.records) if ids is None else [id_ for id_ in ids if id_ in self.records]
        )
        selected = selected[offset : None if limit is None else offset + limit]
        result = {
            "ids": selected,
            "documents": [self.records[id_][0] for id_ in selected],
            "metadatas": [deepcopy(self.records[id_][1]) for id_ in selected],
            "embeddings": [list(self.records[id_][2]) for id_ in selected],
        }
        if ids is not None and self.corrupt_readback and self.upload_count and selected:
            if self.corrupt_readback == "missing":
                for value in result.values():
                    value.pop()
            elif self.corrupt_readback == "document":
                result["documents"][0] = "Wrong content"
            elif self.corrupt_readback == "metadata":
                result["metadatas"][0] = {"title": "Wrong metadata"}
            elif self.corrupt_readback == "dimension":
                result["embeddings"][0] = [1.0]
            elif self.corrupt_readback == "nonfinite":
                result["embeddings"][0][0] = float("nan")
            elif self.corrupt_readback == "vector":
                result["embeddings"][0][0] += 1.0
        if include is not None:
            for field in ("documents", "metadatas", "embeddings"):
                if field not in include:
                    result[field] = None
        return result

    def fork(self, new_name: str) -> "_FakeCollection":
        self.client.events.append(("fork", new_name))
        if self.fail_backup:
            raise RuntimeError("Backup unavailable")
        backup = _FakeCollection(self.client, new_name)
        backup.records = deepcopy(self.records)
        if self.corrupt_backup:
            backup.records.pop(next(iter(backup.records)))
        self.client.collections[new_name] = backup
        return backup

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        self.upload_count += 1
        self.client.events.append(("upsert", list(ids)))
        for id_, document, metadata, vector in zip(
            ids, documents, metadatas, embeddings, strict=True
        ):
            self.records[id_] = (document, deepcopy(metadata), list(vector))
        if self.upload_count == self.fail_upload_at:
            raise RuntimeError("Upload interrupted after accepting records")

    def delete(self, ids: list[str]) -> None:
        self.client.events.append(("delete", list(ids)))
        for id_ in ids:
            del self.records[id_]


class _FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeCollection] = {}
        self.events: list[tuple[str, object]] = []

    def get_collection(self, name: str, embedding_function: object = None) -> _FakeCollection:
        if name not in self.collections:
            raise chromadb.errors.NotFoundError("Collection does not exist")
        return self.collections[name]

    def create_collection(self, name: str, embedding_function: object = None) -> _FakeCollection:
        self.events.append(("create", name))
        collection = _FakeCollection(self, name)
        self.collections[name] = collection
        return collection


@pytest.fixture
def cloud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    config = ingest_cloud.load_cloud_config(_env_file(tmp_path))
    client = _FakeClient()
    collection = client.create_collection(config.settings.chroma_collection)
    for index in range(5):
        collection.records[f"old-{index}"] = ("Old content", {"title": "Old"}, [1.0, 2.0, 3.0])
    client.events.clear()
    monkeypatch.setattr(ingest_cloud.chromadb, "CloudClient", Mock(return_value=client))
    monkeypatch.setattr(ingest_cloud, "ChromaDefaultEmbeddings", _FakeEmbeddings)
    monkeypatch.setattr(ingest_cloud, "BATCH_SIZE", 2)
    return config, client, collection


def test_explicit_env_file_overrides_ambient_target_and_ignores_local_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("CHROMA_COLLECTION=local-collection\n", encoding="utf-8")
    for key, value in {
        "CHROMA_API_KEY": "ambient-secret",
        "CHROMA_TENANT": "ambient-tenant",
        "CHROMA_DATABASE": "ambient-database",
        "CHROMA_COLLECTION": "ambient-collection",
        "CHROMA_PATH": "local-data",
        "EMBEDDING_MODEL": "ambient-model",
        "REACT_DEV_ROOT": "ambient-sources",
    }.items():
        monkeypatch.setenv(key, value)

    config = ingest_cloud.load_cloud_config(_env_file(tmp_path))

    assert config.settings.chroma_api_key.get_secret_value() == "file-cloud-secret"
    assert config.settings.chroma_tenant == "file-tenant"
    assert config.settings.chroma_database == "react-docs"
    assert config.settings.chroma_collection == "react-docs"
    assert config.settings.chroma_path is None
    assert config.settings.embedding_model == "default"
    assert config.settings.react_dev_root == tmp_path / "sources"


@pytest.mark.parametrize("key", ["CHROMA_API_KEY", "CHROMA_TENANT", "EMBEDDING_MODEL"])
def test_cloud_config_requires_credentials_and_model_in_selected_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setenv(key, "ambient-value")

    with pytest.raises(ValueError, match=key):
        ingest_cloud.load_cloud_config(_env_file(tmp_path, **{key: None}))


def test_openai_model_requires_its_key_in_selected_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-secret")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        ingest_cloud.load_cloud_config(
            _env_file(tmp_path, EMBEDDING_MODEL="text-embedding-3-small")
        )


def test_missing_env_file_fails_without_creating_it(tmp_path: Path) -> None:
    path = tmp_path / "missing.env"

    with pytest.raises(ValueError, match="Environment file does not exist"):
        ingest_cloud.load_cloud_config(path)

    assert not path.exists()


def test_dotenv_interpolation_cannot_import_process_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOME_PROCESS_SECRET", "ambient-secret")

    config = ingest_cloud.load_cloud_config(
        _env_file(tmp_path, CHROMA_API_KEY="${SOME_PROCESS_SECRET}")
    )

    assert config.settings.chroma_api_key.get_secret_value() == "${SOME_PROCESS_SECRET}"


def test_dry_run_parses_real_sources_without_network_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = _env_file(tmp_path)
    _source_files(tmp_path)
    cloud_client = Mock(side_effect=AssertionError("Dry run contacted cloud"))
    embeddings = Mock(side_effect=AssertionError("Dry run initialized embeddings"))
    monkeypatch.setattr(ingest_cloud.chromadb, "CloudClient", cloud_client)
    monkeypatch.setattr(ingest_cloud, "ChromaDefaultEmbeddings", embeddings)
    monkeypatch.setattr(ingest_cloud, "OpenAIEmbeddings", embeddings)
    monkeypatch.setattr("sys.argv", ["ingest_cloud", "--env-file", str(env_file), "--dry-run"])

    ingest_cloud.main()

    assert "Loaded 3 chunks" in capsys.readouterr().out
    cloud_client.assert_not_called()
    embeddings.assert_not_called()


@pytest.mark.parametrize("source", ["reference", "learn", "blog"])
def test_missing_source_directory_rejects_partial_refresh(tmp_path: Path, source: str) -> None:
    config = ingest_cloud.load_cloud_config(_env_file(tmp_path))
    _source_files(tmp_path)
    root = tmp_path / "sources" / source
    (root / "example.md").unlink()
    root.rmdir()

    with pytest.raises(ValueError, match=f"directory is missing: {source}"):
        ingest_cloud.cloud_documents(config.settings)


@pytest.mark.parametrize("content", ["No section headings", "## Pages\n\nIndex links."])
def test_source_without_indexable_chunks_rejects_partial_refresh(
    tmp_path: Path, content: str
) -> None:
    config = ingest_cloud.load_cloud_config(_env_file(tmp_path))
    _source_files(tmp_path)
    blog = tmp_path / "sources" / "blog"
    (blog / "example.md").unlink()
    (blog / "index.md").write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="Each documentation source"):
        ingest_cloud.cloud_documents(config.settings)


def test_content_ids_are_stable_order_independent_and_sensitive_to_metadata() -> None:
    documents = _documents(2)
    original_ids = ingest_cloud.document_ids(documents)

    assert ingest_cloud.document_ids(deepcopy(documents)) == original_ids
    assert ingest_cloud.document_ids(list(reversed(documents))) == list(reversed(original_ids))
    reordered_metadata = Document(
        page_content=documents[0].page_content,
        metadata=dict(reversed(list(documents[0].metadata.items()))),
    )
    assert ingest_cloud.document_ids([reordered_metadata])[0] == original_ids[0]
    assert (
        ingest_cloud.document_ids(
            [Document(page_content="Changed", metadata=documents[0].metadata)]
        )[0]
        != original_ids[0]
    )
    changed_metadata = {**documents[0].metadata, "title": "Changed"}
    assert (
        ingest_cloud.document_ids(
            [Document(page_content=documents[0].page_content, metadata=changed_metadata)]
        )[0]
        != original_ids[0]
    )


def test_identical_document_occurrences_remain_distinct_and_repeatable() -> None:
    document = _documents(1)[0]

    ids = ingest_cloud.document_ids([document, deepcopy(document)])

    assert len(set(ids)) == 2
    assert ingest_cloud.document_ids([deepcopy(document), document]) == ids


def test_backup_failure_retains_old_records_and_prevents_upload(cloud: tuple) -> None:
    config, client, collection = cloud
    collection.fail_backup = True
    original = deepcopy(collection.records)

    with pytest.raises(RuntimeError, match="Backup unavailable"):
        ingest_cloud.refresh_cloud(config, _documents())

    assert collection.records == original
    assert not any(event in {"upsert", "delete"} for event, _ in client.events)


def test_incomplete_backup_prevents_upload_and_deletion(cloud: tuple) -> None:
    config, client, collection = cloud
    collection.corrupt_backup = True

    with pytest.raises(RuntimeError, match="Backup verification failed"):
        ingest_cloud.refresh_cloud(config, _documents())

    assert not any(event in {"upsert", "delete"} for event, _ in client.events)


def test_interrupted_upload_keeps_every_old_record_and_backup(cloud: tuple) -> None:
    config, client, collection = cloud
    collection.fail_upload_at = 2
    original = deepcopy(collection.records)

    with pytest.raises(RuntimeError, match="Upload interrupted"):
        ingest_cloud.refresh_cloud(config, _documents())

    assert all(collection.records[id_] == record for id_, record in original.items())
    assert not any(event == "delete" for event, _ in client.events)
    backups = [item for name, item in client.collections.items() if name != collection.name]
    assert len(backups) == 1
    assert backups[0].records == original


@pytest.mark.parametrize(
    "corruption", ["missing", "document", "metadata", "dimension", "nonfinite", "vector"]
)
def test_failed_upload_verification_prevents_deletion(cloud: tuple, corruption: str) -> None:
    config, client, collection = cloud
    original_ids = set(collection.records)
    collection.corrupt_readback = corruption

    with pytest.raises(RuntimeError, match="Cloud verification failed"):
        ingest_cloud.refresh_cloud(config, _documents())

    assert original_ids <= set(collection.records)
    assert not any(event == "delete" for event, _ in client.events)


def test_refresh_preserves_collection_batches_writes_and_is_idempotent(cloud: tuple) -> None:
    config, client, collection = cloud
    original = deepcopy(collection.records)
    documents = _documents()

    ingest_cloud.refresh_cloud(config, documents)

    expected_ids = ingest_cloud.document_ids(documents)
    assert client.collections[config.settings.chroma_collection] is collection
    assert set(collection.records) == set(expected_ids)
    assert [len(ids) for event, ids in client.events if event == "upsert"] == [2, 2, 1]
    assert [len(ids) for event, ids in client.events if event == "delete"] == [2, 2, 1]
    backups = [item for name, item in client.collections.items() if name != collection.name]
    assert len(backups) == 1
    assert backups[0].records == original
    for id_, document in zip(expected_ids, documents, strict=True):
        assert collection.records[id_][:2] == (document.page_content, document.metadata)
    after_first_refresh = deepcopy(collection.records)
    client.events.clear()

    ingest_cloud.refresh_cloud(config, documents)

    assert collection.records == after_first_refresh
    assert not any(event == "delete" for event, _ in client.events)
    ingest_cloud.chromadb.CloudClient.assert_called_with(
        api_key="file-cloud-secret", tenant="file-tenant", database="react-docs"
    )


@pytest.mark.parametrize("absent", [False, True])
def test_refresh_initializes_empty_or_absent_cloud_collection(cloud: tuple, absent: bool) -> None:
    config, client, collection = cloud
    collection.records.clear()
    if absent:
        client.collections.clear()
    documents = _documents(1)

    ingest_cloud.refresh_cloud(config, documents)

    target = client.collections[config.settings.chroma_collection]
    assert set(target.records) == set(ingest_cloud.document_ids(documents))
    assert not any(event in {"fork", "delete"} for event, _ in client.events)
    assert sum(event == "create" for event, _ in client.events) == int(absent)


def test_embedding_dimension_mismatch_preserves_original_collection(
    cloud: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, client, collection = cloud
    original = deepcopy(collection.records)
    embeddings = Mock()
    embeddings.embed_documents.return_value = [[1.0]]
    monkeypatch.setattr(ingest_cloud, "ChromaDefaultEmbeddings", lambda: embeddings)

    with pytest.raises(ValueError, match="Embedding dimensions differ"):
        ingest_cloud.refresh_cloud(config, _documents(1))

    assert collection.records == original
    assert not any(event in {"fork", "upsert", "delete"} for event, _ in client.events)


def test_empty_refresh_is_rejected_before_constructing_cloud_client(cloud: tuple) -> None:
    config, _, _ = cloud

    with pytest.raises(ValueError, match="empty document set"):
        ingest_cloud.refresh_cloud(config, [])

    ingest_cloud.chromadb.CloudClient.assert_not_called()


@pytest.mark.parametrize("content", ["x" * 16384, "\U0001f680" * 4096])
def test_cloud_preflight_checks_document_utf8_bytes_at_boundary(content: str) -> None:
    document = Document(page_content=content, metadata={"title": "Boundary"})

    ingest_cloud.validate_cloud_documents([document])

    with pytest.raises(ValueError):
        ingest_cloud.validate_cloud_documents(
            [Document(page_content=content + "x", metadata=document.metadata)]
        )


@pytest.mark.parametrize("value", ["x" * 8182, "\u00e9" * 4091])
def test_cloud_preflight_checks_metadata_value_utf8_bytes_at_boundary(value: str) -> None:
    document = Document(page_content="Section", metadata={"title": value})

    ingest_cloud.validate_cloud_documents([document])

    with pytest.raises(ValueError):
        ingest_cloud.validate_cloud_documents(
            [Document(page_content="Section", metadata={"title": value + "x"})]
        )


@pytest.mark.parametrize("key", ["k" * 36, "\U0001f680" * 9])
def test_cloud_preflight_checks_metadata_key_utf8_bytes_at_boundary(key: str) -> None:
    ingest_cloud.validate_cloud_documents(
        [Document(page_content="Section", metadata={key: "value"})]
    )

    with pytest.raises(ValueError):
        ingest_cloud.validate_cloud_documents(
            [Document(page_content="Section", metadata={key + "x": "value"})]
        )


def test_cloud_preflight_checks_metadata_key_count_boundary() -> None:
    metadata = {f"key-{index}": "value" for index in range(32)}

    ingest_cloud.validate_cloud_documents([Document(page_content="Section", metadata=metadata)])

    with pytest.raises(ValueError):
        ingest_cloud.validate_cloud_documents(
            [Document(page_content="Section", metadata={**metadata, "extra-key": "value"})]
        )


@pytest.mark.parametrize(
    "document",
    [
        Document(page_content="\U0001f680" * 4097, metadata={"title": "Oversized document"}),
        Document(page_content="Section", metadata={"title": "\u00e9" * 4092}),
    ],
)
def test_refresh_rejects_oversized_data_before_cloud_or_embedding_clients(
    cloud: tuple, monkeypatch: pytest.MonkeyPatch, document: Document
) -> None:
    config, _, collection = cloud
    original = deepcopy(collection.records)
    embeddings = Mock(side_effect=AssertionError("Invalid refresh initialized embeddings"))
    monkeypatch.setattr(ingest_cloud, "ChromaDefaultEmbeddings", embeddings)
    monkeypatch.setattr(ingest_cloud, "OpenAIEmbeddings", embeddings)

    with pytest.raises(ValueError):
        ingest_cloud.refresh_cloud(config, [document])

    ingest_cloud.chromadb.CloudClient.assert_not_called()
    embeddings.assert_not_called()
    assert collection.records == original


def test_dry_run_reports_oversized_source_without_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = _env_file(tmp_path)
    _source_files(tmp_path)
    (tmp_path / "sources" / "blog" / "example.md").write_text(
        "## Large section\n\n" + "x" * 16385, encoding="utf-8"
    )
    cloud_client = Mock(side_effect=AssertionError("Invalid dry run contacted cloud"))
    embeddings = Mock(side_effect=AssertionError("Invalid dry run initialized embeddings"))
    monkeypatch.setattr(ingest_cloud.chromadb, "CloudClient", cloud_client)
    monkeypatch.setattr(ingest_cloud, "ChromaDefaultEmbeddings", embeddings)
    monkeypatch.setattr(ingest_cloud, "OpenAIEmbeddings", embeddings)
    monkeypatch.setattr("sys.argv", ["ingest_cloud", "--env-file", str(env_file), "--dry-run"])

    with pytest.raises(SystemExit) as error:
        ingest_cloud.main()

    assert error.value.code == 1
    output = capsys.readouterr()
    assert "Dry run complete" not in output.out
    cloud_client.assert_not_called()
    embeddings.assert_not_called()


def test_replacement_removes_deleted_and_changed_source_versions(cloud: tuple) -> None:
    config, client, collection = cloud
    documents = _documents(3)
    ingest_cloud.refresh_cloud(config, documents)
    first_snapshot = deepcopy(collection.records)
    replacement = [documents[0], documents[1].model_copy(update={"page_content": "Updated text"})]

    ingest_cloud.refresh_cloud(config, replacement)

    assert set(collection.records) == set(ingest_cloud.document_ids(replacement))
    assert ingest_cloud.document_ids(documents)[0] in collection.records
    assert not set(ingest_cloud.document_ids(documents)[1:]) & set(collection.records)
    assert any(
        backup.records == first_snapshot
        for name, backup in client.collections.items()
        if name != collection.name
    )


def test_retry_after_interrupted_upload_converges_without_duplicates(cloud: tuple) -> None:
    config, _, collection = cloud
    documents = _documents(5)
    collection.fail_upload_at = 1
    with pytest.raises(RuntimeError, match="Upload interrupted"):
        ingest_cloud.refresh_cloud(config, documents)
    collection.fail_upload_at = None

    ingest_cloud.refresh_cloud(config, documents)

    assert set(collection.records) == set(ingest_cloud.document_ids(documents))
    assert collection.count() == len(documents)


def test_truncation_option_replaces_cloud_records_and_is_repeatable(
    cloud: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, _, collection = cloud
    env_file = _env_file(tmp_path)
    _source_files(tmp_path)
    (tmp_path / "sources" / "blog" / "example.md").write_text(
        "## Oversized section\n\n"
        + "\U0001f680" * 5000
        + "\n\n<Sandpack>\n```js\n"
        + "console.log('complete example');\n" * 400
        + "```\n</Sandpack>\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv", ["ingest_cloud", "--env-file", str(env_file), "--truncate-oversized"]
    )

    ingest_cloud.main()
    first_snapshot = deepcopy(collection.records)
    ingest_cloud.main()

    assert "Adjusted 1 oversized chunks" in capsys.readouterr().out
    assert collection.count() == 3
    assert collection.records == first_snapshot
    stored = [
        Document(page_content=text, metadata=metadata)
        for text, metadata, _ in first_snapshot.values()
    ]
    ingest_cloud.validate_cloud_documents(stored)
