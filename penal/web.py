import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from penal.config import ROOT, settings
from penal.llm import is_configured
from penal.mcp_client import call_tool, connect_mcp
from penal.orchestrator import answer_question
from penal.schemas import ChatRequest, ChatResponse

app = FastAPI(title="Biblioteca Penal · RAG + MCP", version="1.0.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
chat_lock = asyncio.Lock()


@app.middleware("http")
async def local_origin(request: Request, call_next):
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        origin = request.headers.get("origin")
        if origin and origin not in {f"http://{request.headers.get('host')}"}:
            return JSONResponse({"detail": "Origem não permitida."}, status_code=403)
        if int(request.headers.get("content-length", 0)) > 16_384:
            return JSONResponse({"detail": "Mensagem muito grande."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    return response


@app.get("/")
async def home():
    return FileResponse(ROOT / "static/index.html")


@app.get("/api/status")
async def status():
    path = ROOT / "data/processed/index.json"
    index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"indexed": bool(index), "llm_configured": is_configured(), "llm_model": settings().llm_model,
            "embedding_model": settings().embedding_model, "documents": index.get("documents", []),
            "chunks": index.get("chunk_count", 0), "chunk_size": settings().chunk_size,
            "chunk_overlap": settings().chunk_overlap, "top_k": settings().top_k,
            "min_similarity": settings().min_similarity}


@app.get("/api/topics")
async def topics():
    if not (ROOT / "data/processed/index.json").exists():
        raise HTTPException(409, "Execute a indexação antes de consultar os tópicos.")
    async with connect_mcp() as session:
        return await call_tool(session, "list_topics", {})


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if not (ROOT / "data/processed/index.json").exists():
        raise HTTPException(409, "Base ainda não indexada. Execute python -m penal.ingest.")
    if chat_lock.locked():
        raise HTTPException(429, "Há uma consulta em andamento. Aguarde a resposta e tente novamente.")
    async with chat_lock:
        try:
            response = await answer_question(payload)
        except Exception:
            logging.getLogger(__name__).exception("Falha na integração MCP")
            raise HTTPException(503, "Não foi possível consultar o servidor MCP. Confira o terminal do backend.") from None
    # Não registra pergunta, texto jurídico ou credencial: só hash, resultado e execução.
    log = {"timestamp": datetime.now(timezone.utc).isoformat(), "question_sha256": hashlib.sha256(payload.message.encode()).hexdigest(),
           "status": response.status, "tools": [t.model_dump(exclude={"arguments"}) for t in response.tools],
           "guardrails": response.guardrails, "elapsed_ms": response.elapsed_ms}
    (ROOT / "logs").mkdir(exist_ok=True)
    with (ROOT / "logs/queries.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(log, ensure_ascii=False) + "\n")
    return response


@app.get("/api/documents/{document_id}")
async def document(document_id: str, page: int = 1):
    async with connect_mcp() as session:
        try:
            return await call_tool(session, "get_document", {"document_id": document_id, "page": page})
        except ValueError:
            raise HTTPException(404, "Documento ou página não disponível.") from None


@app.get("/documents/{document_id}/pdf")
async def pdf(document_id: str):
    index_path = ROOT / "data/processed/index.json"
    if not index_path.exists():
        raise HTTPException(404, "Base não indexada.")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    doc = next((d for d in index["documents"] if d["document_id"] == document_id), None)
    if doc is None:
        raise HTTPException(404, "Documento não disponível.")
    return FileResponse(ROOT / "data/raw" / doc["filename"], media_type="application/pdf")
