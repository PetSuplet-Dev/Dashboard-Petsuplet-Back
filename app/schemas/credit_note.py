from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import date
from decimal import Decimal
from typing import Optional, Any, List, Dict


# ---------------------------------------------------------------------------
# ORM base / internal schemas
# ---------------------------------------------------------------------------

class CreditNoteBase(BaseModel):
    id_alegra: Optional[int] = None
    id_credit_note: Optional[str] = None
    id_invoice: Optional[str] = None
    date: Optional[Any] = None
    invoice_date: Optional[Any] = None
    nc_date: Optional[Any] = None
    time_only: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    client_id: Optional[str] = None
    name_client: Optional[str] = None
    client_identification: Optional[str] = None
    warehouse_name: Optional[str] = None
    associated_invoices: Optional[List[Dict[str, Any]]] = None
    subtotal: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    total_applied: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    cufe: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None


class CreditNoteCreate(CreditNoteBase):
    pass


class CreditNoteResponse(CreditNoteBase):
    """ORM-bound schema — keeps unique_id for internal consumers."""
    unique_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# API-layer response schemas (exact public contract for GET endpoints)
# ---------------------------------------------------------------------------

class CreditNoteListItem(BaseModel):
    """
    API response schema for GET /credit-notes/ list endpoint.
    Mirrors the computed/aliased field shape of the route handler,
    including batch-resolved invoice_date, client alias, and amount alias.
    """
    id: Optional[str] = None              # id_credit_note or str(id_alegra)
    id_credit_note: Optional[str] = None
    id_alegra: Optional[int] = None
    id_invoice: Optional[str] = None      # resolved from associated_invoices
    date: Optional[str] = None            # effective date (invoice_date or cn date)
    invoice_date: Optional[str] = None    # emission date of the linked invoice
    nc_date: Optional[str] = None         # raw credit note date
    created_at: Optional[str] = None      # alias for nc_date (frontend compat)
    time_only: Optional[str] = None
    name_client: Optional[str] = None
    client: Optional[str] = None          # alias for name_client
    client_id: Optional[str] = None
    client_identification: Optional[str] = None
    warehouse_name: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    associated_invoices: List[Any] = []
    subtotal: float = 0.0
    discount: float = 0.0
    tax: float = 0.0
    total_amount: float = 0.0
    amount: float = 0.0                   # alias for total_amount (frontend compat)
    total_applied: float = 0.0
    balance: float = 0.0
    cufe: Optional[str] = None
    items: List[Any] = []


class CreditNoteDetailResponse(CreditNoteListItem):
    """
    API response schema for GET /credit-notes/{credit_note_id} detail endpoint.
    Inherits all list fields; items is always the full payload.
    """
    pass
