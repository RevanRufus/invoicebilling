from django.urls import path
from .views import (
    create_invoice,
    list_invoices,
    add_item,
    finalize_invoice,
    record_payment,
)

urlpatterns = [
    path("api/invoices", create_invoice, name="create invoice"),
    path("api/invoices/list/", list_invoices, name="list_invoices"),
    path("api/invoices/<int:pk>/items/", add_item, name="add item"),
    path("api/invoices/<int:pk>/finalize/", finalize_invoice, name="finalize invoice"),
    path("api/invoices/<int:pk>/payments/", record_payment,name='payment records'),
]
