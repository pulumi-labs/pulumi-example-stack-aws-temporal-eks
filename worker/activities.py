"""Invoice activity retries safely because calculation has no side effects."""

from temporalio import activity
from temporalio.exceptions import ApplicationError

from worker.models import Invoice, InvoiceResult, calculate_invoice


@activity.defn
async def prepare_invoice(invoice: Invoice) -> InvoiceResult:
    """Optionally inject one transient failure to demonstrate Temporal retry."""
    attempt = activity.info().attempt
    if invoice.simulate_transient_failure and attempt == 1:
        raise ApplicationError(
            "Requested synthetic first-attempt failure", type="TransientBillingError"
        )
    return calculate_invoice(invoice, attempt)
