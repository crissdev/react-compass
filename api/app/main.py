import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langsmith import traceable

from app.config import get_settings
from app.models import AnswerResponse, AskRequest, QuestionGateResponse, StreamEvent
from app.service import ReactDocsSearchService, get_search_service, scope_notice_response

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="React Compass API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def encode_event(event: StreamEvent) -> bytes:
    return (event.model_dump_json(exclude_none=True) + "\n").encode()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AnswerResponse)
async def ask(
    request: AskRequest,
    service: Annotated[ReactDocsSearchService, Depends(get_search_service)],
) -> AnswerResponse:
    return await service.search(request.question)


@app.post("/classify", response_model=QuestionGateResponse)
async def classify_question(
    request: AskRequest,
    service: Annotated[ReactDocsSearchService, Depends(get_search_service)],
) -> QuestionGateResponse:
    classification = await service.classify(request.question)
    response = None if classification.category == "react" else scope_notice_response()
    return QuestionGateResponse(category=classification.category, response=response)


@app.post("/ask/stream")
async def ask_stream(
    request: AskRequest,
    service: Annotated[ReactDocsSearchService, Depends(get_search_service)],
) -> StreamingResponse:
    @traceable(name="react_docs_search", run_type="chain")
    async def events() -> AsyncIterator[bytes]:
        try:
            yield encode_event(
                StreamEvent(
                    type="status",
                    stage="classifying",
                    message="Checking question scope and safety",
                )
            )
            classification = await service.classify(request.question)
            if classification.category != "react":
                yield encode_event(StreamEvent(type="result", data=scope_notice_response()))
                return

            yield encode_event(
                StreamEvent(type="status", stage="retrieving", message="Searching React docs")
            )
            documents = await service.retrieve(request.question)
            yield encode_event(
                StreamEvent(type="status", stage="generating", message="Writing a grounded answer")
            )
            await asyncio.sleep(0)
            result = await service.answer(request.question, documents)
            yield encode_event(StreamEvent(type="result", data=result))
        except asyncio.CancelledError:
            logger.info("Search cancelled by the client")
            raise
        except Exception:
            logger.exception("React documentation search failed")
            yield encode_event(
                StreamEvent(
                    type="error",
                    message=(
                        "The search could not be completed. "
                        "Check the API configuration and try again."
                    ),
                )
            )

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )
