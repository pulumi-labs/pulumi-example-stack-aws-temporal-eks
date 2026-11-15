"""Run a separate Temporal application worker with graceful signal shutdown."""

import signal
from datetime import timedelta

import anyio
from temporalio.worker import Worker

from worker.activities import prepare_invoice
from worker.connection import connect
from worker.workflows import InvoiceWorkflow


async def main() -> None:
    """Keep the worker alive until Kubernetes requests graceful termination."""
    client = await connect()
    with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
        async with Worker(
            client, task_queue="invoices", workflows=[InvoiceWorkflow],
            activities=[prepare_invoice],
            graceful_shutdown_timeout=timedelta(seconds=30),
        ):
            async for _received in signals:
                break


if __name__ == "__main__":
    anyio.run(main, backend="asyncio")
