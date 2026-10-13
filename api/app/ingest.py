from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.chroma_store import create_chroma_store
from app.config import get_settings


def markdown_files(path: Path) -> list[Path]:
    return sorted(file for file in path.glob("**/*.md") if file.is_file())


def source_url(source_type: str, root: Path, file: Path) -> str:
    relative = file.relative_to(root).with_suffix("")
    if relative.name == "index":
        relative = relative.parent
    return f"https://react.dev/{source_type}/{relative.as_posix()}".rstrip("/")


def frontmatter_title(content: str) -> str | None:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() == "title":
            return value.strip().strip("\"'") or None

    return None


def split_markdown_sections(content: str) -> list[Document]:
    """Split Markdown into sections, excluding content without a level-two heading."""
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=False,
    )
    return [document for document in splitter.split_text(content) if document.metadata.get("h2")]


def resolve_document_title(content: str, documents: list[Document], fallback_title: str) -> str:
    return str(
        frontmatter_title(content)
        or (documents[0].metadata.get("h1") if documents else None)
        or fallback_title
    )


def section_title(document: Document, title: str) -> str:
    section = document.metadata.get("h3") or document.metadata.get("h2") or title
    return str(section).split(" {/*", maxsplit=1)[0].strip()


def add_source_metadata(
    documents: list[Document], source_type: str, root: Path, file: Path, title: str
) -> list[Document]:
    """Attach source metadata to each document in place."""
    for document in documents:
        document.metadata.update(
            {
                "source_type": source_type,
                "source_url": source_url(source_type, root, file),
                "section": section_title(document, title),
                "language": "en",
                "title": title,
            }
        )
    return documents


def documents_for_file(source_type: str, root: Path, file: Path) -> list[Document]:
    content = file.read_text(encoding="utf-8")
    documents = split_markdown_sections(content)
    title = resolve_document_title(content, documents, file.stem)
    return add_source_metadata(documents, source_type, root, file, title)


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
        for file in markdown_files(root):
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
