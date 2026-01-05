from rest_framework import serializers
from invoicebilling.models import Invoice, InvoiceItem, PaymentTransaction


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ["id", "description", "qty", "unit_price", "tax_rate"]


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "customer_name",
            "status",
            "subtotal",
            "tax_total",
            "grand_total",
            "amount_paid",
            "created_at",
            "updated_at",
            "items",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ["id", "amount", "reference", "created_at"]
