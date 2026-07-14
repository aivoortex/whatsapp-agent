from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from app.agent import AgentService
from app.config import get_settings
from app.db import Repository
from app.knowledge import WebsiteImporter
from app.models import FeedbackCreate, KnowledgeSyncRequest, MessageRequest, MessageResponse, TenantCreate, TenantView
from app.niches import NicheRegistry
from app.security import UnsafeUrlError

settings = get_settings()
repository = Repository(settings.database_path)
niches = NicheRegistry()
agent = AgentService(settings)


@asynccontextmanager
async def lifespan(_):
    repository.initialize()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/v1/niches")
async def list_niches():
    return niches.all()


@app.post("/v1/tenants", response_model=TenantView)
async def create_tenant(payload: TenantCreate, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    if not niches.get(payload.niche):
        raise HTTPException(422, f"Pacote de nicho '{payload.niche}' não encontrado.")
    return repository.upsert_tenant(payload)


@app.get("/v1/tenants/{tenant_id}", response_model=TenantView)
async def get_tenant(tenant_id: str, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    return tenant_or_404(tenant_id)


@app.post("/v1/tenants/{tenant_id}/knowledge/sync")
async def sync_knowledge(tenant_id: str, payload: KnowledgeSyncRequest, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    tenant = tenant_or_404(tenant_id)
    start_url = str(payload.start_url or tenant.get("website_url") or "")
    if not start_url:
        raise HTTPException(422, "Informe uma URL no onboarding ou nesta solicitação.")
    try:
        documents = await WebsiteImporter(settings.request_timeout_seconds, settings.max_page_bytes).crawl(start_url, payload.max_pages or settings.max_crawl_pages)
    except UnsafeUrlError as exc:
        raise HTTPException(422, str(exc)) from exc
    repository.replace_documents(tenant_id, documents)
    repository.save_event(tenant_id, "knowledge_synced", payload={"documents": len(documents), "url": start_url})
    return {"tenant_id": tenant_id, "documents_imported": len(documents)}


@app.get("/v1/tenants/{tenant_id}/knowledge")
async def list_knowledge(tenant_id: str, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    tenant_or_404(tenant_id)
    return repository.list_documents(tenant_id)


@app.post("/v1/tenants/{tenant_id}/messages", response_model=MessageResponse)
async def process_message(tenant_id: str, payload: MessageRequest, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    tenant = tenant_or_404(tenant_id)
    cached = repository.get_processed(tenant_id, payload.message_id)
    if cached:
        return cached
    text = payload.text or " ".join(item.caption or f"[arquivo {item.type}]" for item in payload.attachments)
    if not text.strip():
        raise HTTPException(422, "Informe texto ou ao menos um anexo.")
    niche = niches.get(tenant["niche"])
    if not niche:
        raise HTTPException(500, "O pacote de nicho configurado não está disponível.")
    trace_id = uuid4().hex
    history = repository.recent_messages(tenant_id, payload.contact_id)
    contact = repository.get_contact(tenant_id, payload.contact_id)
    repository.save_message(tenant_id, payload.contact_id, "user", text)
    response = await agent.respond(tenant, niche, text, history, repository.list_documents(tenant_id), contact, trace_id)
    repository.save_message(tenant_id, payload.contact_id, "assistant", response.reply)
    repository.update_contact(tenant_id, payload.contact_id, response.captured_fields, response.intent, response.language)
    event_payload = {"intent": response.intent, "confidence": response.confidence, "handoff": response.handoff_required, "source_count": len(response.sources)}
    repository.save_event(tenant_id, "message_processed", contact_id=payload.contact_id, trace_id=trace_id, payload=event_payload)
    if response.handoff_required:
        repository.save_event(tenant_id, "handoff", contact_id=payload.contact_id, trace_id=trace_id, payload={"reason": response.reason})
    repository.save_processed(tenant_id, payload.message_id, response.model_dump(mode="json"))
    return response


@app.get("/v1/tenants/{tenant_id}/contacts/{contact_id}")
async def contact_context(tenant_id: str, contact_id: str, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    tenant_or_404(tenant_id)
    return {"contact_id": contact_id, **repository.get_contact(tenant_id, contact_id), "recent_messages": repository.recent_messages(tenant_id, contact_id, 30)}


@app.get("/v1/tenants/{tenant_id}/handoffs/{contact_id}")
async def handoff_context(tenant_id: str, contact_id: str, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    tenant_or_404(tenant_id)
    contact = repository.get_contact(tenant_id, contact_id)
    messages = repository.recent_messages(tenant_id, contact_id, 30)
    last_user_messages = [item["content"] for item in messages if item["role"] == "user"][-3:]
    return {
        "contact_id": contact_id,
        "summary": " | ".join(last_user_messages) or "Sem mensagens anteriores.",
        "profile": contact["profile"],
        "last_intent": contact.get("last_intent"),
        "language": contact.get("language"),
        "transcript": messages,
    }


@app.post("/v1/tenants/{tenant_id}/messages/{trace_id}/feedback", status_code=201)
async def create_feedback(tenant_id: str, trace_id: str, payload: FeedbackCreate, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    tenant_or_404(tenant_id)
    repository.save_feedback(tenant_id, trace_id, payload.rating, payload.resolved, payload.comment)
    return {"saved": True}


@app.get("/v1/tenants/{tenant_id}/analytics")
async def analytics(tenant_id: str, x_api_key: str | None = Header(default=None)):
    authorize(x_api_key)
    tenant_or_404(tenant_id)
    return repository.analytics(tenant_id)


def authorize(api_key: str | None) -> None:
    if settings.app_api_key and api_key != settings.app_api_key:
        raise HTTPException(401, "API key inválida.")


def tenant_or_404(tenant_id: str) -> dict:
    tenant = repository.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(404, "Cliente não encontrado.")
    return tenant
