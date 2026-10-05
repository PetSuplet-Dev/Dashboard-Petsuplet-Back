'''
Contains helper functions to map Alegra API payloads to Pydantic schemas.
'''
from datetime import datetime
from typing import Dict, Any, Optional

from ..schemas.invoice import InvoiceCreate
from ..schemas.credit_note import CreditNoteCreate

def _safe_get(data: Dict, *keys: str) -> Optional[Any]:
    """Safely get a nested value from a dict."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data

def _to_date(date_str: Optional[str]) -> Optional[datetime.date]:
    """Convert YYYY-MM-DD string to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

def _to_datetime(datetime_str: Optional[str]) -> Optional[datetime]:
    """Convert ISO datetime string to datetime object."""
    if not datetime_str:
        return None
    try:
        if datetime_str.endswith('Z'):
            datetime_str = datetime_str[:-1] + '+00:00'
        return datetime.fromisoformat(datetime_str)
    except (ValueError, TypeError):
        return None

def map_alegra_invoice(payload: Dict[str, Any]) -> InvoiceCreate:
    """Maps Alegra API invoice payload to InvoiceCreate schema."""
    return InvoiceCreate(
        id_alegra=_safe_get(payload, "id"),
        id_invoice=_safe_get(payload, "numberTemplate", "fullNumber"),
        date=_to_date(_safe_get(payload, "date")),
        due_date=_to_date(_safe_get(payload, "dueDate")),
        date_time=_to_datetime(_safe_get(payload, "datetime")),
        status=_safe_get(payload, "status"),
        payment_form=_safe_get(payload, "paymentForm"),
        term=_safe_get(payload, "term"),
        client_id=_safe_get(payload, "client", "id"),
        name_client=_safe_get(payload, "client", "name"),
        client_identification=_safe_get(payload, "client", "identification"),
        warehouse_id=_safe_get(payload, "warehouse", "id"),
        warehouse_name=_safe_get(payload, "warehouse", "name"),
        seller_name=_safe_get(payload, "seller", "name"),
        subtotal=_safe_get(payload, "subtotal"),
        discount=_safe_get(payload, "discount"),
        tax=_safe_get(payload, "tax"),
        total_amount=_safe_get(payload, "total"),
        total_paid=_safe_get(payload, "totalPaid"),
        balance=_safe_get(payload, "balance"),
        cufe=_safe_get(payload, "stamp", "cufe"),
        legal_status=_safe_get(payload, "stamp", "legalStatus"),
        items=_safe_get(payload, "items"),
    )

def map_alegra_credit_note(payload: Dict[str, Any]) -> CreditNoteCreate:
    """Maps Alegra API credit note payload to CreditNoteCreate schema."""
    dt_obj = _to_datetime(_safe_get(payload, "datetime"))

    return CreditNoteCreate(
        id_alegra=_safe_get(payload, "id"),
        id_credit_note=_safe_get(payload, "numberTemplate", "fullNumber"),
        date=_to_date(_safe_get(payload, "date")),
        time_only=dt_obj.time().strftime("%H:%M:%S") if dt_obj else None,
        status=_safe_get(payload, "status"),
        type=_safe_get(payload, "type"),
        client_id=_safe_get(payload, "client", "id"),
        name_client=_safe_get(payload, "client", "name"),
        client_identification=_safe_get(payload, "client", "identification"),
        warehouse_name=_safe_get(payload, "warehouse", "name"),
        associated_invoices=_safe_get(payload, "associatedInvoices"),
        subtotal=_safe_get(payload, "subtotal"),
        discount=_safe_get(payload, "discount"),
        tax=_safe_get(payload, "tax"),
        total_amount=_safe_get(payload, "total"),
        total_applied=_safe_get(payload, "totalApplied"),
        balance=_safe_get(payload, "balance"),
        cufe=_safe_get(payload, "stamp", "cufe"),
        items=_safe_get(payload, "items"),
    )
