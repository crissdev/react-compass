from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.config import get_settings


def markdown_files(path: Path) -> list[Path]:
    return sorted(file for file in path.glob("**/*.md") if file.is_file())


def source_url(source_type: str, root: Path, file: Path) -> str:
    relative = file.relative_to(root).with_suffix("")
    if relative.name == "index":
        relative = relative.parent
    return f"https://react.dev/{source_type}/{relative.as_posix()}".rstrip("/")


def documents_for_file(source_type: str, root: Path, file: Path) -> list[Document]:
    content = file.read_text(encoding="utf-8")
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=False,
    )
    documents = splitter.split_text(content)
    title = str(documents[0].metadata.get("h1") if documents else file.stem)

    for document in documents:
        section = document.metadata.get("h3") or document.metadata.get("h2") or title
        section = str(section).split(" {/*", maxsplit=1)[0].strip()
        document.metadata.update(
            {
                "source_type": source_type,
                "source_url": source_url(source_type, root, file),
                "section": section,
                "language": "en",
                "title": title,
            }
        )
    return documents


def main() -> None:
    settings = get_settings()
    store = Chroma(
        persist_directory=str(settings.chroma_path),
        collection_name=settings.chroma_collection,
    )
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
    print(f"Indexed {len(documents)} documentation chunks in {settings.chroma_path}")


if __name__ == "__main__":
    main()
