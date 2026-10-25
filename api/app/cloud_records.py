"""Validate and explicitly shorten records for Chroma Cloud's default byte limits."""

import json
import re
from copy import deepcopy

from langchain_core.documents import Document

from app.markdown_metadata import EXAMPLE_METADATA_KEYS, REFERENCE_PATTERN

# https://docs.trychroma.com/cloud/quotas-limits
MAX_DOCUMENT_BYTES = 16_384
MAX_METADATA_VALUE_BYTES = 8_182
MAX_METADATA_KEY_BYTES = 36
MAX_METADATA_KEYS = 32

_CATALOG_KINDS = {key: kind for kind, key in EXAMPLE_METADATA_KEYS.items()}
_IDENTITY_KEYS = {"source_url", "source_type", "language", "title", "section"}
_EXCERPT_MARKER = "\n\n[Excerpt shortened.]"
_OMITTED_MARKER = "[Example omitted.]"
_ATOMIC_PATTERN = re.compile(f"{REFERENCE_PATTERN.pattern}|{re.escape(_OMITTED_MARKER)}")


def _bytes(value: str) -> int:
    return len(value.encode("utf-8"))


def _source(document: Document, index: int) -> str:
    source = document.metadata.get("source_url", f"chunk {index + 1}")
    section = document.metadata.get("section", "")
    return f"{source} {section}".rstrip()


def _validate(documents: list[Document], *, include_sizes: bool) -> None:
    issues = []
    size_overages = False
    structural_overages = False
    for index, document in enumerate(documents):
        overages = []
        size = _bytes(document.page_content)
        if include_sizes and size > MAX_DOCUMENT_BYTES:
            overages.append(f"document: {size} bytes (limit {MAX_DOCUMENT_BYTES})")
            size_overages = True
        if len(document.metadata) > MAX_METADATA_KEYS:
            overages.append(f"metadata: more than {MAX_METADATA_KEYS} keys")
            structural_overages = True
        for key, value in document.metadata.items():
            if _bytes(key) > MAX_METADATA_KEY_BYTES:
                overages.append(f"metadata key {key}: more than {MAX_METADATA_KEY_BYTES} bytes")
                structural_overages = True
            if include_sizes and isinstance(value, str):
                size = _bytes(value)
                if size > MAX_METADATA_VALUE_BYTES:
                    overages.append(
                        f"metadata.{key}: {size} bytes (limit {MAX_METADATA_VALUE_BYTES})"
                    )
                    size_overages = True
        if overages:
            issues.append(f"- {_source(document, index)}: {', '.join(overages)}")
    if issues:
        advice = []
        if size_overages:
            advice.append(
                "Use --truncate-oversized to shorten excerpts and omit complete examples that "
                "do not fit; source identity fields are preserved."
            )
        if structural_overages:
            advice.append("Metadata key sizes and counts must be corrected separately.")
        raise ValueError(
            f"{len(issues)} chunks exceed Chroma Cloud's default size limits. "
            "No embedding requests or cloud writes were made.\n"
            + "\n".join(issues)
            + "\n"
            + " ".join(advice)
            + " See https://docs.trychroma.com/cloud/quotas-limits."
        )


def validate_cloud_documents(documents: list[Document]) -> None:
    """Reject oversized records before embedding charges or cloud writes."""
    _validate(documents, include_sizes=True)


def _shorten(value: str, limit: int) -> str:
    if _bytes(value) <= limit:
        return value
    value = value.removesuffix(_EXCERPT_MARKER)
    prefix = value.encode("utf-8")[: limit - _bytes(_EXCERPT_MARKER)].decode(
        "utf-8", errors="ignore"
    )
    end = len(prefix)
    for token in _ATOMIC_PATTERN.finditer(value):
        if token.start() < end < token.end():
            prefix = value[: token.start()]
            break
    return prefix.rstrip() + _EXCERPT_MARKER


def _prose_keys(document: Document) -> list[str]:
    return [
        key
        for key, value in document.metadata.items()
        if isinstance(value, str) and key not in _CATALOG_KINDS and key not in _IDENTITY_KEYS
    ]


def _references(document: Document) -> set[tuple[str, str]]:
    values = [document.page_content, *(document.metadata[key] for key in _prose_keys(document))]
    return {reference for value in values for reference in REFERENCE_PATTERN.findall(value)}


