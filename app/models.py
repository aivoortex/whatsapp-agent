from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class BusinessHours(BaseModel):
    timezone: str = "America/Sao_Paulo"
    schedule: dict[str, str] = Field(default_factory=dict)


class LeadField(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    label: str = Field(min_length=2, max_length=80)
    question: str = Field(min_length=5, max_length=240)
    required: bool = True


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
    confidence_threshold: float = Field(default=0.18, ge=0, le=1)
    lead_qualification_fields: list[LeadField] = Field(default_factory=list, max_length=12)
    default_language: str = Field(default="pt-BR", max_length=12)
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


class MediaAttachment(BaseModel):
    type: Literal["image", "audio", "document", "video"]
    url: HttpUrl | None = None
    mime_type: str | None = Field(default=None, max_length=100)
    caption: str | None = Field(default=None, max_length=1000)


class MessageRequest(BaseModel):
    text: str = Field(default="", max_length=4000)
    contact_id: str = Field(min_length=3, max_length=120)
    conversation_id: str | None = Field(default=None, max_length=120)
    message_id: str | None = Field(default=None, max_length=160)
    locale: str | None = Field(default=None, max_length=12)
    attachments: list[MediaAttachment] = Field(default_factory=list, max_length=5)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def require_content(cls, value: str) -> str:
        return value.strip()


class Source(BaseModel):
    title: str
    url: str
    score: float
    excerpt: str | None = None


class SuggestedAction(BaseModel):
    type: Literal["handoff", "qualify_lead", "book_appointment", "lookup_order", "update_crm"]
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True


class MessageResponse(BaseModel):
    reply: str
    sources: list[Source] = Field(default_factory=list)
    handoff_required: bool = False
    reason: str | None = None
    intent: str = "general"
    confidence: float = 0
    language: str = "pt-BR"
    captured_fields: dict[str, str] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    trace_id: str


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    resolved: bool | None = None
    comment: str = Field(default="", max_length=1000)
