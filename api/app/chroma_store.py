from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.config import Settings


def create_chroma_store(
    settings: Settings,
    embedding_function: Embeddings | None = None,
) -> Chroma:
    embeddings = embedding_function or OpenAIEmbeddings(model=settings.embedding_model)
    common = {
        "collection_name": settings.chroma_collection,
        "embedding_function": embeddings,
    }

    if settings.chroma_api_key:
        return Chroma(
            **common,
            chroma_cloud_api_key=settings.chroma_api_key.get_secret_value(),
            tenant=settings.chroma_tenant,
            database=settings.chroma_database,
        )

    if settings.chroma_path is None:
        raise ValueError("CHROMA_PATH is required for a local Chroma store")

    return Chroma(**common, persist_directory=str(settings.chroma_path))
