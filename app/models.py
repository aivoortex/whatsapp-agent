from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


class BusinessHours(BaseModel):
    timezone: str = "America/Sao_Paulo"
    schedule: dict[str, str] = Field(default_factory=dict)


class TenantCreate(BaseModel):
    tenant_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,49}$")
    business_name: str = Field(min_length=2, max_length=120)
    niche: str = "general"
    website_url: HttpUrl | None = None
    assistant_name: str = Field(default="Assistente", max_length=60)
    tone: str = Field(default="profissional, claro e cordial", max_length=200)
    objective: str = Field(min_length=5, max_length=500)
    human_handoff_contact: str | None = Field(default=None, max_length=200)
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    forbidden_topics: list[str] = Field(default_factory=list, max_length=30)
    custom_instructions: str = Field(default="", max_length=3000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("forbidden_topics")
    @classmethod
    def trim_topics(cls, topics: list[str]) -> list[str]:
        return [topic.strip()[:100] for topic in topics if topic.strip()]


class TenantView(TenantCreate):
    created_at: str
    updated_at: str


class KnowledgeSyncRequest(BaseModel):
    start_url: HttpUrl | None = None
    max_pages: int | None = Field(default=None, ge=1, le=100)


class KnowledgeDocument(BaseModel):
    url: str
    title: str
    text: str
    fetched_at: str


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    contact_id: str = Field(min_length=3, max_length=120)
    conversation_id: str | None = Field(default=None, max_length=120)


class Source(BaseModel):
    title: str
    url: str
    score: float


class MessageResponse(BaseModel):
    reply: str
    sources: list[Source] = Field(default_factory=list)
    handoff_required: bool = False
    reason: str | None = None
