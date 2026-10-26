from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from engram import __version__
from engram.api.routes import admin, me
from engram.config import get_settings


class Health(BaseModel):
    status: str
    version: str


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncConnectionPool(settings.database_url, min_size=1, open=False) as pool:
            app.state.pool = pool
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
    app.include_router(admin.router)
    return app


app = create_app()
