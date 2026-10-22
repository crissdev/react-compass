import asyncio
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from langsmith import tracing_context
from starlette.requests import ClientDisconnect
from starlette.types import Message, Scope

from app.main import SEARCH_TIMEOUT_MESSAGE, app, settings
from app.models import AnswerResponse, GeneratedAnswer, QuestionClassification
from app.service import ReactDocsSearchService, get_search_service
from app.streaming import CancellableStreamingResponse


class BlockingSearchService:
    def __init__(self, blocked_stage: str) -> None:
        self.blocked_stage = blocked_stage
        self.cancelled = False

    async def block(self, stage: str) -> None:
        if stage == self.blocked_stage:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    async def classify(self, question: str) -> QuestionClassification:
        await self.block("classifying")
        return QuestionClassification(category="react")

    async def retrieve(self, question: str) -> list[Document]:
        await self.block("retrieving")
        return []

    async def answer(self, question: str, documents: list[Document]) -> AnswerResponse:
        await self.block("generating")
        return AnswerResponse(message="An answer", sources=[])

    async def search(self, question: str) -> AnswerResponse:
        await self.classify(question)
        documents = await self.retrieve(question)
        return await self.answer(question, documents)


@pytest.mark.parametrize("stage", ["classifying", "retrieving", "generating"])
def test_stream_deadline_cancels_active_stage_and_returns_error(
    stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = BlockingSearchService(stage)
    monkeypatch.setattr(settings, "search_timeout_seconds", 0.01)
    app.dependency_overrides[get_search_service] = lambda: service
    try:
        response = TestClient(app).post("/ask/stream", json={"question": "How does React work?"})
    finally:
        app.dependency_overrides.clear()

    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200
    assert events[-2]["stage"] == stage
    assert events[-1] == {"type": "error", "message": SEARCH_TIMEOUT_MESSAGE}
    assert all(event["type"] != "result" for event in events)
    assert service.cancelled


@pytest.mark.parametrize("endpoint", ["/ask", "/classify"])
def test_json_endpoints_return_gateway_timeout_and_cancel_work(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = BlockingSearchService("classifying")
    monkeypatch.setattr(settings, "search_timeout_seconds", 0.01)
    app.dependency_overrides[get_search_service] = lambda: service
    try:
        response = TestClient(app).post(endpoint, json={"question": "How does React work?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 504
    assert response.json() == {"detail": SEARCH_TIMEOUT_MESSAGE}
    assert service.cancelled


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
@pytest.mark.parametrize("stage", ["classifying", "generating"])
def test_client_disconnect_cancels_running_model_chain(spec_version: str, stage: str) -> None:
    async def run() -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def block(active_stage: str) -> None:
            if active_stage == stage:
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        async def classify(_: object) -> QuestionClassification:
            await block("classifying")
            return QuestionClassification(category="react")

        async def generate(_: object) -> GeneratedAnswer:
            await block("generating")
            return GeneratedAnswer(status="answered", message="An answer [1].", suggestions=[])

        model = Mock()
        model.with_structured_output.side_effect = [
            RunnableLambda(classify),
            RunnableLambda(generate),
        ]
        store = Mock()
        store.as_retriever.return_value.invoke.return_value = [Document(page_content="React docs")]
        service = ReactDocsSearchService(model, store)
        app.dependency_overrides[get_search_service] = lambda: service
        messages: list[Message] = []
        request_sent = False

        async def receive() -> Message:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {
                    "type": "http.request",
                    "body": json.dumps({"question": "How does React work?"}).encode(),
                    "more_body": False,
                }
            await started.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            messages.append(message)

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": spec_version},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/ask/stream",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        }
        try:
            with tracing_context(enabled=False):
                await asyncio.wait_for(app(scope, receive, send), timeout=1)
        finally:
            app.dependency_overrides.clear()

        assert cancelled.is_set()
        events = [
            json.loads(message["body"])
            for message in messages
            if message["type"] == "http.response.body" and message.get("body")
        ]
        assert events[-1]["stage"] == stage
        assert all(event["type"] == "status" for event in events)

    asyncio.run(run())


def test_broken_client_write_closes_stream_generator() -> None:
    async def run() -> None:
        closed = False

        async def events():
            nonlocal closed
            try:
                yield b"status\n"
            finally:
                closed = True

        async def receive() -> Message:
            await asyncio.Event().wait()
            raise AssertionError("The disconnect listener should be cancelled")

        async def send(message: Message) -> None:
            if message["type"] == "http.response.body":
                raise OSError("Client disconnected")

        response = CancellableStreamingResponse(events())
        with pytest.raises(ClientDisconnect):
            await response({"type": "http"}, receive, send)
        assert closed

    asyncio.run(run())
