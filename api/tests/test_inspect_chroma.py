import json
import sys
from pathlib import Path

import chromadb
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.inspect_chroma import inspect_collection, main


@pytest.fixture
def populated_settings(tmp_path: Path) -> Settings:
    path = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(path))
    collection = client.create_collection(name="inspection-test", embedding_function=None)
    collection.add(
        ids=["first", "second", "third"],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        documents=[
            "## First\n[Sandpack: sandbox]\n[CodeSnippet: snippet]",
            "## Second\nThe second section.",
            "## Other page\nAnother document.",
        ],
        metadatas=[
            {
                "source_url": "https://react.dev/learn/examples",
                "section": "First",
                "deprecated": "Use the new API.",
                "sandpacks": json.dumps({"sandbox": {"content": "<Sandpack>...</Sandpack>"}}),
                "code_snippets": json.dumps(
                    {"snippet": {"language": "js", "code": "const x = 1;"}}
                ),
            },
            {"source_url": "https://react.dev/learn/examples", "section": "Second"},
            {"source_url": "https://react.dev/learn/other", "section": "Other page"},
        ],
    )
    return Settings(
        _env_file=None,
        chroma_path=path,
        chroma_collection="inspection-test",
        chroma_api_key=None,
    )


def test_inspection_returns_readable_metadata_without_changing_stored_chunks(
    populated_settings: Settings,
) -> None:
    result = inspect_collection(
        populated_settings, limit=1, source_url="https://react.dev/learn/examples"
    )

    assert result["collection"] == "inspection-test"
    assert result["path"] == str(populated_settings.chroma_path.resolve())
    assert result["total_count"] == 3
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record["id"] == "first"
    assert record["document"] == "## First\n[Sandpack: sandbox]\n[CodeSnippet: snippet]"
    assert record["metadata"]["sandpacks"]["sandbox"]["content"] == "<Sandpack>...</Sandpack>"
    assert record["metadata"]["code_snippets"]["snippet"]["language"] == "js"
    assert record["metadata"]["deprecated"] == "Use the new API."

    client = chromadb.PersistentClient(path=str(populated_settings.chroma_path))
    stored = client.get_collection("inspection-test", embedding_function=None).get(ids=["first"])
    assert isinstance(stored["metadatas"][0]["sandpacks"], str)
    assert isinstance(stored["metadatas"][0]["code_snippets"], str)


def test_inspection_filters_and_paginates_collection_records(populated_settings: Settings) -> None:
    second = inspect_collection(
        populated_settings, limit=1, offset=1, source_url="https://react.dev/learn/examples"
    )
    assert [record["id"] for record in second["records"]] == ["second"]
    assert second["total_count"] == 3

    absent = inspect_collection(populated_settings, source_url="https://react.dev/learn/example")
    assert absent["records"] == []
    assert absent["total_count"] == 3


def test_cli_saves_readable_json(
    populated_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "chunks.json"
    monkeypatch.setattr("app.inspect_chroma.get_settings", lambda: populated_settings)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_chroma",
            "--limit",
            "1",
            "--source-url",
            "https://react.dev/learn/other",
            "--output",
            str(output),
        ],
    )

    main()

    exported = json.loads(output.read_text(encoding="utf-8"))
    assert exported["total_count"] == 3
    assert [record["id"] for record in exported["records"]] == ["third"]


def test_cloud_mode_is_rejected_without_opening_a_local_store(tmp_path: Path) -> None:
    path = tmp_path / "unused"
    settings = Settings(
        _env_file=None,
        chroma_path=path,
        chroma_api_key=SecretStr("a-secret-that-should-not-be-exported"),
        chroma_tenant="test-tenant",
    )

    with pytest.raises(ValueError, match="requires local Chroma mode"):
        inspect_collection(settings)

    assert not path.exists()


def test_missing_local_directory_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing"
    settings = Settings(_env_file=None, chroma_path=path, chroma_api_key=None)

    with pytest.raises(ValueError, match="directory does not exist"):
        inspect_collection(settings)

    assert not path.exists()


def test_existing_empty_directory_is_not_modified(tmp_path: Path) -> None:
    path = tmp_path / "empty"
    path.mkdir()
    settings = Settings(_env_file=None, chroma_path=path, chroma_api_key=None)

    with pytest.raises(ValueError, match="database does not exist"):
        inspect_collection(settings)

    assert list(path.iterdir()) == []
