"""The worker on Modal (D35), scaling to zero between jobs.

A new job wakes it: the database posts to `wake` (migration `wake_worker`), which starts
`drain_ingest` or `drain_cards`, whichever has jobs ready (D92). A sweep every 15 minutes
emails any new alerts (`engram.alerts`), and catches retries whose backoff has passed and
jobs left by a worker that died or was preempted: a running job's lock is renewed every
minute, so one unrenewed for five is abandoned. Only one of each drain runs at a time.

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


# Reading materials and making cards run in separate functions, each one container at a
# time, so cards are made while a textbook is read (D92). Each job has its own time limit
# (engram.worker.main.TIME_LIMITS); a drain stops claiming jobs whose limit no longer fits in
# its own, and is started again by the next wake or sweep.
INGEST_TIMEOUT = 3 * 60 * 60
CARDS_TIMEOUT = 2 * 60 * 60
# Left at the end of a drain for finishing up.
MARGIN = 5 * 60


async def _drain(worker: str, seconds: int) -> int:
    from datetime import timedelta

    from engram.config import get_settings
    from engram.worker.main import WORKERS, drain

    return await drain(
        get_settings(),
        f"modal:{socket.gethostname()}:{worker}",
        WORKERS[worker],
        timedelta(seconds=seconds - MARGIN),
    )


@app.function(
    volumes={"/models": models},
    cpu=4,
    memory=8192,
    timeout=INGEST_TIMEOUT,
    max_containers=1,
)
async def drain_ingest() -> int:
    return await _drain("ingest", INGEST_TIMEOUT)


@app.function(
    volumes={"/models": models},
    cpu=1,
    memory=2048,
    timeout=CARDS_TIMEOUT,
    max_containers=1,
)
async def drain_cards() -> int:
    return await _drain("cards", CARDS_TIMEOUT)


async def _start_ready() -> list[str]:
    """Start the drain of each worker with jobs ready; returns which were started."""
    from psycopg import AsyncConnection

    from engram.config import get_settings
    from engram.worker import queue
    from engram.worker.main import WORKERS

    drains = {"ingest": drain_ingest, "cards": drain_cards}
    started = []
    async with await AsyncConnection.connect(get_settings().database_url) as conn:
        for worker, kinds in WORKERS.items():
            if await queue.has_ready(conn, kinds):
                await drains[worker].spawn.aio()
                started.append(worker)
    return started


@app.function(schedule=modal.Period(minutes=15), cpu=0.25, memory=512)
async def sweep() -> None:
    import logging

    from engram import alerts
    from engram.config import get_settings

    try:
        await alerts.run(get_settings())
    except Exception:
        # Never in the way of the jobs; Modal's logs keep the traceback.
        logging.getLogger("engram.alerts").exception("alert check failed")
    await _start_ready()


@app.function(cpu=0.25, memory=512)
@modal.fastapi_endpoint(method="POST")
async def wake(request: Request) -> dict[str, bool]:
    expected = f"Bearer {os.environ['ENGRAM_WORKER_WAKE_TOKEN']}"
    if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
        raise HTTPException(status_code=401)
    started = await _start_ready()
    return {"woken": bool(started)}
