"""
Banking Agentic AI System — main entry point.

Start:
    uvicorn main:app --reload --port 8000

This is the ONLY file that knows about FastAPI.
Everything else is pure Python.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import router
from api.middleware.edge_layer import EdgeLayerMiddleware
from api.middleware.edge_layer import TimeoutMiddleware
from db.connection import db


# ── Lifecycle: connect/disconnect DB pool ─────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create DB pool. Shutdown: close it."""
    await db.connect()
    yield
    await db.disconnect()


# ── Create app ────────────────────────────────────────

app = FastAPI(
    title="Banking Agentic AI System",
    description=(
        "Multi-agent banking assistant with PostgreSQL, "
        "MCP tools, and AWS Bedrock."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── Edge layer (WAF, security headers) ────────────────
app.add_middleware(EdgeLayerMiddleware)
app.add_middleware(TimeoutMiddleware)

# ── API routes ────────────────────────────────────────
app.include_router(router, prefix="/api")



app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")

