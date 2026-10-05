from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    BackgroundTasks,
    status,
    HTTPException,
    Query,
    Body,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer
from sqlalchemy import text, func

from app.database.session import get_db
from app.models import CreditNote
from app.models.invoice import Invoice
from app.schemas import CreditNoteListItem, CreditNoteDetailResponse
from app.core.tasks import sync_credit_notes, sync_alegra_credit_notes_task
from app.api.dependencies import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


class SyncRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_credit_notes_endpoint(
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    payload: Optional[SyncRequest] = Body(None),
):
    """
    Manually triggers credit note synchronization from Alegra in the background.
    Requires valid YYYY-MM-DD dates to prevent accidental mass downloads.
    """
    body_start = (
        payload.start_date
        if payload
        and payload.start_date not in (None, "", "string", "null", "undefined")
        else None
    )
    body_end = (
        payload.end_date
        if payload and payload.end_date not in (None, "", "string", "null", "undefined")
        else None
    )

    query_start = (
        start_date
        if start_date not in (None, "", "string", "null", "undefined")
        else None
    )
    query_end = (
        end_date if end_date not in (None, "", "string", "null", "undefined") else None
    )

    raw_start = body_start or query_start
    raw_end = body_end or query_end

    if raw_start and not raw_end:
        raw_end = raw_start
    elif raw_end and not raw_start:
        raw_start = raw_end

    if not raw_start or not raw_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar un rango de fechas válido (start_date y end_date en formato YYYY-MM-DD) para evitar sincronizaciones descontroladas.",
        )

    background_tasks.add_task(
        sync_credit_notes,
        start_date=raw_start,
        end_date=raw_end,
    )
    return {
        "status": "Sync initiated",
        "start_date": raw_start,
        "end_date": raw_end,
    }


@router.get("/sync-status")
def get_credit_notes_sync_status():
    """
    Returns whether a credit notes synchronization background task is currently active.
    """
    from app.core.tasks import is_credit_note_syncing
    return {"is_syncing": is_credit_note_syncing()}



@router.post("/daily-check-credit-notes", status_code=status.HTTP_202_ACCEPTED)
def daily_check_credit_notes(background_tasks: BackgroundTasks):
    """
    Initiates incremental synchronization of credit notes from Alegra for yesterday and today
    in the background.
    """
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    background_tasks.add_task(
        sync_alegra_credit_notes_task,
        start_date_str=yesterday_str,
        end_date_str=today_str,
    )
    return {"message": "Daily credit note synchronization started in the background..."}


@router.post("/weekly-check-credit-notes", status_code=status.HTTP_202_ACCEPTED)
def weekly_check_credit_notes(background_tasks: BackgroundTasks):
    """
    Initiates synchronization of credit notes from the last 7 days.
    """
    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)

    today_str = today.strftime("%Y-%m-%d")
    seven_days_ago_str = seven_days_ago.strftime("%Y-%m-%d")

    background_tasks.add_task(
        sync_alegra_credit_notes_task,
        start_date_str=seven_days_ago_str,
        end_date_str=today_str,
    )
    return {
        "message": "Weekly credit note synchronization started in the background..."
    }


@router.post("/period-monthly-check-credit-notes", status_code=status.HTTP_202_ACCEPTED)
def period_monthly_check_credit_notes(background_tasks: BackgroundTasks):
    """
    Initiates synchronization of credit notes for the current month (from day 1 to today).
    """
    today = datetime.now()
    first_day_of_month = today.replace(day=1)

    start_date_str = first_day_of_month.strftime("%Y-%m-%d")
    end_date_str = today.strftime("%Y-%m-%d")

    background_tasks.add_task(
        sync_alegra_credit_notes_task,
        start_date_str=start_date_str,
        end_date_str=end_date_str,
    )
    return {
        "message": f"Monthly credit note synchronization started in the background ({start_date_str} to {end_date_str})..."
    }


