"""Submit a JSON invoice through the real mTLS frontend."""

import sys
from datetime import timedelta
from pathlib import Path

import anyio
from temporalio.common import WorkflowIDReusePolicy

from worker.connection import connect
from worker.models import Invoice
from worker.workflows import InvoiceWorkflow


async def main() -> None:
    """Use the invoice ID as a stable workflow ID for application idempotency."""
    invoice = Invoice.model_validate_json(Path(sys.argv[1]).read_bytes())
    client = await connect()
    result = await client.execute_workflow(
        InvoiceWorkflow.run, invoice, id=f"invoice-{invoice.invoice_id}",
        task_queue="invoices", execution_timeout=timedelta(minutes=2),
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
    print(result.model_dump_json())


if __name__ == "__main__":
    anyio.run(main, backend="asyncio")
