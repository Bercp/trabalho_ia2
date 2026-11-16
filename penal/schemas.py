from typing import Literal

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    filename: str
    page: int
    topic_key: str
    edition: str
    source_url: str = ""
    text: str
    similarity: float = 0
    retrieval_method: Literal["hybrid", "article_match"] = "hybrid"


class SearchResult(BaseModel):
    query: str
    chunks: list[Chunk] = Field(default_factory=list)
    sufficient: bool = False
    threshold: float = 0


class DocumentResult(BaseModel):
    document_id: str
    title: str
    filename: str
    edition: str
    source_url: str
    total_pages: int
    page: int
    text: str


class Topic(BaseModel):
    topic_key: str
    title: str
    documents: int
    chunks: int


class TopicsResult(BaseModel):
    topics: list[Topic]
    document_count: int
    chunk_count: int


class Citation(BaseModel):
    chunk_id: str
    quote: str = Field(min_length=25, max_length=1800)


class Claim(BaseModel):
    text: str = Field(min_length=10, max_length=1200)
    evidence: list[Citation] = Field(min_length=1, max_length=3)


class GroundedAnswer(BaseModel):
    sufficient: bool
    claims: list[Claim] = Field(default_factory=list, max_length=5)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    topic_key: str | None = Field(default=None, max_length=80)
    mode: Literal["chat", "search"] = "chat"


class ToolEvent(BaseModel):
    name: str
    arguments: dict
    ok: bool
    chunks: int = 0
    initiated_by: Literal["backend", "llm"] = "backend"


class ChatResponse(BaseModel):
    status: str
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    sources: list[Chunk] = Field(default_factory=list)
    tools: list[ToolEvent] = Field(default_factory=list)
    guardrails: dict = Field(default_factory=dict)
    elapsed_ms: int = 0
