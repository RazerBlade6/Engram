"""The worker on Modal (D35), scaling to zero between jobs.

A new job wakes it: the database posts to `wake` (migration `wake_worker`), which starts
`drain`. A sweep every 15 minutes catches retries whose backoff has passed and jobs left by a
worker that died. Only one `drain` runs at a time, so a job running longer than the queue's
stale-lock time is never claimed twice.

Deploy from backend/ with `uv run --with modal modal deploy modal_app.py`. Settings come
from the Modal secret `engram`; see docs/DEPLOY.md.
"""

import hmac
import os
import socket
from pathlib import Path

import modal

HERE = Path(__file__).parent

image = (
    modal.Image.debian_slim(python_version="3.13")
    .env(
        {
            "UV_COMPILE_BYTECODE": "1",
            "HF_HOME": "/models/huggingface",
            "FASTEMBED_CACHE_PATH": "/models/fastembed",
        }
    )
    .uv_sync(str(HERE), extras=["ingest"])
    .add_local_python_source("engram")
)

# Docling's layout models and the embedding model, downloaded on first use and kept.
models = modal.Volume.from_name("engram-models", create_if_missing=True)
secret = modal.Secret.from_name("engram")

# Only the image has the backend's dependencies; these imports run in the container.
with image.imports():
    from fastapi import HTTPException, Request

app = modal.App("engram-worker", image=image, secrets=[secret])


@app.function(
    volumes={"/models": models},
    cpu=4,
    memory=8192,
    timeout=3 * 60 * 60,
    max_containers=1,
)
async def drain() -> int:
    from engram.config import get_settings
    from engram.worker.main import drain

    return await drain(get_settings(), f"modal:{socket.gethostname()}")


async def _ready() -> bool:
    from psycopg import AsyncConnection

    from engram.config import get_settings
    from engram.worker import queue

    async with await AsyncConnection.connect(get_settings().database_url) as conn:
        return await queue.has_ready(conn)


@app.function(schedule=modal.Period(minutes=15), cpu=0.25, memory=512)
async def sweep() -> None:
    if await _ready():
        await drain.spawn.aio()


@app.function(cpu=0.25, memory=512)
@modal.fastapi_endpoint(method="POST")
async def wake(request: Request) -> dict[str, bool]:
    expected = f"Bearer {os.environ['ENGRAM_WORKER_WAKE_TOKEN']}"
    if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
        raise HTTPException(status_code=401)
    await drain.spawn.aio()
    return {"woken": True}
