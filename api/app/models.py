from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1_000)


class GeneratedAnswer(BaseModel):
    message: str = Field(
        description="A grounded Markdown answer. Use [1], [2], and so on for source citations."
    )


class SourceExcerpt(BaseModel):
    id: str
    citation: int = Field(ge=1)
    title: str
    section: str | None = None
    source_type: Literal["reference", "learn", "blog", "github", "unknown"] = "unknown"
    source_url: str
    excerpt: str


class AnswerResponse(BaseModel):
    message: str
    sources: list[SourceExcerpt]


class StreamEvent(BaseModel):
    type: Literal["status", "result", "error"]
    stage: str | None = None
    message: str | None = None
    data: AnswerResponse | None = None
