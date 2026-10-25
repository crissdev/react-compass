"""Refresh only Chroma Cloud, using credentials from an explicit dotenv file."""

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import chromadb
from chromadb import Collection
from dotenv import dotenv_values
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from app.chroma_store import ChromaDefaultEmbeddings
from app.cloud_records import truncate_cloud_documents, validate_cloud_documents
from app.config import Settings
from app.ingest import load_documents

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env.cloud"
BATCH_SIZE = 100


@dataclass(frozen=True)
class CloudConfig:
    settings: Settings
    openai_api_key: SecretStr | None


def load_cloud_config(env_file: Path) -> CloudConfig:
    """Load cloud settings without falling back to local dotenv or process credentials."""
    env_file = env_file.resolve()
    if not env_file.is_file():
        raise ValueError(f"Environment file does not exist: {env_file}")
    values = dotenv_values(env_file, interpolate=False)

    def value(key: str, default: str = "") -> str:
        return (values.get(key) or default).strip()

    for key in ("CHROMA_API_KEY", "CHROMA_TENANT", "EMBEDDING_MODEL"):
        if not value(key):
            raise ValueError(f"{key} must be set in {env_file}")
    model = value("EMBEDDING_MODEL")
    api_key = value("OPENAI_API_KEY")
    if model != "default" and not api_key:
        raise ValueError(f"OPENAI_API_KEY must be set in {env_file} for this embedding model")
    source_root = Path(value("REACT_DEV_ROOT", "../react.dev/src/content"))
    if not source_root.is_absolute():
        source_root = env_file.parent / source_root
    settings = Settings(
        _env_file=None,
        chroma_api_key=value("CHROMA_API_KEY"),
        chroma_tenant=value("CHROMA_TENANT"),
        chroma_database=value("CHROMA_DATABASE", "react-docs"),
        chroma_collection=value("CHROMA_COLLECTION", "react-docs"),
        chroma_path=None,
        embedding_model=model,
        react_dev_root=source_root.resolve(),
    )
    return CloudConfig(settings, SecretStr(api_key) if api_key else None)


def cloud_documents(settings: Settings) -> list[Document]:
    for source in ("reference", "learn", "blog"):
        if not (settings.react_dev_root / source).is_dir():
            raise ValueError(f"Documentation source directory is missing: {source}")
    documents = load_documents(settings)
    sources = {document.metadata["source_type"] for document in documents}
    if sources != {"reference", "learn", "blog"}:
        raise ValueError("Each documentation source must contain indexable chunks")
    return documents


def document_ids(documents: list[Document]) -> list[str]:
    """Content IDs make reruns idempotent, including documents with identical content."""
    occurrences: Counter[str] = Counter()
    ids = []
    for document in documents:
        canonical = json.dumps(
            {"document": document.page_content, "metadata": document.metadata},
            sort_keys=True,
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        ids.append(f"react-docs-{digest}-{occurrences[digest]}")
        occurrences[digest] += 1
    return ids


def collection_ids(collection: Collection) -> set[str]:
    count = collection.count()
    ids = []
    for offset in range(0, count, BATCH_SIZE):
        ids.extend(collection.get(limit=BATCH_SIZE, offset=offset, include=[])["ids"])
    if len(ids) != count or len(set(ids)) != count or collection.count() != count:
        raise RuntimeError("Collection changed while reading; stop other ingestion jobs and retry")
    return set(ids)


def verify_batch(
    collection: Collection, ids: list[str], documents: list[Document], vectors: list[list[float]]
) -> None:
    result = collection.get(ids=ids, include=["documents", "metadatas", "embeddings"])
    if set(result["ids"]) != set(ids):
        raise RuntimeError(
            "Cloud verification failed: missing uploaded chunks; old records retained"
        )
    expected = dict(zip(ids, zip(documents, vectors, strict=True), strict=True))
    for index, chunk_id in enumerate(result["ids"]):
        document, vector = expected[chunk_id]
        if (
            result["documents"] is None
            or result["metadatas"] is None
            or result["embeddings"] is None
            or result["documents"][index] != document.page_content
            or result["metadatas"][index] != document.metadata
            or len(result["embeddings"][index]) != len(vector)
            or not all(
                math.isclose(actual, expected, rel_tol=1e-5, abs_tol=1e-7)
                for actual, expected in zip(result["embeddings"][index], vector, strict=True)
            )
        ):
            raise RuntimeError("Cloud verification failed: chunk mismatch; old records retained")


def refresh_cloud(config: CloudConfig, documents: list[Document]) -> None:
    settings = config.settings
    if not settings.chroma_api_key or not settings.chroma_tenant:
        raise ValueError("Cloud credentials are required; local ingestion is not supported")
    if not documents:
        raise ValueError("Cannot refresh an empty document set")
    if settings.embedding_model != "default" and not config.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for this embedding model")
    validate_cloud_documents(documents)
    client = chromadb.CloudClient(
        api_key=settings.chroma_api_key.get_secret_value(),
        tenant=settings.chroma_tenant,
        database=settings.chroma_database,
    )
    try:
        collection = client.get_collection(settings.chroma_collection, embedding_function=None)
    except chromadb.errors.NotFoundError:
        collection = client.create_collection(settings.chroma_collection, embedding_function=None)
    original_ids = collection_ids(collection)
    embedding_function = (
        ChromaDefaultEmbeddings()
        if settings.embedding_model == "default"
        else OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=config.openai_api_key,
            base_url="https://api.openai.com/v1",
        )
    )
    print(f"Generating {len(documents)} embeddings with {settings.embedding_model}", flush=True)
    vectors = embedding_function.embed_documents([document.page_content for document in documents])
    dimensions = {len(vector) for vector in vectors}
    if (
        len(vectors) != len(documents)
        or len(dimensions) != 1
        or 0 in dimensions
        or max(dimensions) > 4096
        or any(not math.isfinite(number) for vector in vectors for number in vector)
    ):
        raise RuntimeError("Embedding provider returned invalid vectors; collection not refreshed")
    dimension = dimensions.pop()
    if original_ids:
        sample = collection.get(limit=1, include=["embeddings"])["embeddings"]
        if sample is None or len(sample) != 1 or len(sample[0]) != dimension:
            raise ValueError(
                "Embedding dimensions differ; use the deployed model or a new collection"
            )
        backup_name = (
            f"{collection.name[:25]}-backup-{datetime.now(UTC):%Y%m%d%H%M%S}-{uuid4().hex[:8]}"
        )
        backup = collection.fork(new_name=backup_name)
        if collection_ids(backup) != original_ids or collection_ids(collection) != original_ids:
            raise RuntimeError("Backup verification failed; collection not refreshed")
        print(f"Cloud backup retained: {backup_name}", flush=True)

    ids = document_ids(documents)
    for start in range(0, len(ids), BATCH_SIZE):
        batch = documents[start : start + BATCH_SIZE]
        collection.upsert(
            ids=ids[start : start + BATCH_SIZE],
            documents=[document.page_content for document in batch],
            metadatas=[document.metadata for document in batch],
            embeddings=vectors[start : start + BATCH_SIZE],
        )
        print(f"Uploaded {min(start + BATCH_SIZE, len(ids))}/{len(ids)} chunks", flush=True)
    for start in range(0, len(ids), BATCH_SIZE):
        verify_batch(
            collection,
            ids[start : start + BATCH_SIZE],
            documents[start : start + BATCH_SIZE],
            vectors[start : start + BATCH_SIZE],
        )
    expected_ids = set(ids)
    if collection_ids(collection) != original_ids | expected_ids:
        raise RuntimeError("Unexpected cloud records appeared; old records retained")
    obsolete = sorted(original_ids - expected_ids)
    for start in range(0, len(obsolete), BATCH_SIZE):
        collection.delete(ids=obsolete[start : start + BATCH_SIZE])
    if collection_ids(collection) != expected_ids:
        raise RuntimeError("Final cloud verification failed; retry the command")
    print(f"Verified {len(ids)} cloud chunks; removed {len(obsolete)} obsolete records", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--dry-run", action="store_true", help="Parse sources without network access"
    )
    parser.add_argument(
        "--truncate-oversized",
        action="store_true",
        help="Shorten oversized prose and omit complete examples as needed to fit cloud limits",
    )
    args = parser.parse_args()
    try:
        config = load_cloud_config(args.env_file)
        documents = cloud_documents(config.settings)
        settings = config.settings
        print(
            f"Target: Chroma Cloud database {settings.chroma_database}, "
            f"collection {settings.chroma_collection}, model {settings.embedding_model}",
            flush=True,
        )
        print(f"Loaded {len(documents)} chunks from {settings.react_dev_root}", flush=True)
        if args.truncate_oversized:
            documents, changes = truncate_cloud_documents(documents)
            print(f"Adjusted {len(changes)} oversized chunks for Chroma Cloud", flush=True)
            for change in changes:
                print(change, flush=True)
        validate_cloud_documents(documents)
        if args.dry_run:
            print("Dry run complete; no embedding requests or cloud writes")
            return
        refresh_cloud(config, documents)
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
