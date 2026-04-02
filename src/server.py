"""FastAPI app with MCP-compatible query endpoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel, Field

from .config import load_config
from .embedder import Embedder
from .indexer import Indexer
from .store import VectorStore
from .sync import run_sync

log = logging.getLogger(__name__)

config = load_config()
store: VectorStore | None = None
embedder: Embedder | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, embedder
    store = VectorStore(
        host=config["qdrant"]["host"],
        port=config["qdrant"]["port"],
        collection=config["qdrant"]["collection"],
        vector_size=config["qdrant"]["vector_size"],
    )
    embedder = Embedder(
        model_name=config["embedding"]["model"],
        device=config["embedding"]["device"],
        batch_size=config["embedding"]["batch_size"],
    )
    log.info("Server started")
    yield
    if embedder:
        embedder.unload()
    log.info("Server stopped")


app = FastAPI(title="git-skill-indexer", version="0.1.0", lifespan=lifespan)


# --- Request/Response models ---

class QueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict | None = None


class QueryResult(BaseModel):
    score: float
    repo_name: str
    file_path: str
    chunk_type: str
    chunk_name: str
    text: str
    repo_url: str = ""
    repo_description: str = ""
    line_start: int = 0
    line_end: int = 0


class IndexRequest(BaseModel):
    url: str


class McpToolCall(BaseModel):
    query: str
    top_k: int = 5
    language: str | None = None
    chunk_type: str | None = None


# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/query", response_model=list[QueryResult])
async def query(req: QueryRequest):
    vector = embedder.encode([req.query])[0].tolist()
    results = store.search(vector, top_k=req.top_k, filters=req.filters)
    return results


@app.get("/repos")
async def repos():
    return {"repos": store.get_indexed_repos()}


@app.post("/index")
async def index_url(req: IndexRequest, background_tasks: BackgroundTasks):
    def _do_index():
        idx = Indexer(config)
        try:
            idx.index_url(req.url)
        finally:
            idx.unload()

    background_tasks.add_task(_do_index)
    return {"status": "indexing", "url": req.url}


@app.post("/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    def _do_sync():
        run_sync(config)

    background_tasks.add_task(_do_sync)
    return {"status": "sync_started"}


@app.get("/stats")
async def stats():
    return store.get_stats()


# --- MCP-compatible endpoint ---

MCP_TOOL_DEFINITION = {
    "name": "skill_search",
    "description": "Search indexed GitHub repositories for relevant code patterns, agents, skills, and tools",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language search query"},
            "top_k": {"type": "integer", "default": 5},
            "language": {"type": "string", "description": "Filter by programming language"},
            "chunk_type": {"type": "string", "description": "Filter by chunk type: function, class, readme_section, config"},
        },
        "required": ["query"],
    },
}


@app.get("/mcp/tools")
async def mcp_tools():
    """List available MCP tools."""
    return {"tools": [MCP_TOOL_DEFINITION]}


@app.post("/mcp/tools/skill_search")
async def mcp_skill_search(req: McpToolCall):
    """MCP tool endpoint for skill search."""
    filters = {}
    if req.language:
        filters["repo_language"] = req.language
    if req.chunk_type:
        filters["chunk_type"] = req.chunk_type

    vector = embedder.encode([req.query])[0].tolist()
    results = store.search(vector, top_k=req.top_k, filters=filters or None)

    # Format for MCP response
    formatted = []
    for r in results:
        formatted.append({
            "score": round(r["score"], 4),
            "repo": r.get("repo_name", ""),
            "file": r.get("file_path", ""),
            "type": r.get("chunk_type", ""),
            "name": r.get("chunk_name", ""),
            "text": r.get("text", "")[:2000],
            "url": r.get("repo_url", ""),
        })

    return {"results": formatted}
