"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.database import engine
from app.routes.api import router as api_router
from app.routes.web import limiter, router as web_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(funcName)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Path(settings.workdir_path).mkdir(parents=True, exist_ok=True)
    logger.info("Workdir: %s", settings.workdir_path)
    yield
    # Shutdown
    await engine.dispose()
    logger.info("DB engine disposed")


app = FastAPI(
    title="Súmula Curricular FAPESP",
    description="Construtor de Súmula Curricular FAPESP a partir de múltiplas fontes",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Routers
app.include_router(web_router)
app.include_router(api_router)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": "Recurso não encontrado"})


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.error("Internal server error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor"})