@router.get("/", response_model=List[CreditNoteListItem])
def get_credit_notes(
    limit: int = Query(
        default=50, ge=1, le=500, description="Maximum number of items to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    start_date: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """
    Retrieves the list of actual credit notes stored in the database, sorted by date in descending order.
    Supports optional date range filtering via start_date and end_date (YYYY-MM-DD).
    Lightweight transmission optimized for high speed and cloud deployment.
    """
    query = db.query(
        CreditNote.id_credit_note,
        CreditNote.id_alegra,
        CreditNote.id_invoice,
        CreditNote.date,
        CreditNote.invoice_date,
        CreditNote.time_only,
        CreditNote.name_client,
        CreditNote.client_id,
        CreditNote.client_identification,
        CreditNote.warehouse_name,
        CreditNote.status,
        CreditNote.type,
        CreditNote.associated_invoices,
        CreditNote.subtotal,
        CreditNote.discount,
        CreditNote.tax,
        CreditNote.total_amount,
        CreditNote.total_applied,
        CreditNote.balance,
        CreditNote.cufe,
        CreditNote.items,
    )

    # Filter by the emission date of the associated invoice (or fallback to credit note date)
    effective_date = func.coalesce(CreditNote.invoice_date, CreditNote.date)
    if start_date:
        query = query.filter(effective_date >= start_date)
    if end_date:
        query = query.filter(effective_date <= end_date)

    query = query.order_by(effective_date.desc(), CreditNote.date.desc())

    query = query.offset(offset).limit(limit)

    rows = query.all()

    # --- Batch-resolve invoice dates for any legacy records without invoice_date populated ---
    assoc_ids_set: set = set()
    for r in rows:
        if not r.invoice_date and r.associated_invoices and isinstance(r.associated_invoices, list):
            for assoc in r.associated_invoices:
                if isinstance(assoc, dict):
                    raw_id = assoc.get("id")
                    if raw_id:
                        try:
                            assoc_ids_set.add(int(raw_id))
                        except (ValueError, TypeError):
                            pass

    invoice_date_map: dict = {}
    if assoc_ids_set:
        inv_rows = (
            db.query(Invoice.id_alegra, Invoice.date)
            .filter(Invoice.id_alegra.in_(list(assoc_ids_set)))
            .all()
        )
        for inv in inv_rows:
            if inv.id_alegra and inv.date:
                invoice_date_map[inv.id_alegra] = str(inv.date)

    result: List[CreditNoteListItem] = []
    for r in rows:
        id_inv = r.id_invoice
        invoice_date_str = str(r.invoice_date) if r.invoice_date else None

        if (
            not id_inv
            and r.associated_invoices
            and isinstance(r.associated_invoices, list)
            and len(r.associated_invoices) > 0
        ):
            first_assoc = r.associated_invoices[0]
            if isinstance(first_assoc, dict):
                id_inv = (
                    first_assoc.get("fullNumber")
                    or first_assoc.get("number")
                    or first_assoc.get("id")
                )
                if not invoice_date_str:
                    raw_assoc_id = first_assoc.get("id")
                    if raw_assoc_id:
                        try:
                            alegra_id = int(raw_assoc_id)
                            invoice_date_str = invoice_date_map.get(alegra_id)
                        except (ValueError, TypeError):
                            pass

        eff_date = r.invoice_date or r.date
        result.append(
            CreditNoteListItem(
                id=str(r.id_credit_note or r.id_alegra),
                id_credit_note=r.id_credit_note,
                id_alegra=r.id_alegra,
                id_invoice=str(id_inv) if id_inv else None,
                date=str(eff_date) if eff_date else None,
                invoice_date=invoice_date_str or (str(eff_date) if eff_date else None),
                nc_date=str(r.date) if r.date else None,
                created_at=str(r.date) if r.date else None,
                time_only=r.time_only,
                name_client=r.name_client,
                client=r.name_client,
                client_id=r.client_id,
                client_identification=r.client_identification,
                warehouse_name=r.warehouse_name,
                status=r.status,
                type=r.type,
                associated_invoices=r.associated_invoices or [],
                subtotal=float(r.subtotal or 0) if r.subtotal is not None else 0.0,
                discount=float(r.discount or 0) if r.discount is not None else 0.0,
                tax=float(r.tax or 0) if r.tax is not None else 0.0,
                total_amount=float(r.total_amount or 0),
                amount=float(r.total_amount or 0),
                total_applied=float(r.total_applied or 0) if r.total_applied is not None else 0.0,
                balance=float(r.balance or 0) if r.balance is not None else 0.0,
                cufe=r.cufe,
                items=r.items if isinstance(r.items, list) else [],
            )
        )
    return result


@router.get("/{credit_note_id}", response_model=CreditNoteDetailResponse)
def get_credit_note_detail(credit_note_id: str, db: Session = Depends(get_db)):
    """
    Retrieves full credit note details including complete items array for a specific credit note.
    Searches by id_alegra, id_credit_note, or unique_id.
    """
    cn = None
    if credit_note_id.isdigit():
        cn = (
            db.query(CreditNote)
            .filter(CreditNote.id_alegra == int(credit_note_id))
            .first()
        )

    if not cn:
        cn = (
            db.query(CreditNote)
            .filter(CreditNote.id_credit_note == credit_note_id)
            .first()
        )

    if not cn:
        try:
            cn = (
                db.query(CreditNote)
                .filter(CreditNote.unique_id == credit_note_id)
                .first()
            )
        except Exception:
            pass

    if not cn:
        raise HTTPException(status_code=404, detail="Nota de crédito no encontrada")

    id_inv = cn.id_invoice
    if (
        not id_inv
        and cn.associated_invoices
        and isinstance(cn.associated_invoices, list)
        and len(cn.associated_invoices) > 0
    ):
        first_assoc = cn.associated_invoices[0]
        if isinstance(first_assoc, dict):
            id_inv = (
                first_assoc.get("fullNumber")
                or first_assoc.get("number")
                or first_assoc.get("id")
            )

    eff_date = cn.invoice_date or cn.date
    return CreditNoteDetailResponse(
        id=str(cn.id_credit_note or cn.id_alegra),
        id_credit_note=cn.id_credit_note,
        id_alegra=cn.id_alegra,
        id_invoice=str(id_inv) if id_inv else None,
        date=str(eff_date) if eff_date else None,
        invoice_date=str(cn.invoice_date) if cn.invoice_date else (str(cn.date) if cn.date else None),
        nc_date=str(cn.date) if cn.date else None,
        created_at=str(cn.date) if cn.date else None,
        time_only=cn.time_only,
        name_client=cn.name_client,
        client=cn.name_client,
        client_id=cn.client_id,
        client_identification=cn.client_identification,
        warehouse_name=cn.warehouse_name,
        status=cn.status,
        type=cn.type,
        associated_invoices=cn.associated_invoices or [],
        subtotal=float(cn.subtotal or 0) if cn.subtotal is not None else 0.0,
        discount=float(cn.discount or 0) if cn.discount is not None else 0.0,
        tax=float(cn.tax or 0) if cn.tax is not None else 0.0,
        total_amount=float(cn.total_amount or 0),
        amount=float(cn.total_amount or 0),
        total_applied=float(cn.total_applied or 0) if cn.total_applied is not None else 0.0,
        balance=float(cn.balance or 0) if cn.balance is not None else 0.0,
        cufe=cn.cufe,
        items=cn.items or [],
    )
