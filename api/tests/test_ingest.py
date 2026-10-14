import json
import re
from pathlib import Path

import pytest
from langchain_core.documents import Document

from app.ingest import _parse_frontmatter, documents_for_file


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


@pytest.mark.parametrize(
    ("content", "title", "body"),
    [
        ("", None, ""),
        ("---", None, "---"),
        ("## Usage\n\nBody.\n", None, "## Usage\n\nBody.\n"),
        ("Intro\n---\ntitle: Body title\n---\n", None, "Intro\n---\ntitle: Body title\n---\n"),
        ("---\ntitle: 'Hooks: an overview'\n---\n\nBody.\n", "Hooks: an overview", "\nBody.\n"),
        ('---\ntitle: "Hooks"\n---', "Hooks", ""),
        ("---\n---\ntitle: Body title\n", None, "title: Body title\n"),
        ("---\ntitle: First\ntitle: Second\n---\nBody.", "First", "Body."),
        ("---\ntitle: ''\ntitle: Second\n---\nBody.", None, "Body."),
        (" --- \r\ntitle: Hooks\r\n --- \r\n\r\n  Body.\r\n", "Hooks", "\r\n  Body.\r\n"),
        ("---\ntitle: Hooks\n## Usage\n", "Hooks", "---\ntitle: Hooks\n## Usage\n"),
    ],
)
def test_frontmatter_parsing_preserves_the_title_and_remaining_content(
    content: str, title: str | None, body: str
) -> None:
    parsed = _parse_frontmatter(content)

    assert parsed.frontmatter_title == title
    assert parsed.content == body


@pytest.mark.parametrize(
    ("frontmatter", "heading", "expected_title"),
    [
        ("---\ntitle: ''\n---\n", "# Page heading\n\n", "Page heading"),
        ("---\n---\n", "# Page heading\n\n", "Page heading"),
        ("", "", "examples"),
    ],
)
def test_documents_fall_back_without_a_frontmatter_title(
    tmp_path: Path, frontmatter: str, heading: str, expected_title: str
) -> None:
    documents = _documents_for_content(tmp_path, f"{frontmatter}{heading}## Usage\n\nBody.\n")

    assert len(documents) == 1
    assert documents[0].metadata["title"] == expected_title


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


def test_page_intro_and_its_examples_are_copied_to_every_chunk(tmp_path: Path) -> None:
    info = "js src/Intro.js active {1,3}"
    code = "const [value, setValue] = useState(0);\n\n  console.log(value);\n"
    snippet = f"```{info}\n{code}```"
    sandpack = (
        '<Sandpack showConsole autorun="false">\n'
        "```js src/App.js active\n"
        'export default function App() { return "</Intro>"; }\n'
        "```\n\n"
        "```css src/styles.css hidden\n"
        "body { color: red; }\n"
        "```\n"
        "</Sandpack>"
    )
    local_snippet = "```js\nconsole.log('Section example');\n```"
    documents = _documents_for_content(
        tmp_path,
        "---\ntitle: 'State'\n"
        "description: |\n  <Intro>Frontmatter-only intro.</Intro>\n---\n\n"
        "<Intro>\n\n**State** lets you remember a [value](/learn/state).\n\n"
        f"{snippet}\n\n{sandpack}\n\n</Intro>\n\n"
        "Other preamble content.\n\n"
        f"## Reference\n\n{local_snippet}\n\n"
        "### Parameters\n\nPass an initial value.\n\n"
        "## Usage\n\nUpdate the value.\n",
    )

    assert len(documents) == 3
    intro = documents[0].metadata["intro"]
    intro_snippet_ids = _references(intro, "CodeSnippet")
    intro_sandpack_ids = _references(intro, "Sandpack")
    assert len(intro_snippet_ids) == len(intro_sandpack_ids) == 1
    assert intro == (
        "**State** lets you remember a [value](/learn/state).\n\n"
        f"[CodeSnippet: {intro_snippet_ids[0]}]\n\n[Sandpack: {intro_sandpack_ids[0]}]"
    )
    for document in documents:
        assert document.metadata["intro"] == intro
        assert "<Intro>" not in document.page_content
        assert "remember a" not in document.page_content
        assert "Other preamble" not in document.page_content
        assert _records(document, "code_snippets")[intro_snippet_ids[0]] == {
            "content": snippet,
            "info": info,
            "language": "js",
            "meta": "src/Intro.js active {1,3}",
            "code": code,
        }
        assert _records(document, "sandpacks")[intro_sandpack_ids[0]]["content"] == sandpack
        assert set(_records(document, "code_snippets")) == set(
            intro_snippet_ids + _references(document.page_content, "CodeSnippet")
        )
        assert set(_records(document, "sandpacks")) == set(intro_sandpack_ids)
    assert len(_records(documents[0], "code_snippets")) == 2
    assert len(_records(documents[1], "code_snippets")) == 1
    assert len(_records(documents[2], "code_snippets")) == 1


def test_multiple_page_intros_are_combined_without_section_intros(tmp_path: Path) -> None:
    local_intro = "<Intro>This introduction belongs to a section.</Intro>"
    documents = _documents_for_content(
        tmp_path,
        "<Intro>First introduction.</Intro>\n\n"
        "<Intro>Second introduction.</Intro>\n\n"
        f"## First section\n\n{local_intro}\n\n"
        "## Second section\n\nMore details.\n",
    )

    assert len(documents) == 2
    assert all(
        document.metadata["intro"] == "First introduction.\n\nSecond introduction."
        for document in documents
    )
    assert local_intro in documents[0].page_content
    assert local_intro not in documents[1].page_content


