"""Inspect local chunks without embeddings; decode example metadata for JSON export."""

import argparse
import contextlib
import json
from pathlib import Path
from typing import Any

import chromadb

from app.config import Settings, get_settings


def inspect_collection(
    settings: Settings, limit: int = 5, offset: int = 0, source_url: str | None = None
) -> dict[str, Any]:
    """Read chunks, decoding JSON example fields while retaining malformed legacy strings."""
    if settings.uses_chroma_cloud:
        raise ValueError("Inspection requires local Chroma mode; remove CHROMA_API_KEY.")
    if limit < 1 or offset < 0:
        raise ValueError("Limit must be positive and offset must be nonnegative.")
    path = settings.chroma_path
    if path is None or not path.is_dir():
        raise ValueError(f"Local Chroma directory does not exist: {path}")
    if not (path / "chroma.sqlite3").is_file():
        raise ValueError(f"Local Chroma database does not exist: {path}")

    client = chromadb.PersistentClient(path=str(path))
    collection = client.get_collection(name=settings.chroma_collection, embedding_function=None)
    result = collection.get(
        limit=limit,
        offset=offset,
        where={"source_url": source_url} if source_url is not None else None,
        include=["documents", "metadatas"],
    )
    records = []
    for chunk_id, document, metadata in zip(
        result["ids"], result["documents"] or [], result["metadatas"] or [], strict=True
    ):
        readable = dict(metadata or {})
        for key in ("sandpacks", "code_snippets"):
            value = readable.get(key)
            if isinstance(value, str):
                with contextlib.suppress(json.JSONDecodeError):
                    readable[key] = json.loads(value)
        records.append({"id": chunk_id, "document": document, "metadata": readable})
    return {
        "collection": settings.chroma_collection,
        "path": str(path.resolve()),
        "total_count": collection.count(),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--source-url", help="Filter by the exact source_url metadata value.")
    parser.add_argument("--output", type=Path, help="Save JSON to a file instead of printing it.")
    args = parser.parse_args()
    try:
        result = inspect_collection(get_settings(), args.limit, args.offset, args.source_url)
    except (ValueError, chromadb.errors.NotFoundError) as error:
        parser.error(str(error))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