def _catalogs(document: Document) -> dict[str, dict]:
    catalogs = {}
    for key in _CATALOG_KINDS:
        if key not in document.metadata:
            continue
        value = document.metadata[key]
        try:
            records = json.loads(value)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"Cannot shorten malformed example catalog metadata.{key}") from error
        if not isinstance(records, dict) or any(
            not isinstance(record, dict) for record in records.values()
        ):
            raise ValueError(f"Cannot shorten malformed example catalog metadata.{key}")
        catalogs[key] = records
    return catalogs


def _json(records: dict) -> str:
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


def _store_catalog(document: Document, key: str, records: dict) -> None:
    if records:
        document.metadata[key] = _json(records)
    else:
        document.metadata.pop(key, None)


def _shorten_prose(document: Document) -> None:
    document.page_content = _shorten(document.page_content, MAX_DOCUMENT_BYTES)
    for key in _prose_keys(document):
        document.metadata[key] = _shorten(document.metadata[key], MAX_METADATA_VALUE_BYTES)


def _replace_omitted(document: Document, omitted: set[tuple[str, str]]) -> None:
    def replace(match: re.Match[str]) -> str:
        return _OMITTED_MARKER if (match[1], match[2]) in omitted else match[0]

    document.page_content = REFERENCE_PATTERN.sub(replace, document.page_content)
    for key in _prose_keys(document):
        document.metadata[key] = REFERENCE_PATTERN.sub(replace, document.metadata[key])


def _changed_fields(original: Document, shortened: Document) -> list[str]:
    changes = []
    if original.page_content != shortened.page_content:
        changes.append(
            f"document: {_bytes(original.page_content)} -> {_bytes(shortened.page_content)} bytes"
        )
    for key in original.metadata:
        before = original.metadata[key]
        after = shortened.metadata.get(key)
        if before != after:
            changes.append(f"metadata.{key}: {_bytes(before)} -> {_bytes(after or '')} bytes")
    return changes


def truncate_cloud_documents(documents: list[Document]) -> tuple[list[Document], list[str]]:
    """Shorten copies of excerpts and omit whole examples, preserving source identity."""
    _validate(documents, include_sizes=False)
    shortened_documents = []
    reports = []
    for index, original in enumerate(documents):
        document = deepcopy(original)
        original_catalogs = _catalogs(original)
        original_references = _references(original)
        _shorten_prose(document)
        references = _references(document)
        removed_references = original_references - references
        omitted = set()
        for key, original_records in original_catalogs.items():
            kind = _CATALOG_KINDS[key]
            records = {
                reference: record
                for reference, record in original_records.items()
                if (kind, reference) not in removed_references
            }
            if (
                records == original_records
                and _bytes(document.metadata[key]) <= MAX_METADATA_VALUE_BYTES
            ):
                continue
            if _bytes(_json(records)) > MAX_METADATA_VALUE_BYTES:
                kept = {}
                for reference, record in records.items():
                    candidate = {**kept, reference: record}
                    if (kind, reference) in references and _bytes(
                        _json(candidate)
                    ) <= MAX_METADATA_VALUE_BYTES:
                        kept = candidate
                records = kept
            omitted.update(
                (kind, reference) for reference in original_records.keys() - records.keys()
            )
            _store_catalog(document, key, records)

        _replace_omitted(document, omitted)
        _shorten_prose(document)
        removed_references = original_references - _references(document)
        final_catalogs = _catalogs(document)
        for key, records in final_catalogs.items():
            kind = _CATALOG_KINDS[key]
            retained = {
                reference: record
                for reference, record in records.items()
                if (kind, reference) not in removed_references
            }
            if retained != records:
                _store_catalog(document, key, retained)
        changes = _changed_fields(original, document)
        if changes:
            kept = sum(len(records) for records in _catalogs(document).values())
            omitted_count = sum(len(records) for records in original_catalogs.values()) - kept
            reports.append(
                f"{_source(original, index)}: {'; '.join(changes)}; "
                f"examples kept {kept}, omitted {omitted_count}"
            )
        shortened_documents.append(document)
    validate_cloud_documents(shortened_documents)
    return shortened_documents, reports
