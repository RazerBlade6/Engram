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
    inspector,
    materials,
    me,
    review,
    sources,
)
from engram.config import get_settings
from engram.storage import Storage

# Connections for concurrent requests; a few users need few.
POOL_SIZE = 5


class Health(BaseModel):
    status: str
    version: str


def create_app() -> FastAPI:
    settings = get_settings()

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
            yield

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
    app.include_router(materials.router)
    app.include_router(review.router)
    app.include_router(chat.router)
    app.include_router(sources.router)
    app.include_router(admin.router)
    app.include_router(inspector.router)
    return app


app = create_app()
