import uuid
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import List, Generic, TypeVar

T = TypeVar("T")


class ReconciliationBase(BaseModel):
    id_alegra_invoice: int
    id_alegra_credit_note: int
    id_inv: str
    id_cn: str
    name_client: str
    matched_amount: Decimal


class ReconciliationCreate(ReconciliationBase):
    pass


class ReconciliationResponse(ReconciliationBase):
    unique_id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


class ReconciliationPaginatedResponse(BaseModel, Generic[T]):
    total_records: int
    page: int
    limit: int
    data: List[T]


class ClientNetBalanceResponse(BaseModel):
    client_name: str
    total_invoices_amount: Decimal
    total_credit_notes_amount: Decimal
    net_balance: Decimal
    invoice_count: int
    credit_note_count: int


class ReconciliationSyncResponse(BaseModel):
    status: str
    message: str
    reconciled_count: int
    total_records: int

