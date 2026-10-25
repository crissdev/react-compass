import json
from copy import deepcopy

import pytest
from langchain_core.documents import Document

from app.cloud_records import (
    MAX_DOCUMENT_BYTES,
    MAX_METADATA_VALUE_BYTES,
    truncate_cloud_documents,
    validate_cloud_documents,
)
from app.ingest_cloud import document_ids


def _document(content: str = "Section", **metadata: str) -> Document:
    return Document(
        page_content=content,
        metadata={
            "source_url": "https://react.dev/learn/example",
            "source_type": "learn",
            "section": "Usage",
            **metadata,
        },
    )


def _json(records: dict, **kwargs: object) -> str:
    return json.dumps(records, ensure_ascii=False, **kwargs)


@pytest.mark.parametrize("content", ["x" * MAX_DOCUMENT_BYTES, "\U0001f680" * 4096])
def test_document_byte_boundary_is_valid_and_unchanged(content: str) -> None:
    document = _document(content)

    validate_cloud_documents([document])
    shortened, reports = truncate_cloud_documents([document])

    assert shortened == [document]
    assert shortened[0] is not document
    assert reports == []


@pytest.mark.parametrize("content", ["x" * (MAX_DOCUMENT_BYTES + 1), "\U0001f680" * 4097])
def test_oversized_utf8_document_has_valid_visible_excerpt(content: str) -> None:
    original = _document(content)

    shortened, reports = truncate_cloud_documents([original])

    result = shortened[0]
    assert len(result.page_content.encode("utf-8")) <= MAX_DOCUMENT_BYTES
    assert result.page_content.endswith("[Excerpt shortened.]")
    assert "\ufffd" not in result.page_content
    assert result.metadata == original.metadata
    assert len(reports) == 1
    assert "https://react.dev/learn/example Usage" in reports[0]
    assert f"document: {len(content.encode('utf-8'))} ->" in reports[0]
    assert "examples kept 0, omitted 0" in reports[0]
    assert original.page_content == content


@pytest.mark.parametrize("value", ["x" * MAX_METADATA_VALUE_BYTES, "\u00e9" * 4091])
def test_metadata_byte_boundary_is_valid_and_unchanged(value: str) -> None:
    document = _document(intro=value)

    validate_cloud_documents([document])
    shortened, reports = truncate_cloud_documents([document])

    assert shortened == [document]
    assert reports == []


@pytest.mark.parametrize("key", ["intro", "deprecated", "experimental", "other_prose"])
def test_generic_prose_metadata_is_shortened_without_changing_identity(key: str) -> None:
    document = _document(**{key: "\u6f22\u5b57" * 2000})
    original_metadata = deepcopy(document.metadata)

    shortened, reports = truncate_cloud_documents([document])

    value = shortened[0].metadata[key]
    assert len(value.encode("utf-8")) <= MAX_METADATA_VALUE_BYTES
    assert value.endswith("[Excerpt shortened.]")
    assert "\ufffd" not in value
    assert shortened[0].metadata["source_url"] == document.metadata["source_url"]
    assert shortened[0].metadata["section"] == document.metadata["section"]
    assert document.metadata == original_metadata
    assert f"metadata.{key}: 12000 ->" in reports[0]


def test_catalog_that_fits_is_preserved_byte_for_byte_including_unknown_records() -> None:
    raw = _json({"example": {"content": "<Sandpack>\u6f22\u5b57</Sandpack>"}}, indent=4)
    document = _document("[Sandpack: unknown]", sandpacks=raw)

    shortened, reports = truncate_cloud_documents([document])

    assert shortened == [document]
    assert shortened[0].metadata["sandpacks"] == raw
    assert reports == []