@pytest.mark.parametrize(
    "preamble",
    [
        "Ordinary preamble prose.",
        "<Intro>\n \n</Intro>",
        "<IntroBadge />\n\n<Intro />",
        "```md\n<Intro>A literal intro.</Intro>\n```",
        "<Sandpack>\n<Intro>A literal intro.</Intro>\n</Sandpack>",
    ],
)
def test_missing_empty_or_example_intros_do_not_add_page_metadata(
    tmp_path: Path, preamble: str
) -> None:
    documents = _documents_for_content(
        tmp_path,
        f"{preamble}\n\n## Section\n\n<Intro>A local introduction.</Intro>\n",
    )

    assert len(documents) == 1
    assert "intro" not in documents[0].metadata
    assert not _records(documents[0], "code_snippets")
    assert not _records(documents[0], "sandpacks")


def test_intro_code_hides_fake_headings_and_intro_tag_literals(tmp_path: Path) -> None:
    snippet = "~~~md src/example.md\n## A code heading\n</Intro>\n<Intro>Literal.</Intro>\n~~~"
    documents = _documents_for_content(
        tmp_path,
        f"<Intro>\nA summary.\n\n{snippet}\n\nMore summary.\n</Intro>\n\n"
        "## Real section\n\nDetails.\n",
    )

    assert len(documents) == 1
    document = documents[0]
    intro = document.metadata["intro"]
    snippet_ids = _references(intro, "CodeSnippet")
    assert len(snippet_ids) == 1
    assert intro == f"A summary.\n\n[CodeSnippet: {snippet_ids[0]}]\n\nMore summary."
    assert _records(document, "code_snippets")[snippet_ids[0]]["content"] == snippet
    assert document.metadata["section"] == "Real section"
    assert "summary" not in document.page_content


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


@pytest.mark.parametrize(
    ("component", "key", "notice_text"),
    [
        ("Deprecated", "deprecated", "Use the newer API instead."),
        (
            "Experimental",
            "experimental",
            "**This API is experimental.**\n\n"
            "- Install `react@experimental`.\n"
            "- Don't use it in production.\n\n"
            "Only available in [Server Components](/reference/rsc/use-client).",
        ),
    ],
)
def test_page_notice_is_copied_to_every_chunk_without_indexing_the_intro(
    tmp_path: Path,
    component: str,
    key: str,
    notice_text: str,
) -> None:
    notice = f"<{component}>\n{notice_text}\n</{component}>"
    local_notice = f"<{component}>Only this example has a notice.</{component}>"
    documents = _documents_for_content(
        tmp_path,
        "---\n"
        "title: 'Legacy API'\n"
        "description: |\n"
        "  ## This YAML value is not a section\n"
        f"  <{component}>Frontmatter-only information.</{component}>\n"
        "---\n\n"
        f"{notice}\n\nIntroduction that should not be indexed.\n\n"
        "## Usage\n\nUse this API carefully.\n\n"
        f"### Legacy example\n\n{local_notice}\n\nAn older usage.\n\n"
        "## Alternatives\n\nUse the replacement API.\n",
    )

    assert len(documents) == 3
    for document in documents:
        assert document.metadata["title"] == "Legacy API"
        assert document.metadata[key] == notice_text
        assert "Frontmatter-only" not in document.page_content
        assert "This YAML value" not in document.page_content
        assert "Introduction that" not in document.page_content
        assert notice_text not in document.page_content
    assert local_notice in documents[1].page_content
    assert local_notice not in documents[0].page_content
    assert local_notice not in documents[2].page_content


def test_multiple_page_experimental_notices_are_combined(tmp_path: Path) -> None:
    documents = _documents_for_content(
        tmp_path,
        "<Experimental>\nFirst warning.\n</Experimental>\n\n"
        "<Experimental>\nSecond warning.\n</Experimental>\n\n"
        "## Usage\n\nUse carefully.\n",
    )

    assert documents[0].metadata["experimental"] == "First warning.\n\nSecond warning."


@pytest.mark.parametrize(
    "intro",
    [
        "```md\n## Fake section\n<Experimental>A literal.</Experimental>\n```",
        "<Sandpack>\n## Fake section\n<Experimental>A literal.</Experimental>\n</Sandpack>",
        "<ExperimentalBadge />\n\n<Experimental />",
    ],
)
def test_intro_examples_and_badges_do_not_mark_a_page_experimental(
    tmp_path: Path, intro: str
) -> None:
    documents = _documents_for_content(tmp_path, f"{intro}\n\n## Usage\n\nStable API.\n")

    assert len(documents) == 1
    assert "experimental" not in documents[0].metadata


def test_section_experimental_notice_stays_local(tmp_path: Path) -> None:
    notice = "<Experimental>This example is experimental.</Experimental>"
    documents = _documents_for_content(
        tmp_path,
        f"## Experimental example\n\n{notice}\n\n## Stable example\n\nStable API.\n",
    )

    assert len(documents) == 2
    assert all("experimental" not in document.metadata for document in documents)
    assert notice in documents[0].page_content
    assert notice not in documents[1].page_content


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
