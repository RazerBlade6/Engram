from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engram import __version__
from engram.config import get_settings


class Health(BaseModel):
    status: str
    version: str


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Engram API", version=__version__)
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

    return app


app = create_app()