def test_json_compaction_avoids_omitting_complete_examples() -> None:
    record = {"content": "<Sandpack>\n\u6f22\u5b57 code\n</Sandpack>"}
    raw = _json({"example": record}, indent=4096)
    assert len(raw.encode()) > MAX_METADATA_VALUE_BYTES
    document = _document("[Sandpack: example]", sandpacks=raw)

    shortened, reports = truncate_cloud_documents([document])

    assert json.loads(shortened[0].metadata["sandpacks"]) == {"example": record}
    assert shortened[0].page_content == document.page_content
    assert len(shortened[0].metadata["sandpacks"].encode()) <= MAX_METADATA_VALUE_BYTES
    assert "examples kept 1, omitted 0" in reports[0]


def test_oversized_example_is_omitted_whole_and_later_small_record_is_kept_exactly() -> None:
    large = {"content": "<Sandpack>" + "\u6f22" * 3000 + "</Sandpack>"}
    small = {"content": "<Sandpack>\n```js\nconst value = '\u6f22';\n```\n</Sandpack>"}
    document = _document(
        "[Sandpack: large]\n[Sandpack: small]\n[Sandpack: unknown]",
        sandpacks=_json({"large": large, "small": small}),
        intro="Intro [Sandpack: large] [Sandpack: small]",
        deprecated="Notice [Sandpack: large]",
        experimental="Notice [Sandpack: large]",
        other_prose="Context [Sandpack: large]",
    )
    original = deepcopy(document)

    shortened, reports = truncate_cloud_documents([document])

    result = shortened[0]
    assert json.loads(result.metadata["sandpacks"]) == {"small": small}
    assert "[Sandpack: small]" in result.page_content
    assert "[Sandpack: unknown]" in result.page_content
    assert "[Example omitted.]" in result.page_content
    for value in [
        result.page_content,
        *(result.metadata[key] for key in ("intro", "deprecated", "experimental", "other_prose")),
    ]:
        assert "[Sandpack: large]" not in value
        assert "[Example omitted.]" in value
    assert "examples kept 1, omitted 1" in reports[0]
    assert document == original
    validate_cloud_documents(shortened)


def test_snippet_and_sandpack_ids_have_independent_namespaces() -> None:
    sandpack = {"content": "<Sandpack>const value = 1;</Sandpack>"}
    snippet = {
        "content": "```js\n" + "x" * MAX_METADATA_VALUE_BYTES + "\n```",
        "code": "x" * MAX_METADATA_VALUE_BYTES,
    }
    document = _document(
        "[Sandpack: shared] [CodeSnippet: shared] [CodeSnippet: unknown]",
        sandpacks=_json({"shared": sandpack}),
        code_snippets=_json({"shared": snippet}),
    )

    shortened, reports = truncate_cloud_documents([document])

    result = shortened[0]
    assert json.loads(result.metadata["sandpacks"]) == {"shared": sandpack}
    assert "code_snippets" not in result.metadata
    assert result.page_content == "[Sandpack: shared] [Example omitted.] [CodeSnippet: unknown]"
    assert "examples kept 1, omitted 1" in reports[0]


def test_excerpt_never_splits_example_reference_at_its_utf8_boundary() -> None:
    prefix = "\u00e9" * 8175
    document = _document(
        prefix + "[Sandpack: example]" + "x" * 100,
        sandpacks=_json({"example": {"content": "<Sandpack>Small</Sandpack>"}}),
    )

    shortened, _ = truncate_cloud_documents([document])

    result = shortened[0]
    assert result.page_content == prefix + "\n\n[Excerpt shortened.]"
    assert "[Sandpack:" not in result.page_content
    assert "sandpacks" not in result.metadata
    validate_cloud_documents(shortened)


def test_prose_trimming_prunes_only_catalog_records_whose_references_were_lost() -> None:
    early = {"content": "<Sandpack>Early</Sandpack>"}
    late = {"content": "<Sandpack>Late</Sandpack>"}
    document = _document(
        "[Sandpack: early] " + "x" * MAX_DOCUMENT_BYTES + " [Sandpack: late]",
        sandpacks=_json({"early": early, "late": late}, indent=4),
    )

    shortened, reports = truncate_cloud_documents([document])

    assert json.loads(shortened[0].metadata["sandpacks"]) == {"early": early}
    assert "[Sandpack: early]" in shortened[0].page_content
    assert "[Sandpack: late]" not in shortened[0].page_content
    assert "examples kept 1, omitted 1" in reports[0]


