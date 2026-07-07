from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=80)
    history: list[ChatMessage] = Field(default_factory=list, max_length=50)
    conversation_summary: str | None = Field(default=None, max_length=4000)
    user_message_count: int = Field(default=0, ge=0, le=500)
    website: str | None = Field(default=None, max_length=200, description="Honeypot — must be empty")

    @model_validator(mode="after")
    def reject_honeypot(self) -> "ChatRequest":
        if self.website and self.website.strip():
            raise ValueError("Invalid request")
        return self


class ReadMoreLink(BaseModel):
    url: str
    title: str


class MediaItem(BaseModel):
    url: str
    alt: str | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[dict] = Field(default_factory=list)
    read_more: ReadMoreLink | None = None
    media: MediaItem | None = None
    suggest_lead_form: bool = False
    show_lead_cta: bool = False
    uncertain: bool = False
    conversation_summary: str | None = None


class LeadRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr
    topic: str | None = Field(default=None, max_length=200)
    message: str = Field(..., min_length=1, max_length=5000)
    session_id: str | None = Field(default=None, max_length=80)
    source_url: str | None = Field(default=None, max_length=500)
    conversation: list[ChatMessage] = Field(default_factory=list, max_length=100)
    website: str | None = Field(default=None, max_length=200, description="Honeypot — must be empty")

    @model_validator(mode="after")
    def reject_honeypot(self) -> "LeadRequest":
        if self.website and self.website.strip():
            raise ValueError("Invalid request")
        return self

    @field_validator("conversation")
    @classmethod
    def cap_conversation(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        return v[:100]


class LeadResponse(BaseModel):
    ok: bool = True
    lead_id: str
    chat_summary: str = ""


class LeadRecord(BaseModel):
    id: str
    session_id: str | None = None
    name: str
    company: str | None = None
    phone: str | None = None
    email: str
    topic: str | None = None
    message: str
    source_url: str | None = None
    chat_summary: str | None = None
    conversation: list[ChatMessage] = Field(default_factory=list)
    created_at: str | None = None
    status: Literal["new", "emailed", "finished"] = "new"


class LeadStatusUpdate(BaseModel):
    status: Literal["new", "emailed", "finished"]


class ReindexResponse(BaseModel):
    ok: bool
    pages_crawled: int
    chunks_stored: int
    message: str
