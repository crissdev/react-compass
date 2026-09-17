from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1_000)


class GeneratedAnswer(BaseModel):
    message: str = Field(
        description=(
            "A grounded Markdown answer. Cite sources using only bare numeric markers such as "
            "[1] and [2], never labeled markers such as [SOURCE 1]."
        )
    )


class QuestionClassification(BaseModel):
    category: Literal["react", "unrelated", "prompt_injection"]


class SourceExcerpt(BaseModel):
    id: str
    citation: int = Field(ge=1)
    title: str
    section: str | None = None
    source_type: Literal["reference", "learn", "blog", "github", "unknown"] = "unknown"
    source_url: str
    excerpt: str


class AnswerResponse(BaseModel):
    kind: Literal["react_answer", "scope_notice"] = "react_answer"
    message: str
    sources: list[SourceExcerpt]


class QuestionGateResponse(BaseModel):
    category: Literal["react", "unrelated", "prompt_injection"]
    response: AnswerResponse | None = None


class StreamEvent(BaseModel):
    type: Literal["status", "result", "error"]
    stage: str | None = None
    message: str | None = None
    data: AnswerResponse | None = None
