import json
import re
from pathlib import Path

import pytest
from langchain_core.documents import Document

from app.ingest import documents_for_file


def _documents_for_content(tmp_path: Path, content: str) -> list[Document]:
    root = tmp_path / "learn"
    root.mkdir()
    file = root / "examples.md"
    file.write_text(content, encoding="utf-8")
    return documents_for_file("learn", root, file)


def _references(content: str, kind: str) -> list[str]:
    return re.findall(rf"\[{kind}: ([^\]]+)\]", content)


def _records(document: Document, key: str) -> dict[str, dict[str, str]]:
    value = document.metadata.get(key, "{}")
    assert isinstance(value, str)
    return json.loads(value)


def test_documents_use_the_frontmatter_title(tmp_path: Path) -> None:
    root = tmp_path / "learn"
    file = root / "escape-hatches.md"
    root.mkdir()
    file.write_text(
        "---\n"
        "title: 'Escape Hatches'\n"
        "---\n\n"
        "This introduction is intentionally not indexed.\n\n"
        "## Reusing logic with custom Hooks {/*reusing-logic-with-custom-hooks*/}\n\n"
        "Share reusable behavior.\n",
        encoding="utf-8",
    )

    documents = documents_for_file("learn", root, file)
    section_document = documents[0]

    assert len(documents) == 1
    assert "intentionally not indexed" not in section_document.page_content
    assert all(document.metadata["title"] == "Escape Hatches" for document in documents)
    assert section_document.metadata["section"] == "Reusing logic with custom Hooks"
    assert section_document.metadata["source_url"] == "https://react.dev/learn/escape-hatches"


def test_sandpacks_are_extracted_before_their_code_fences(tmp_path: Path) -> None:
    sandpack = (
        "<Sandpack showConsole autorun={false}>\n"
        "```js src/App.js active {1,3}\n"
        "export default function App() {\n"
        "  return <h1>Hello</h1>;\n"
        "}\n"
        "```\n\n"
        "```css src/styles.css hidden\n"
        "h1 { color: red; }\n"
        "```\n"
        "</Sandpack>"
    )
    standalone = "```js\nconsole.log('Outside the sandbox');\n```"
    documents = _documents_for_content(
        tmp_path,
        f"## Try an example\n\nBefore the example.\n\n{sandpack}\n\n"
        f"After the example.\n\n{standalone}\n",
    )

    assert len(documents) == 1
    document = documents[0]
    sandpack_ids = _references(document.page_content, "Sandpack")
    snippet_ids = _references(document.page_content, "CodeSnippet")
    assert len(sandpack_ids) == len(snippet_ids) == 1
    assert _records(document, "sandpacks")[sandpack_ids[0]]["content"] == sandpack
    assert _records(document, "code_snippets")[snippet_ids[0]]["content"] == standalone
    assert set(_records(document, "code_snippets")) == set(snippet_ids)
    assert "<Sandpack" not in document.page_content
    assert "```" not in document.page_content
    assert "Before the example." in document.page_content
    assert "After the example." in document.page_content


@pytest.mark.parametrize(
    ("info", "meta"),
    [
        (
            "js {expectedErrors: {'react-compiler': [5]}}",
            "{expectedErrors: {'react-compiler': [5]}}",
        ),
        ("js src/data.js", "src/data.js"),
        ("js src/Clock.js active {2,4-6}", "src/Clock.js active {2,4-6}"),
    ],
)
def test_snippet_rendering_metadata_is_preserved_verbatim(
    tmp_path: Path, info: str, meta: str
) -> None:
    code = "export const label = 'Clock';\n\n  console.log(label);\n"
    fence = f"```{info}\n{code}```"
    document = _documents_for_content(tmp_path, f"## Code example\n\n{fence}\n")[0]

    snippet_ids = _references(document.page_content, "CodeSnippet")
    assert len(snippet_ids) == 1
    record = _records(document, "code_snippets")[snippet_ids[0]]
    assert record["content"] == fence
    assert record["info"] == info
    assert record["language"] == "js"
    assert record["meta"] == meta
    assert record["code"] == code


def test_example_metadata_contains_only_references_in_its_chunk(tmp_path: Path) -> None:
    documents = _documents_for_content(
        tmp_path,
        "## First section\n\n"
        "<Sandpack>\n```js src/App.js\nconsole.log('First');\n```\n</Sandpack>\n\n"
        "## Second section\n\n"
        "```js src/data.js\nexport const value = 2;\n```\n\n"
        "## Third section\n\nOnly prose here.\n",
    )

    assert len(documents) == 3
    for document in documents:
        assert set(_records(document, "sandpacks")) == set(
            _references(document.page_content, "Sandpack")
        )
        assert set(_records(document, "code_snippets")) == set(
            _references(document.page_content, "CodeSnippet")
        )
    assert len(_records(documents[0], "sandpacks")) == 1
    assert len(_records(documents[1], "code_snippets")) == 1
    assert not _records(documents[2], "sandpacks")
    assert not _records(documents[2], "code_snippets")


