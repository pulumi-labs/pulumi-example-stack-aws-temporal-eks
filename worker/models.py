"""Invoice input boundary and integer monetary calculation."""

from typing import Annotated, NewType

from pydantic import BaseModel, ConfigDict, Field

InvoiceId = NewType("InvoiceId", str)
Cents = NewType("Cents", int)


class LineItem(BaseModel):
    """A bounded positive quantity and integer unit price."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    quantity: Annotated[int, Field(strict=True, ge=1, le=10000)]
    unit_price_cents: Annotated[int, Field(strict=True, ge=0, le=100000000)]


class Invoice(BaseModel):
    """Untrusted requests are decoded here by the Pydantic converter."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    invoice_id: Annotated[InvoiceId, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    items: Annotated[tuple[LineItem, ...], Field(min_length=1, max_length=100)]
    tax_basis_points: Annotated[int, Field(strict=True, ge=0, le=10000)]
    simulate_transient_failure: bool = False


class InvoiceResult(BaseModel):
    """A completed calculation with its native activity attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    invoice_id: InvoiceId
    subtotal_cents: Cents
    tax_cents: Cents
    total_cents: Cents
    activity_attempt: int


def calculate_invoice(invoice: Invoice, attempt: int) -> InvoiceResult:
    """Apply half-up tax rounding once to the complete subtotal."""
    subtotal = sum(item.quantity * item.unit_price_cents for item in invoice.items)
    tax = (subtotal * invoice.tax_basis_points + 5000) // 10000
    return InvoiceResult(
        invoice_id=invoice.invoice_id, subtotal_cents=Cents(subtotal),
        tax_cents=Cents(tax), total_cents=Cents(subtotal + tax),
        activity_attempt=attempt,
    )
