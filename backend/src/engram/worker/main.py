"""Background worker.

Long-running jobs (ingesting a textbook, generating a chapter's cards) run here rather
than in the API. Jobs will be claimed from a Postgres-backed queue once the schema lands;
until then the loop only polls on an interval and shuts down cleanly on SIGINT/SIGTERM.
"""

import asyncio
import contextlib
import logging
import signal

from engram.config import get_settings

logger = logging.getLogger("engram.worker")


async def run_once() -> bool:
    """Claim and run at most one job. Returns True if a job ran."""
    return False


async def run(stop: asyncio.Event, poll_interval: float) -> None:
    logger.info("worker started")
    while not stop.is_set():
        ran = await run_once()
        if ran:
            continue
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)
    logger.info("worker stopped")


async def _main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await run(stop, get_settings().worker_poll_interval_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(_main())


if __name__ == "__main__":
    main()
