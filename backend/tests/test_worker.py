import asyncio

from engram.worker.main import run


def test_worker_stops_when_signalled() -> None:
    async def scenario() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(run(stop, poll_interval=10))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(scenario())
