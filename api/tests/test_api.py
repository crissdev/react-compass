import json

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.main import app
from app.models import AnswerResponse, SourceExcerpt
from app.service import format_sources, get_search_service


class FakeSearchService:
    async def retrieve(self, question: str) -> list[Document]:
        return [Document(page_content=f"Documentation about {question}")]

    async def answer(self, question: str, documents: list[Document]) -> AnswerResponse:
        return await self.search(question)

    async def search(self, question: str) -> AnswerResponse:
        return AnswerResponse(
            message=f"`useState` answers {question} [1]",
            sources=[
                SourceExcerpt(
                    id="1",
                    citation=1,
                    title="useState",
                    section="Reference",
                    source_type="reference",
                    source_url="https://react.dev/reference/react/useState",
                    excerpt="useState declares a state variable.",
                )
            ],
        )


def test_format_sources_deduplicates_and_truncates() -> None:
    document = Document(
        page_content="word " * 100,
        metadata={
            "title": "useState",
            "section": "Reference",
            "source_type": "reference",
            "source_url": "https://react.dev/reference/react/useState.md",
        },
    )

    sources = format_sources([document, document])

    assert len(sources) == 1
    assert sources[0].citation == 1
    assert len(sources[0].excerpt) <= 420
    assert sources[0].excerpt.endswith("...")
    assert sources[0].source_url == "https://react.dev/reference/react/useState"


def test_stream_returns_status_and_result_events() -> None:
    app.dependency_overrides[get_search_service] = lambda: FakeSearchService()
    client = TestClient(app)

    try:
        response = client.post("/ask/stream", json={"question": "How does useState work?"})
    finally:
        app.dependency_overrides.clear()

    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200
    assert [event["type"] for event in events] == ["status", "status", "result"]
    assert events[-1]["data"]["sources"][0]["title"] == "useState"


def test_question_is_validated() -> None:
    app.dependency_overrides[get_search_service] = lambda: FakeSearchService()
    client = TestClient(app)
    try:
        response = client.post("/ask/stream", json={"question": ""})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
