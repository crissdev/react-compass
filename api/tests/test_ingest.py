from pathlib import Path

from app.ingest import documents_for_file


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