def test_repeated_examples_have_distinct_stable_references(tmp_path: Path) -> None:
    root = tmp_path / "learn"
    root.mkdir()
    file = root / "repeated.md"
    snippet = "```js\nconsole.log('Same code');\n```"
    sandpack = f"<Sandpack>\n{snippet}\n</Sandpack>"
    file.write_text(
        f"## Repeated examples\n\n{snippet}\n\n{snippet}\n\n{sandpack}\n\n{sandpack}\n",
        encoding="utf-8",
    )

    first = documents_for_file("learn", root, file)
    second = documents_for_file("learn", root, file)

    assert [document.page_content for document in first] == [
        document.page_content for document in second
    ]
    assert [document.metadata for document in first] == [document.metadata for document in second]
    for kind, key in [("CodeSnippet", "code_snippets"), ("Sandpack", "sandpacks")]:
        ids = _references(first[0].page_content, kind)
        assert len(ids) == len(set(ids)) == 2
        assert set(_records(first[0], key)) == set(ids)


def test_page_deprecation_is_copied_to_every_chunk_without_indexing_the_intro(
    tmp_path: Path,
) -> None:
    notice = "<Deprecated>\nUse the newer API instead.\n</Deprecated>"
    local_notice = "<Deprecated>Only this example is deprecated.</Deprecated>"
    documents = _documents_for_content(
        tmp_path,
        "---\n"
        "title: 'Legacy API'\n"
        "description: |\n"
        "  ## This YAML value is not a section\n"
        "  Frontmatter-only information.\n"
        "---\n\n"
        f"{notice}\n\nIntroduction that should not be indexed.\n\n"
        "## Usage\n\nUse this API carefully.\n\n"
        f"### Legacy example\n\n{local_notice}\n\nAn older usage.\n\n"
        "## Alternatives\n\nUse the replacement API.\n",
    )

    assert len(documents) == 3
    for document in documents:
        assert document.metadata["title"] == "Legacy API"
        assert "Use the newer API instead." in document.metadata["deprecated"]
        assert "Only this example" not in document.metadata["deprecated"]
        assert "Frontmatter-only" not in document.page_content
        assert "This YAML value" not in document.page_content
        assert "Introduction that" not in document.page_content
        assert "Use the newer API instead." not in document.page_content
    assert local_notice in documents[1].page_content
    assert local_notice not in documents[0].page_content
    assert local_notice not in documents[2].page_content


@pytest.mark.parametrize(
    ("opening", "code", "closing"),
    [
        ("````js", "```\n## A code heading\n", "`````"),
        ("```js", "    ```\n## A code heading\n", "```"),
        ("~~~js", "~~\n```\n## A code heading\n", "~~~~"),
        ("   ```js", "## A code heading\n", "   ```"),
        ("\t```js", "## A code heading\n", "\t```"),
    ],
)
def test_fences_hide_component_literals_and_fake_headings(
    tmp_path: Path, opening: str, code: str, closing: str
) -> None:
    code += "<Sandpack>\n<Deprecated>This is a literal.</Deprecated>\n</Sandpack>\n"
    fence = f"{opening}\n{code}{closing}"
    documents = _documents_for_content(tmp_path, f"## Real section\n\n{fence}\n\nAfter the code.\n")

    assert len(documents) == 1
    document = documents[0]
    snippet_ids = _references(document.page_content, "CodeSnippet")
    assert len(snippet_ids) == 1
    record = _records(document, "code_snippets")[snippet_ids[0]]
    assert record["content"] == fence
    assert record["code"] == code
    assert not _records(document, "sandpacks")
    assert not document.metadata.get("deprecated")
    assert document.metadata["section"] == "Real section"
    assert "After the code." in document.page_content


def test_sandpack_headings_and_intro_code_are_not_indexed_as_sections(tmp_path: Path) -> None:
    sandpack = (
        "<Sandpack>\n"
        "## Not a documentation section\n"
        "```js src/App.js\n"
        'const closingTag = "</Sandpack>";\n'
        "```\n"
        "</Sandpack>"
    )
    documents = _documents_for_content(
        tmp_path,
        "```md\n## A heading in introductory code\n```\n\n"
        f"{sandpack}\n\n## Real section\n\n{sandpack}\n\nThe explanation.\n",
    )

    assert len(documents) == 1
    document = documents[0]
    assert document.metadata["section"] == "Real section"
    ids = _references(document.page_content, "Sandpack")
    assert len(ids) == 1
    assert set(_records(document, "sandpacks")) == set(ids)
    assert _records(document, "sandpacks")[ids[0]]["content"] == sandpack
    assert not _records(document, "code_snippets")
    assert "Not a documentation section" not in document.page_content
    assert "A heading in introductory code" not in document.page_content
