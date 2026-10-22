from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.chroma_store import create_chroma_store
from app.config import get_settings
from app.markdown_metadata import add_markdown_metadata, extract_markdown_metadata


def _markdown_files(path: Path) -> list[Path]:
    return sorted(
        file for file in path.glob("**/*.md") if file.name != "index.md" and file.is_file()
    )


def _source_url(source_type: str, root: Path, file: Path) -> str:
    relative = file.relative_to(root).with_suffix("")
    if relative.name == "index":
        relative = relative.parent
    return f"https://react.dev/{source_type}/{relative.as_posix()}".rstrip("/")


@dataclass(frozen=True)
class _ParsedMarkdown:
    frontmatter_title: str | None
    content: str


def _parse_frontmatter(content: str) -> _ParsedMarkdown:
    """Extract the scalar title and body without splitting the full document."""
    line_end = content.find("\n")
    if line_end == -1 or content[:line_end].strip() != "---":
        return _ParsedMarkdown(None, content)

    title = None
    title_found = False
    line_start = line_end + 1
    while line_start < len(content):
        line_end = content.find("\n", line_start)
        if line_end == -1:
            line_end = len(content)
        line = content[line_start:line_end]
        if line.strip() == "---":
            return _ParsedMarkdown(title, content[line_end + 1 :])
        key, separator, value = line.partition(":")
        if not title_found and separator and key.strip() == "title":
            title = value.strip().strip("\"'") or None
            title_found = True
        line_start = line_end + 1

    return _ParsedMarkdown(title, content)


def _split_markdown_sections(content: str) -> list[Document]:
    """Split Markdown into sections, excluding content without a level-two heading."""
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=False,
    )
    return [document for document in splitter.split_text(content) if document.metadata.get("h2")]


def _resolve_document_title(
    frontmatter_title: str | None, documents: list[Document], fallback_title: str
) -> str:
    return str(
        frontmatter_title
        or (documents[0].metadata.get("h1") if documents else None)
        or fallback_title
    )


def _section_title(document: Document, title: str) -> str:
    section = document.metadata.get("h3") or document.metadata.get("h2") or title
    return str(section).split(" {/*", maxsplit=1)[0].strip()


def _add_source_metadata(
    documents: list[Document], source_type: str, root: Path, file: Path, title: str
) -> list[Document]:
    """Attach source metadata to each document in place."""
    for document in documents:
        document.metadata.update(
            {
                "source_type": source_type,
                "source_url": _source_url(source_type, root, file),
                "section": _section_title(document, title),
                "language": "en",
                "title": title,
            }
        )
    return documents


def documents_for_file(source_type: str, root: Path, file: Path) -> list[Document]:
    parsed = _parse_frontmatter(file.read_text(encoding="utf-8"))
    markdown, metadata = extract_markdown_metadata(
        parsed.content, _source_url(source_type, root, file)
    )
    documents = _split_markdown_sections(markdown)
    title = _resolve_document_title(parsed.frontmatter_title, documents, file.stem)
    add_markdown_metadata(documents, metadata)
    return _add_source_metadata(documents, source_type, root, file, title)


def main() -> None:
    settings = get_settings()
    store = create_chroma_store(settings)
    roots = {
        "reference": settings.react_docs_reference_path,
        "learn": settings.react_docs_learn_path,
        "blog": settings.react_docs_blog_path,
    }

    documents: list[Document] = []
    for source_type, root in roots.items():
        for file in _markdown_files(root):
            documents.extend(documents_for_file(source_type, root, file))

    if not documents:
        raise RuntimeError("No React documentation Markdown files were found")

    store.add_documents(documents)
    destination = (
        f"Chroma Cloud database {settings.chroma_database}"
        if settings.uses_chroma_cloud
        else str(settings.chroma_path)
    )
    print(f"Indexed {len(documents)} documentation chunks in {destination}")


if __name__ == "__main__":
    main()
