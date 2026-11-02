import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from engram import __version__
from engram.api.pages import PdfPages
from engram.api.routes import (
    admin,
    chat,
    courses,
    dates,
    events,
    inspector,
    materials,
    me,
    review,
    sources,
)
from engram.config import get_settings
from engram.embeddings import get_embedder
from engram.storage import Storage

logger = logging.getLogger(__name__)

# Connections for concurrent requests; a few users need few.
POOL_SIZE = 5


class Health(BaseModel):
    status: str
    version: str


def _report_warm_up(task: "asyncio.Task[object]") -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        # Not fatal: the first question loads the model again, and fails there if it must.
        logger.warning("couldn't load the embedding model at startup: %s", exc)


def _log_to_stderr() -> None:
    """Uvicorn sets up only its own loggers; this makes the API's INFO lines (such as Ask's
    timings) reach the console and Cloud Run's logs too."""
    engram = logging.getLogger("engram")
    if not engram.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
        engram.addHandler(handler)
        engram.setLevel(logging.INFO)


def create_app() -> FastAPI:
    settings = get_settings()
    _log_to_stderr()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with (
            AsyncConnectionPool(
                settings.database_url, min_size=1, max_size=POOL_SIZE, open=False
            ) as pool,
            Storage(settings) as storage,
        ):
            app.state.pool = pool
            app.state.storage = storage
            app.state.pages = PdfPages(storage)
            # Loaded in the background, so it doesn't hold up startup but is usually ready
            # before the first question instead of being loaded by it.
            warm = asyncio.create_task(asyncio.to_thread(get_embedder, settings.embedding_model))
            warm.add_done_callback(_report_warm_up)
            yield
            await asyncio.gather(warm, return_exceptions=True)

    app = FastAPI(title="Engram API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> Health:
        return Health(status="ok", version=__version__)

    app.include_router(me.router)
    app.include_router(courses.router)
    app.include_router(dates.router)
    app.include_router(events.router)
    app.include_router(materials.router)
    app.include_router(review.router)
    app.include_router(chat.router)
    app.include_router(sources.router)
    app.include_router(admin.router)
    app.include_router(inspector.router)
    return app


app = create_app()
