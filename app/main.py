"""
Azure RAG Chatbot - FastAPI Application

Enterprise chatbot for confidential manuals with:
- Hybrid + vector retrieval via Azure AI Search
- Generation via Azure OpenAI
- Citations with manual name, page, and chunk ID
- No hallucinations policy
- Simple web frontend for chat interface
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.api.chat import router as chat_router

app = FastAPI(
    title="Azure RAG Chatbot",
    description="Enterprise RAG chatbot for confidential manuals",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_frontend():
        """Serve the frontend index.html."""
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/styles.css")
    async def serve_styles():
        """Serve the frontend styles."""
        return FileResponse(str(FRONTEND_DIR / "styles.css"), media_type="text/css")

    @app.get("/app.js")
    async def serve_js():
        """Serve the frontend JavaScript."""
        return FileResponse(str(FRONTEND_DIR / "app.js"), media_type="application/javascript")
