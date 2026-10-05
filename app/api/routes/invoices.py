from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, BackgroundTasks, status, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models import Invoice, CreditNote
from app.schemas import ChartTimelineItem, InvoiceListItem, InvoiceDetailResponse
from app.core.tasks import sync_invoices, sync_alegra_invoices_task
from app.api.dependencies import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


class SyncRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_invoices_endpoint(
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    payload: Optional[SyncRequest] = Body(None),
):
    """
    Manually triggers invoice synchronization from Alegra in the background.
    Requires valid YYYY-MM-DD dates to prevent accidental mass downloads.
    """
    body_start = payload.start_date if payload and payload.start_date not in (None, "", "string", "null", "undefined") else None
    body_end = payload.end_date if payload and payload.end_date not in (None, "", "string", "null", "undefined") else None

    query_start = start_date if start_date not in (None, "", "string", "null", "undefined") else None
    query_end = end_date if end_date not in (None, "", "string", "null", "undefined") else None

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
        sync_invoices,
        start_date=raw_start,
        end_date=raw_end,
    )
    return {
        "status": "Sync initiated",
        "start_date": raw_start,
        "end_date": raw_end,
    }


@router.get("/sync-status")
def get_invoice_sync_status():
    """
    Returns whether an invoice synchronization background task is currently active.
    """
    from app.core.tasks import is_invoice_syncing
    return {"is_syncing": is_invoice_syncing()}




@router.post("/daily-check-invoices", status_code=status.HTTP_202_ACCEPTED)
def daily_check_invoices(background_tasks: BackgroundTasks):
    """
    Initiates incremental synchronization of invoices from Alegra for yesterday and today
    in the background. Responds immediately with HTTP 202 Accepted.
    Designed for light daily updates.
    """
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    background_tasks.add_task(
        sync_alegra_invoices_task, start_date_str=yesterday_str, end_date_str=today_str
    )
    return {"message": "Daily invoice synchronization started in the background..."}


@router.post("/weekly-check-invoices", status_code=status.HTTP_202_ACCEPTED)
def weekly_check_invoices(background_tasks: BackgroundTasks):
    """
    Initiates synchronization of invoices from the last 7 days.
    """
    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)

    today_str = today.strftime("%Y-%m-%d")
    seven_days_ago_str = seven_days_ago.strftime("%Y-%m-%d")

    background_tasks.add_task(
        sync_alegra_invoices_task,
        start_date_str=seven_days_ago_str,
        end_date_str=today_str,
    )
    return {"message": "Weekly invoice synchronization started in the background..."}


@router.post("/period-monthly-check-invoices", status_code=status.HTTP_202_ACCEPTED)
def period_monthly_check_invoices(background_tasks: BackgroundTasks):
    """
    Initiates synchronization of invoices for the current month (from day 1 to today).
    """
    today = datetime.now()
    first_day_of_month = today.replace(day=1)

    start_date_str = first_day_of_month.strftime("%Y-%m-%d")
    end_date_str = today.strftime("%Y-%m-%d")

    background_tasks.add_task(
        sync_alegra_invoices_task,
        start_date_str=start_date_str,
        end_date_str=end_date_str,
    )
    return {
        "message": f"Monthly invoice synchronization started in the background ({start_date_str} to {end_date_str})..."
    }


@router.get("/chart-timeline", response_model=List[ChartTimelineItem])
def get_chart_timeline(db: Session = Depends(get_db)):
    """
    Calculates aggregated daily income (Invoices) vs expenses (Credit Notes)
    directly in PostgreSQL for fast chart rendering.
    """
    inv_agg = (
        db.query(Invoice.date, func.sum(Invoice.total_amount).label("incomes"))
        .filter(Invoice.date.isnot(None))
        .group_by(Invoice.date)
        .all()
    )
    cn_agg = (
        db.query(CreditNote.date, func.sum(CreditNote.total_amount).label("expenses"))
        .filter(CreditNote.date.isnot(None))
        .group_by(CreditNote.date)
        .all()
    )

    daily_map: Dict[str, Dict[str, Any]] = {}
    for r in inv_agg:
        d = str(r.date)
        daily_map[d] = {"date": d, "incomes": float(r.incomes or 0), "expenses": 0.0}

    for r in cn_agg:
        d = str(r.date)
        if d not in daily_map:
            daily_map[d] = {
                "date": d,
                "incomes": 0.0,
                "expenses": float(r.expenses or 0),
            }
        else:
            daily_map[d]["expenses"] = float(r.expenses or 0)

    return sorted(daily_map.values(), key=lambda x: x["date"])


