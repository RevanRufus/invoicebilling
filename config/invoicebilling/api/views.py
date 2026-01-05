from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from invoicebilling.models import Invoice, InvoiceItem, PaymentTransaction
from decimal import Decimal
from invoicebilling.api.serializer import InvoiceSerializer, PaymentSerializer

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from django.shortcuts import get_object_or_404
from django.db import transaction


def api_error(code: str, message, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"error": {"code": code, "message": message}}, status=http_status)


def compute_totals(invoice: Invoice):
    """
    Compute totals from items (simple python loop; easy to understand).
    """
    items = invoice.items.all()
    if not items.exists():
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")

    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")

    for it in items:
        line_sub = it.qty * it.unit_price
        line_tax = (line_sub * it.tax_rate) / Decimal("100.00")
        subtotal += line_sub
        tax_total += line_tax

    grand_total = subtotal + tax_total

    subtotal = subtotal.quantize(Decimal("0.01"))
    tax_total = tax_total.quantize(Decimal("0.01"))
    grand_total = grand_total.quantize(Decimal("0.01"))
    return subtotal, tax_total, grand_total


@extend_schema(
    summary="Create invoice (Draft)",
    description="Creates a new invoice in DRAFT status.",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "number": {"type": "string", "example": "INV-0001"},
                "customer_name": {"type": "string", "example": "Acme Pvt Ltd"},
            },
            "required": ["number", "customer_name"],
        }
    },
    responses={
        201: InvoiceSerializer,
        400: OpenApiResponse(description="Validation error"),
    },
)
@api_view(["POST"])
def create_invoice(request):
    number = request.data.get("number")
    customer_name = request.data.get("customer_name")

    if not number:
        return api_error("VALIDATION_ERROR", {"number": "This field is required."})
    if not customer_name:
        return api_error(
            "VALIDATION_ERROR", {"customer_name": "This field is required."}
        )

    if Invoice.objects.filter(number=number).exists():
        return api_error("DUPLICATE_NUMBER", "Invoice number already exists.")

    invoice = Invoice.objects.create(
        number=number, customer_name=customer_name, status="DRAFT"
    )
    return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="List invoices",
    description="Returns a list of invoices.",
    responses={
        200: InvoiceSerializer(many=True),
        400: OpenApiResponse(description="Validation error"),
    },
)
@api_view(["GET"])
def list_invoices(request):
    qs = Invoice.objects.all().order_by("created_at")
    return Response(InvoiceSerializer(qs, many=True).data, status=status.HTTP_200_OK)


@extend_schema(
    summary="Add Items (Drafted Invoice only)",
    description="Adds an item to a DRAFT invoice. Not allowed after finalization.",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "example": "Laptop bag"},
                "qty": {"type": "string", "example": "2"},
                "unit_price": {"type": "string", "example": "750.00"},
                "tax_rate": {"type": "string", "example": "18.00"},
            },
            "required": ["description", "qty", "unit_price"],
        }
    },
    responses={
        201: InvoiceSerializer,
        400: OpenApiResponse(description="Validation error"),
        409: OpenApiResponse(description="Immutable invoice (not DRAFT)"),
    },
)
@api_view(["POST"])
def add_item(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status != "DRAFT":
        return api_error(
            "IMMUTABLE_INVOICE",
            "Cannot add items after finalization.",
            status.HTTP_409_CONFLICT,
        )

    desc = request.data.get("description")
    qty = request.data.get("qty")
    unit_price = request.data.get("unit_price")
    tax_rate = request.data.get("tax_rate", "0.00")

    if not desc:
        return api_error("VALIDATION_ERROR", {"description": "This field is required."})
    try:
        qty = Decimal(str(qty))
        unit_price = Decimal(str(unit_price))
        tax_rate = Decimal(str(tax_rate))
    except Exception:
        return api_error(
            "VALIDATION_ERROR", "qty/unit_price/tax_rate must be valid numbers."
        )

    if qty <= 0:
        return api_error("VALIDATION_ERROR", {"qty": "Must be > 0."})
    if unit_price < 0:
        return api_error("VALIDATION_ERROR", {"unit_price": "Cannot be negative."})
    if tax_rate < 0:
        return api_error("VALIDATION_ERROR", {"tax_rate": "Cannot be negative."})

    InvoiceItem.objects.create(
        invoice=invoice,
        description=desc,
        qty=qty,
        unit_price=unit_price,
        tax_rate=tax_rate,
    )

    return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Finalize invoice (Lock)",
    description="Locks the invoice. Only DRAFT invoices can be finalized. Totals are frozen.",
    responses={
        200: InvoiceSerializer,
        400: OpenApiResponse(description="Cannot finalize (no items / validation)"),
        409: OpenApiResponse(description="Invalid status transition"),
    },
)
@api_view(["POST"])
def finalize_invoice(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status != "DRAFT":
        return api_error(
            "INVALID_STATUS",
            "Only DRAFT invoices can be finalized.",
            status.HTTP_409_CONFLICT,
        )

    if not invoice.items.exists():
        return api_error("NO_ITEMS", "Cannot finalize invoice without items.")

    subtotal, tax_total, grand_total = compute_totals(invoice)

    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.grand_total = grand_total
    invoice.status = "FINALIZED"
    invoice.save(
        update_fields=["subtotal", "tax_total", "grand_total", "status", "updated_at"]
    )

    return Response(InvoiceSerializer(invoice).data, status=status.HTTP_200_OK)


@extend_schema(
    summary="Record payment",
    description="Records a payment against an invoice. Invoice must be FINALIZED. Prevents overpayment.",
    request=PaymentSerializer,
    responses={
        201: InvoiceSerializer,
        400: OpenApiResponse(description="Validation / overpayment"),
        409: OpenApiResponse(description="Invoice not in correct status"),
    },
    examples=[
        OpenApiExample(
            "Payment Example",
            value={"amount": "1000.00", "reference": "TXN123"},
            request_only=True,
        )
    ],
)
@api_view(["POST"])
def record_payment(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status == "DRAFT":
        return api_error(
            "INVALID_STATUS",
            "Finalize invoice before taking payments.",
            status.HTTP_409_CONFLICT,
        )

    amount = request.data.get("amount")
    reference = request.data.get("reference", "")

    try:
        amount = Decimal(str(amount))
    except Exception:
        return api_error("VALIDATION_ERROR", {"amount": "Must be a valid number."})

    if amount <= 0:
        return api_error("VALIDATION_ERROR", {"amount": "Must be > 0."})

    with transaction.atomic():
        inv = Invoice.objects.select_for_update().get(pk=invoice.pk)

        if inv.amount_paid + amount > inv.grand_total:
            return api_error("OVERPAYMENT", "Payment would exceed invoice total.")

        # if inv.amount_paid + amount < inv.grand_total:
        #     return api_error(
        #         "LESSPAYMENT",
        #         "Payment amount is less than the remaining invoice balance.",
        #     )

        PaymentTransaction.objects.create(
            invoice=inv, amount=amount, reference=reference
        )

        inv.amount_paid = (inv.amount_paid + amount).quantize(Decimal("0.01"))

        if inv.amount_paid == inv.grand_total:
            inv.status = "PAID"

        inv.save(update_fields=["amount_paid", "status", "updated_at"])

    invoice.refresh_from_db()
    return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)
