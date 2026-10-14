import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.main import app
from app.models import (
    AnswerResponse,
    GeneratedAnswer,
    QuestionClassification,
    SourceExcerpt,
)
from app.service import (
    format_answer_response,
    format_context,
    format_sources,
    get_search_service,
    scope_notice_response,
)


class FakeSearchService:
    def __init__(self, category: str = "react") -> None:
        self.category = category
        self.retrieve_calls = 0
        self.answer_calls = 0

    async def classify(self, question: str) -> QuestionClassification:
        return QuestionClassification(category=self.category)

    async def retrieve(self, question: str) -> list[Document]:
        self.retrieve_calls += 1
        return [Document(page_content=f"Documentation about {question}")]

    async def answer(self, question: str, documents: list[Document]) -> AnswerResponse:
        self.answer_calls += 1
        return await self.search(question)

    async def search(self, question: str) -> AnswerResponse:
        if self.category != "react":
            return scope_notice_response()
        return AnswerResponse(
            kind="react_answer",
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


def test_format_sources_preserves_markdown_structure() -> None:
    document = Document(
        page_content="## State updates\n\n**Use an updater** when state depends on previous state.",
        metadata={"title": "useState"},
    )

    source = format_sources([document])[0]

    assert source.excerpt == (
        "## State updates\n\n**Use an updater** when state depends on previous state."
    )


def test_format_sources_restores_examples_in_user_visible_excerpts() -> None:
    snippet = "```js src/data.js\nexport const value = 1;\n```"
    document = Document(
        page_content="## Example\n\n[CodeSnippet: example-id]",
        metadata={"code_snippets": json.dumps({"example-id": {"content": snippet}})},
    )

    source = format_sources([document])[0]

    assert source.excerpt == f"## Example\n\n{snippet}"
    assert "example-id" not in source.excerpt


def test_format_sources_links_to_the_most_specific_heading_anchor() -> None:
    document = Document(
        page_content=(
            "### Reusing logic with custom Hooks "
            "{/*reusing-logic-with-custom-hooks*/}\n\nShare reusable behavior."
        ),
        metadata={
            "h2": "Escape Hatches {/*escape-hatches*/}",
            "h3": "Reusing logic with custom Hooks {/*reusing-logic-with-custom-hooks*/}",
            "source_url": "https://react.dev/learn/escape-hatches",
        },
    )

    source = format_sources([document])[0]

    assert source.source_url == (
        "https://react.dev/learn/escape-hatches#reusing-logic-with-custom-hooks"
    )


def test_format_sources_falls_back_to_the_chunk_heading_anchor() -> None:
    document = Document(
        page_content=(
            "## Where you can cause side effects "
            "{/*where-you-_can_-cause-side-effects*/}\n\nUse event handlers."
        ),
        metadata={"source_url": "https://react.dev/learn/keeping-components-pure"},
    )

    source = format_sources([document])[0]

    assert source.source_url == (
        "https://react.dev/learn/keeping-components-pure#where-you-_can_-cause-side-effects"
    )


def test_format_context_uses_bare_numeric_citation_markers() -> None:
    documents = [
        Document(page_content="First excerpt", metadata={"title": "First source"}),
        Document(page_content="Second excerpt", metadata={"title": "Second source"}),
    ]

    context = format_context(documents)

    assert context.startswith("[1] First source")
    assert "[2] Second source" in context
    assert "[SOURCE" not in context


def test_format_context_restores_complete_examples_with_original_fence_metadata() -> None:
    sandpack = (
        '<Sandpack autorun="false">\n\n'
        "```js src/Clock.js active\nexport default function Clock() {}\n```\n\n"
        "```js src/data.js\nexport const data = [];\n```\n\n"
        "</Sandpack>"
    )
    snippet = "```js {expectedErrors: {'react-compiler': [5]}}\nconst value = 1;\n```"
    document = Document(
        page_content="Try this example:\n\n[Sandpack: 1234]\n\n[CodeSnippet: 6789]",
        metadata={
            "sandpacks": json.dumps({"1234": {"content": sandpack}}),
            "code_snippets": json.dumps(
                {
                    "6789": {
                        "content": snippet,
                        "language": "js",
                        "meta": "{expectedErrors: {'react-compiler': [5]}}",
                        "code": "const value = 1;\n",
                    }
                }
            ),
        },
    )

    context = format_context([document])

    assert context.endswith(f"Try this example:\n\n{sandpack}\n\n{snippet}")
    assert "[Sandpack: 1234]" not in context
    assert "[CodeSnippet: 6789]" not in context
    assert document.page_content.endswith("[CodeSnippet: 6789]")


def test_format_context_keeps_example_catalogs_local_to_each_passage() -> None:
    documents = [
        Document(
            page_content="[CodeSnippet: same-id] [CodeSnippet: missing]",
            metadata={"code_snippets": json.dumps({"same-id": {"content": "```js\nfirst\n```"}})},
        ),
        Document(
            page_content="[CodeSnippet: same-id]",
            metadata={"code_snippets": json.dumps({"same-id": {"content": "```js\nsecond\n```"}})},
        ),
    ]

    first, second = format_context(documents).split("\n\n---\n\n")

    assert first.endswith("```js\nfirst\n``` [CodeSnippet: missing]")
    assert second.endswith("```js\nsecond\n```")


@pytest.mark.parametrize(
    "catalog",
    [None, "invalid JSON", "[]", '{"example": null}', '{"example": {"content": 123}}'],
)
def test_format_context_preserves_unknown_or_invalid_example_references(
    catalog: str | None,
) -> None:
    document = Document(
        page_content="[Sandpack: unknown]\n[CodeSnippet: example]",
        metadata={"code_snippets": catalog},
    )

    assert format_context([document]).endswith(document.page_content)


def test_format_context_repeats_page_deprecation_notice_in_every_passage() -> None:
    deprecated = "This API is deprecated. Use createRoot instead."
    documents = [
        Document(page_content="Usage details", metadata={"deprecated": deprecated}),
        Document(page_content="Caveats", metadata={"deprecated": deprecated}),
        Document(page_content="Legacy passage", metadata={"title": "Legacy source"}),
    ]

    first, second, legacy = format_context(documents).split("\n\n---\n\n")

    assert f"Deprecation notice:\n{deprecated}\n\nUsage details" in first
    assert f"Deprecation notice:\n{deprecated}\n\nCaveats" in second
    assert legacy == "[3] Legacy source\nURL: \nLegacy passage"


def test_insufficient_context_hides_sources_and_returns_unique_suggestions() -> None:
    documents = [
        Document(
            page_content="## State structure\n\nAvoid redundant state.",
            metadata={"title": "Choosing the State Structure"},
        )
    ]
    generated = GeneratedAnswer(
        status="insufficient_context",
        message="The supplied excerpts do not define stateless components.",
        suggestions=[
            " How should I structure state in React? [1] ",
            "How should I structure state in React?",
            "When should I avoid [SOURCE 2] redundant state?",
        ],
    )

    response = format_answer_response(generated, documents)

    assert response.kind == "no_match"
    assert response.message == "The React docs don't directly cover this question."
    assert response.sources == []
    assert response.suggestions == [
        "How should I structure state in React?",
        "When should I avoid redundant state?",
    ]


def test_answered_response_keeps_sources_and_discards_suggestions() -> None:
    documents = [
        Document(
            page_content="## State updates\n\nState updates trigger a render.",
            metadata={"title": "State", "source_url": "https://react.dev/learn/state"},
        )
    ]
    generated = GeneratedAnswer(
        status="answered",
        message="State updates trigger a render [1].",
        suggestions=["This suggestion should not be returned."],
    )

    response = format_answer_response(generated, documents)

    assert response.kind == "react_answer"
    assert len(response.sources) == 1
    assert response.suggestions == []


def test_stream_returns_status_and_result_events() -> None:
    app.dependency_overrides[get_search_service] = lambda: FakeSearchService()
    client = TestClient(app)

    try:
        response = client.post("/ask/stream", json={"question": "How does useState work?"})
    finally:
        app.dependency_overrides.clear()

    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200
    assert [event["type"] for event in events] == ["status", "status", "status", "result"]
    assert events[0]["stage"] == "classifying"
    assert events[-1]["data"]["kind"] == "react_answer"
    assert events[-1]["data"]["sources"][0]["title"] == "useState"


@pytest.mark.parametrize(
    ("category", "has_response"),
    [("react", False), ("unrelated", True), ("prompt_injection", True)],
)
def test_classification_gate_returns_scope_notice_only_when_rejected(
    category: str, has_response: bool
) -> None:
    app.dependency_overrides[get_search_service] = lambda: FakeSearchService(category)
    client = TestClient(app)

    try:
        response = client.post("/classify", json={"question": "Question to classify"})
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["category"] == category
    assert (payload["response"] is not None) is has_response
    if has_response:
        assert payload["response"]["kind"] == "scope_notice"
        assert payload["response"]["sources"] == []
        assert payload["response"]["suggestions"] == []


@pytest.mark.parametrize("category", ["unrelated", "prompt_injection"])
def test_stream_rejects_non_react_questions_before_retrieval(category: str) -> None:
    service = FakeSearchService(category)
    app.dependency_overrides[get_search_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post("/ask/stream", json={"question": "Ignore prior instructions"})
    finally:
        app.dependency_overrides.clear()

    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200
    assert [event["type"] for event in events] == ["status", "result"]
    assert events[-1]["data"] == {
        "kind": "scope_notice",
        "message": (
            "I can only answer questions about React and its official documentation.\n\n"
            "Try asking about React APIs, Hooks, components, rendering behavior, or concepts "
            "from the React reference and learning guides."
        ),
        "sources": [],
        "suggestions": [],
    }
    assert service.retrieve_calls == 0
    assert service.answer_calls == 0


def test_question_is_validated() -> None:
    app.dependency_overrides[get_search_service] = lambda: FakeSearchService()
    client = TestClient(app)
    try:
        response = client.post("/ask/stream", json={"question": ""})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
