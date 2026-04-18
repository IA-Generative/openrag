"""MyRAG (beta) — Front augmente DSFR pour OpenRAG."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import ingest, collections, sync, graph, articles

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_title,
        "version": settings.app_version,
    }


@app.get("/")
async def root():
    return JSONResponse(
        content={
            "app": settings.app_title,
            "version": settings.app_version,
            "docs": "/docs",
        }
    )


app.include_router(ingest.router)
app.include_router(collections.router)
app.include_router(sync.router)
app.include_router(graph.router)
app.include_router(articles.router)


@app.get("/api/config")
async def get_config():
    return {
        "app_title": settings.app_title,
        "openrag_url": settings.openrag_url,
        "graphrag_viewer_url": settings.graphrag_viewer_url,
        "myrag_public_url": settings.myrag_public_url,
    }