def test_reference_preserved_in_intro_keeps_example_cut_from_document() -> None:
    raw = _json({"late": {"content": "<Sandpack>Late</Sandpack>"}}, indent=4)
    document = _document(
        "x" * MAX_DOCUMENT_BYTES + " [Sandpack: late]",
        intro="Introduction [Sandpack: late]",
        sandpacks=raw,
    )

    shortened, reports = truncate_cloud_documents([document])

    assert shortened[0].metadata["sandpacks"] == raw
    assert shortened[0].metadata["intro"] == document.metadata["intro"]
    assert "examples kept 1, omitted 0" in reports[0]


def test_multiple_examples_use_exact_serialized_byte_budget() -> None:
    record = {"content": "\u6f22" * 1500}
    document = _document(
        "[Sandpack: first] [Sandpack: second]",
        sandpacks=_json({"first": record, "second": record}),
    )

    shortened, _ = truncate_cloud_documents([document])

    assert json.loads(shortened[0].metadata["sandpacks"]) == {"first": record}
    assert shortened[0].page_content == "[Sandpack: first] [Example omitted.]"
    validate_cloud_documents(shortened)


def test_transform_and_content_ids_are_deterministic_and_idempotent() -> None:
    documents = [
        _document(
            "\U0001f680" * 5000,
            intro="\u6f22" * 4000,
        ),
        _document(
            "[Sandpack: large] [Sandpack: small] [Sandpack: unknown]",
            sandpacks=_json({"large": {"content": "x" * 9000}, "small": {"content": "Small"}}),
        ),
    ]

    first, reports = truncate_cloud_documents(documents)
    repeat, repeat_reports = truncate_cloud_documents(documents)
    second, second_reports = truncate_cloud_documents(first)

    assert len(reports) == 2
    assert repeat == first
    assert repeat_reports == reports
    assert second == first
    assert second_reports == []
    assert document_ids(second) == document_ids(first)


@pytest.mark.parametrize("field", ["source_url", "source_type", "title", "section", "language"])
def test_source_identity_fields_are_never_truncated(field: str) -> None:
    document = _document(**{field: "x" * (MAX_METADATA_VALUE_BYTES + 1)})
    original = deepcopy(document)

    with pytest.raises(ValueError, match=f"metadata.{field}"):
        truncate_cloud_documents([document])

    assert document == original


@pytest.mark.parametrize(
    "metadata", [{"\U0001f680" * 10: "value"}, {f"key-{index}": "value" for index in range(33)}]
)
def test_structural_metadata_overages_cannot_be_fixed_by_truncation(metadata: dict) -> None:
    document = Document(page_content="Section", metadata=metadata)

    with pytest.raises(ValueError, match="corrected separately") as error:
        truncate_cloud_documents([document])

    assert "--truncate-oversized" not in str(error.value)


def test_validation_reports_size_overages_with_opt_in_truncation_advice() -> None:
    with pytest.raises(ValueError, match="--truncate-oversized") as error:
        validate_cloud_documents([_document("x" * (MAX_DOCUMENT_BYTES + 1))])

    assert "https://react.dev/learn/example Usage" in str(error.value)


@pytest.mark.parametrize("catalog", ["{not-json", "[]", '{"example":"not-a-record"}'])
def test_malformed_example_catalogs_fail_without_corrupting_source(catalog: str) -> None:
    document = _document("[Sandpack: example]", sandpacks=catalog)
    original = deepcopy(document)

    with pytest.raises(ValueError, match="malformed example catalog"):
        truncate_cloud_documents([document])

    assert document == original
