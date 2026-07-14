from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.agent import AgentService
from app.config import get_settings
from app.db import Repository
from app.knowledge import WebsiteImporter
from app.models import KnowledgeSyncRequest, MessageRequest, MessageResponse, TenantCreate, TenantView
from app.niches import NicheRegistry
from app.security import UnsafeUrlError

settings = get_settings(); repository = Repository(settings.database_path); niches = NicheRegistry(); agent = AgentService(settings)

@asynccontextmanager
async def lifespan(_):
    repository.initialize(); yield

app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

@app.get("/", include_in_schema=False)
async def home(): return FileResponse(Path(__file__).parent / "static" / "index.html")

@app.get("/health")
async def health(): return {"status": "ok"}

@app.get("/v1/niches")
async def list_niches(): return niches.all()

@app.post("/v1/tenants", response_model=TenantView)
async def create_tenant(payload: TenantCreate):
    if not niches.get(payload.niche): raise HTTPException(422, f"Pacote de nicho '{payload.niche}' não encontrado.")
    return repository.upsert_tenant(payload)

@app.get("/v1/tenants/{tenant_id}", response_model=TenantView)
async def get_tenant(tenant_id: str): return tenant_or_404(tenant_id)

@app.post("/v1/tenants/{tenant_id}/knowledge/sync")
async def sync_knowledge(tenant_id: str, payload: KnowledgeSyncRequest):
    tenant = tenant_or_404(tenant_id); start_url = str(payload.start_url or tenant.get("website_url") or "")
    if not start_url: raise HTTPException(422, "Informe uma URL no onboarding ou nesta solicitação.")
    try:
        docs = await WebsiteImporter(settings.request_timeout_seconds, settings.max_page_bytes).crawl(start_url, payload.max_pages or settings.max_crawl_pages)
    except UnsafeUrlError as exc: raise HTTPException(422, str(exc)) from exc
    repository.replace_documents(tenant_id, docs)
    return {"tenant_id": tenant_id, "documents_imported": len(docs)}

@app.get("/v1/tenants/{tenant_id}/knowledge")
async def list_knowledge(tenant_id: str): tenant_or_404(tenant_id); return repository.list_documents(tenant_id)

@app.post("/v1/tenants/{tenant_id}/messages", response_model=MessageResponse)
async def process_message(tenant_id: str, payload: MessageRequest):
    tenant = tenant_or_404(tenant_id); niche = niches.get(tenant["niche"])
    history = repository.recent_messages(tenant_id, payload.contact_id)
    repository.save_message(tenant_id, payload.contact_id, "user", payload.text)
    response = await agent.respond(tenant, niche, payload.text, history, repository.list_documents(tenant_id))
    repository.save_message(tenant_id, payload.contact_id, "assistant", response.reply)
    return response

def tenant_or_404(tenant_id):
    tenant = repository.get_tenant(tenant_id)
    if not tenant: raise HTTPException(404, "Cliente não encontrado.")
    return tenant
