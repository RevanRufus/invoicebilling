# invoicebilling
Invoice billing API with DRF and Swagger - STRATEGIC VENTURES 


# Invoice Billing API (Django + DRF)

## Overview
A simple invoice billing system built using Django REST Framework.


## Tech Stack
- Python 3.x
- Django
- Django REST Framework
- drf-spectacular (Swagger / OpenAPI)
- mysqlclient
- python-dotenv

## Features
- Create invoice in DRAFT status
- Add items only to DRAFT invoices
- Finalize invoice and lock totals
- Record payments with transaction safety
- Prevent overpayment
- Auto mark invoice as PAID
- Swagger / OpenAPI documentation



## Invoice Lifecycle
- DRAFT → FINALIZED → PAID