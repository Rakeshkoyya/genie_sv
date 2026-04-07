"""API routers for Genie backend."""

from app.routers.health import router as health_router
from app.routers.users import router as users_router
from app.routers.sources import router as sources_router
from app.routers.datasets import router as datasets_router
from app.routers.prompts import router as prompts_router
from app.routers.prompt_folders import router as prompt_folders_router
from app.routers.formats import router as formats_router
from app.routers.prompt_chains import router as prompt_chains_router
from app.routers.generate import router as generate_router
from app.routers.generations import router as generations_router
from app.routers.exports import router as exports_router
from app.routers.infographics import router as infographics_router
from app.routers.workflows import router as workflows_router
from app.routers.docforge import router as docforge_router

__all__ = [
    "health_router",
    "users_router",
    "sources_router",
    "datasets_router",
    "prompts_router",
    "prompt_folders_router",
    "formats_router",
    "prompt_chains_router",
    "generate_router",
    "generations_router",
    "exports_router",
    "infographics_router",
    "workflows_router",
    "docforge_router",
]
