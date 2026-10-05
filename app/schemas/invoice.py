from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Any, List, Dict


# ---------------------------------------------------------------------------
# ORM base / internal schemas
# ---------------------------------------------------------------------------

class InvoiceBase(BaseModel):
    id_alegra: Optional[int] = None
    id_invoice: Optional[str] = None
    date: Optional[Any] = None
    due_date: Optional[date] = None
    date_time: Optional[datetime] = None
    status: Optional[str] = None
    payment_form: Optional[str] = None
    term: Optional[str] = None
    client_id: Optional[str] = None
    name_client: Optional[str] = None
    client_identification: Optional[str] = None
    warehouse_id: Optional[str] = None
    warehouse_name: Optional[str] = None
    seller_name: Optional[str] = None
    subtotal: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    total_paid: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    cufe: Optional[str] = None
    legal_status: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceResponse(InvoiceBase):
    """ORM-bound schema — keeps unique_id for internal consumers."""
    unique_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# API-layer response schemas (exact public contract for GET endpoints)
# ---------------------------------------------------------------------------

class InvoiceListItem(BaseModel):
    """
    API response schema for GET /invoices/ list endpoint.
    All monetary fields are coerced to float, dates to str, matching
    the exact field contract consumed by the frontend.
    """
    id_invoice: Optional[str] = None
    id: Optional[str] = None             # alias for id_alegra as string
    id_alegra: Optional[int] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    date_time: Optional[str] = None
    status: Optional[str] = None
    payment_form: Optional[str] = None
    term: Optional[str] = None
    client_id: Optional[str] = None
    name_client: Optional[str] = None
    client_identification: Optional[str] = None
    warehouse_id: Optional[str] = None
    warehouse_name: Optional[str] = None
    seller_name: Optional[str] = None
    subtotal: float = 0.0
    discount: float = 0.0
    tax: float = 0.0
    total_amount: float = 0.0
    total_paid: float = 0.0
    balance: float = 0.0
    cufe: Optional[str] = None
    legal_status: Optional[str] = None
    items: List[Any] = []


class InvoiceDetailResponse(InvoiceListItem):
    """
    API response schema for GET /invoices/{invoice_id} detail endpoint.
    Inherits all list fields; items is always a full list (never truncated).
    """
    pass


class ChartTimelineItem(BaseModel):
    date: str
    incomes: float
    expenses: float
