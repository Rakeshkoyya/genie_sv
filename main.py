"""FastAPI application entry point for Genie backend."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.routers import (
    health_router,
    users_router,
    sources_router,
    datasets_router,
    prompts_router,
    prompt_folders_router,
    formats_router,
    prompt_chains_router,
    generate_router,
    generations_router,
    exports_router,
    infographics_router,
    workflows_router,
    docforge_router,
    wiki_router,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print("Starting Genie backend...")
    yield
    # Shutdown
    print("Shutting down Genie backend...")
    await engine.dispose()


app = FastAPI(
    title="Genie Backend API",
    description="Backend API for Genie document generation platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(users_router)
app.include_router(sources_router)
app.include_router(datasets_router)
app.include_router(prompts_router)
app.include_router(prompt_folders_router)
app.include_router(formats_router)
app.include_router(prompt_chains_router)
app.include_router(generate_router)
app.include_router(generations_router)
app.include_router(exports_router)
app.include_router(infographics_router)
app.include_router(workflows_router)
app.include_router(docforge_router)
app.include_router(wiki_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Genie Backend API",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
