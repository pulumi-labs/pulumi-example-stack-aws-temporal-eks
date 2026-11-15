"""Durable workflow state and bounded retry scheduling."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from worker.activities import prepare_invoice
    from worker.models import Invoice, InvoiceResult


@workflow.defn
class InvoiceWorkflow:
    """Mutable result is workflow state reconstructed by deterministic replay."""

    def __init__(self) -> None:
        self.result: InvoiceResult | None = None

    @workflow.run
    async def run(self, invoice: Invoice) -> InvoiceResult:
        """Schedule retryable work and retain its completed typed result."""
        self.result = await workflow.execute_activity(
            prepare_invoice, invoice, start_to_close_timeout=timedelta(seconds=10),
            schedule_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=5), maximum_attempts=3,
            ),
        )
        return self.result

    @workflow.query
    def invoice_result(self) -> InvoiceResult | None:
        """Return pending or completed state, including after workflow closure."""
        return self.result
