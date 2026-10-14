from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.config import Settings


class ChromaDefaultEmbeddings(Embeddings):
    """Use Chroma's local default model through LangChain's embedding interface."""

    def __init__(self) -> None:
        self._function = DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vector)) for vector in self._function(input=texts)]

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, self._function.embed_query(input=[text])[0]))


def create_chroma_store(
    settings: Settings,
    embedding_function: Embeddings | None = None,
) -> Chroma:
    if embedding_function is not None:
        embeddings = embedding_function
    elif settings.embedding_model == "default":
        embeddings = ChromaDefaultEmbeddings()
    else:
        embeddings = OpenAIEmbeddings(model=settings.embedding_model)
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