@router.get("/", response_model=List[InvoiceListItem])
def get_invoices(
    limit: int = Query(
        default=50, ge=1, le=500, description="Maximum number of items to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    start_date: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """
    Retrieves the list of actual invoices stored in the database, sorted by date in descending order.
    Supports optional date range filtering via start_date and end_date (YYYY-MM-DD).
    Lightweight transmission optimized for high speed and cloud deployment.
    """
    query = db.query(
        Invoice.id_invoice,
        Invoice.id_alegra,
        Invoice.date,
        Invoice.due_date,
        Invoice.date_time,
        Invoice.status,
        Invoice.payment_form,
        Invoice.term,
        Invoice.client_id,
        Invoice.name_client,
        Invoice.client_identification,
        Invoice.warehouse_id,
        Invoice.warehouse_name,
        Invoice.seller_name,
        Invoice.subtotal,
        Invoice.discount,
        Invoice.tax,
        Invoice.total_amount,
        Invoice.total_paid,
        Invoice.balance,
        Invoice.cufe,
        Invoice.legal_status,
        Invoice.items,
    ).order_by(Invoice.date.desc())

    if start_date:
        query = query.filter(Invoice.date >= start_date)
    if end_date:
        query = query.filter(Invoice.date <= end_date)

    query = query.offset(offset).limit(limit)

    rows = query.all()

    return [
        InvoiceListItem(
            id_invoice=r.id_invoice,
            id=str(r.id_alegra),
            id_alegra=r.id_alegra,
            date=str(r.date) if r.date else None,
            due_date=str(r.due_date) if r.due_date else None,
            date_time=r.date_time.isoformat() if r.date_time else None,
            status=r.status,
            payment_form=r.payment_form,
            term=r.term,
            client_id=r.client_id,
            name_client=r.name_client,
            client_identification=r.client_identification,
            warehouse_id=r.warehouse_id,
            warehouse_name=r.warehouse_name,
            seller_name=r.seller_name,
            subtotal=float(r.subtotal or 0) if r.subtotal is not None else 0.0,
            discount=float(r.discount or 0) if r.discount is not None else 0.0,
            tax=float(r.tax or 0) if r.tax is not None else 0.0,
            total_amount=float(r.total_amount or 0),
            total_paid=float(r.total_paid or 0) if r.total_paid is not None else 0.0,
            balance=float(r.balance or 0) if r.balance is not None else 0.0,
            cufe=r.cufe,
            legal_status=r.legal_status,
            items=r.items if isinstance(r.items, list) else [],
        )
        for r in rows
    ]


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
def get_invoice_detail(invoice_id: str, db: Session = Depends(get_db)):
    """
    Retrieves full invoice details including complete items array for a specific invoice.
    Searches by id_alegra, id_invoice, or unique_id.
    """
    invoice = None
    if invoice_id.isdigit():
        invoice = db.query(Invoice).filter(Invoice.id_alegra == int(invoice_id)).first()

    if not invoice:
        invoice = db.query(Invoice).filter(Invoice.id_invoice == invoice_id).first()

    if not invoice:
        try:
            invoice = db.query(Invoice).filter(Invoice.unique_id == invoice_id).first()
        except Exception:
            pass

    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    return InvoiceDetailResponse(
        id_invoice=invoice.id_invoice,
        id=str(invoice.id_alegra),
        id_alegra=invoice.id_alegra,
        date=str(invoice.date) if invoice.date else None,
        due_date=str(invoice.due_date) if invoice.due_date else None,
        date_time=invoice.date_time.isoformat() if invoice.date_time else None,
        status=invoice.status,
        payment_form=invoice.payment_form,
        term=invoice.term,
        client_id=invoice.client_id,
        name_client=invoice.name_client,
        client_identification=invoice.client_identification,
        warehouse_id=invoice.warehouse_id,
        warehouse_name=invoice.warehouse_name,
        seller_name=invoice.seller_name,
        subtotal=float(invoice.subtotal or 0) if invoice.subtotal is not None else 0.0,
        discount=float(invoice.discount or 0) if invoice.discount is not None else 0.0,
        tax=float(invoice.tax or 0) if invoice.tax is not None else 0.0,
        total_amount=float(invoice.total_amount or 0),
        total_paid=float(invoice.total_paid or 0) if invoice.total_paid is not None else 0.0,
        balance=float(invoice.balance or 0) if invoice.balance is not None else 0.0,
        cufe=invoice.cufe,
        legal_status=invoice.legal_status,
        items=invoice.items or [],
    )
