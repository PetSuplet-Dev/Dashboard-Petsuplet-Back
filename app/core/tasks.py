import asyncio
import re
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.core.alegra_client import get_alegra_client
import logging
from starlette.concurrency import run_in_threadpool
from app.models.invoice import Invoice
from app.models.credit_note import CreditNote
from app.utils.db_utils import bulk_upsert_objects

logger = logging.getLogger(__name__)

# Concurrency locks to prevent overlapping runs of the same sync task
INVOICE_SYNC_LOCK = asyncio.Lock()
CREDIT_NOTE_SYNC_LOCK = asyncio.Lock()


def is_invoice_syncing() -> bool:
    """Return whether invoice sync task is currently locked/running."""
    return INVOICE_SYNC_LOCK.locked()


def is_credit_note_syncing() -> bool:
    """Return whether credit note sync task is currently locked/running."""
    return CREDIT_NOTE_SYNC_LOCK.locked()


def __getattr__(name: str):
    """Dynamic fallback for legacy module attributes."""
    if name == "IS_SYNCING_INVOICES":
        return INVOICE_SYNC_LOCK.locked()
    if name == "IS_SYNCING_CREDIT_NOTES":
        return CREDIT_NOTE_SYNC_LOCK.locked()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def _to_date(date_str):
    """Convert YYYY-MM-DD string to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _to_datetime(datetime_str):
    """Convert ISO datetime string to datetime object."""
    if not datetime_str:
        return None
    try:
        s = str(datetime_str)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None



_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date_str(value: Optional[str]) -> Optional[str]:
    """Return the value only if it matches YYYY-MM-DD format, else None."""
    if value and _DATE_RE.match(value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            pass
    return None


def _generate_date_range(start_date_str: str, end_date_str: str) -> List[str]:
    """Generate a list of YYYY-MM-DD strings for each day in the range [start, end]."""
    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


BATCH_SIZE_ALEGRA = 30  # Max allowed by Alegra API


def _parse_invoice_item(item: Dict) -> Dict:
    """Parse a single Alegra invoice API response item into a DB-ready dict."""
    num_template = item.get("numberTemplate", {})
    id_inv = (
        str(num_template.get("fullNumber", ""))
        if num_template.get("fullNumber")
        else None
    )

    client_data = item.get("client") or {}
    warehouse_data = item.get("warehouse") or {}
    seller_data = item.get("seller") or {}
    stamp_data = item.get("stamp") or {}

    return {
        "id_alegra": int(item["id"]) if item.get("id") else None,
        "id_invoice": id_inv,
        "date": _to_date(item.get("date")),
        "due_date": _to_date(item.get("dueDate")),
        "date_time": _to_datetime(item.get("datetime")),
        "status": item.get("status"),
        "payment_form": item.get("paymentForm"),
        "term": item.get("term"),
        "client_id": (
            str(client_data.get("id"))
            if client_data.get("id")
            else None
        ),
        "name_client": client_data.get("name"),
        "client_identification": client_data.get("identification"),
        "warehouse_id": (
            str(warehouse_data.get("id"))
            if warehouse_data.get("id")
            else None
        ),
        "warehouse_name": warehouse_data.get("name"),
        "seller_name": seller_data.get("name"),
        "subtotal": item.get("subtotal"),
        "discount": item.get("discount"),
        "tax": item.get("tax"),
        "total_amount": item.get("total"),
        "total_paid": item.get("totalPaid"),
        "balance": item.get("balance"),
        "cufe": stamp_data.get("cufe"),
        "legal_status": stamp_data.get("legalStatus"),
        "items": item.get("items"),
    }


def _parse_credit_note_item(item: Dict) -> Dict:
    """Parse a single Alegra credit note API response item into a DB-ready dict."""
    num_template = item.get("numberTemplate", {})
    id_cn = (
        str(num_template.get("fullNumber", ""))
        if num_template.get("fullNumber")
        else None
    )

    client_data = item.get("client") or {}
    warehouse_data = item.get("warehouse") or {}
    stamp_data = item.get("stamp") or {}
    dt_obj = _to_datetime(item.get("datetime"))

    associated_invoices = item.get("invoices") or item.get("associatedInvoices") or []

    # Extract associated invoice ID and the invoice's emission date
    id_inv = None
    invoice_date = None
    if isinstance(associated_invoices, list) and len(associated_invoices) > 0:
        first_inv = associated_invoices[0]
        if isinstance(first_inv, dict):
            id_inv = (
                first_inv.get("fullNumber")
                or first_inv.get("number")
                or (str(first_inv.get("id")) if first_inv.get("id") else None)
            )
            raw_inv_date = first_inv.get("date")
            if raw_inv_date:
                invoice_date = _to_date(raw_inv_date)

    # If no linked invoice date is found, fallback to the credit note's own date
    cn_date = _to_date(item.get("date"))
    if not invoice_date:
        invoice_date = cn_date

    return {
        "id_alegra": int(item["id"]) if item.get("id") else None,
        "id_credit_note": id_cn,
        "id_invoice": id_inv,
        "date": cn_date,
        "invoice_date": invoice_date,
        "time_only": (
            dt_obj.time().strftime("%H:%M:%S")
            if dt_obj
            else None
        ),
        "status": item.get("status"),
        "type": item.get("type"),
        "client_id": (
            str(client_data.get("id"))
            if client_data.get("id")
            else None
        ),
        "name_client": client_data.get("name"),
        "client_identification": client_data.get("identification"),
        "warehouse_name": warehouse_data.get("name"),
        "associated_invoices": associated_invoices,
        "subtotal": item.get("subtotal"),
        "discount": item.get("discount"),
        "tax": item.get("tax"),
        "total_amount": item.get("total"),
        "total_applied": item.get("totalApplied"),
        "balance": item.get("balance"),
        "cufe": stamp_data.get("cufe"),
        "items": item.get("items"),
    }


def _bulk_upsert_invoices_sync(session: Session, records: List[Dict]) -> None:
    bulk_upsert_objects(
        db=session,
        model=Invoice,
        records=records,
        index_elements=["id_alegra"],
    )


def _bulk_upsert_credit_notes_sync(session: Session, records: List[Dict]) -> None:
    bulk_upsert_objects(
        db=session,
        model=CreditNote,
        records=records,
        index_elements=["id_alegra"],
    )


def _create_session_sync() -> Session:
    return SessionLocal()


def _close_session_sync(session: Session) -> None:
    session.close()


def _rollback_session_sync(session: Session) -> None:
    session.rollback()


async def _sync_invoices_by_date_range(
    session: Session,
    alegra_client,
    start_date: str,
    end_date: str,
) -> int:
    """
    Optimized sync: iterates day-by-day using Alegra's exact `date` filter.
    This avoids downloading the entire invoice history and filtering in memory.
    """
    dates = _generate_date_range(start_date, end_date)
    total_processed = 0

    for day_str in dates:
        current_start = 0
        print(f"  [invoices] Syncing date: {day_str}")

        while True:
            invoice_list_data = await alegra_client.get_invoices_page(
                start=current_start,
                limit=BATCH_SIZE_ALEGRA,
                order_field="id",
                order_direction="ASC",
                date=day_str,
            )

            if not invoice_list_data:
                break

            invoices_to_upsert = [_parse_invoice_item(item) for item in invoice_list_data]

            if invoices_to_upsert:
                await run_in_threadpool(
                    _bulk_upsert_invoices_sync,
                    session,
                    invoices_to_upsert,
                )
                total_processed += len(invoices_to_upsert)

            if len(invoice_list_data) < BATCH_SIZE_ALEGRA:
                break

            current_start += BATCH_SIZE_ALEGRA

    return total_processed


async def _sync_invoices_full(
    session: Session,
    alegra_client,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> int:
    """
    Full sync: paginates through all invoices ordered DESC and optionally
    filters by date range in memory. Used when no range is specified
    or as a fallback.
    """
    current_start = 0
    total_processed = 0

    while True:
        invoice_list_data = await alegra_client.get_invoices_page(
            start=current_start,
            limit=BATCH_SIZE_ALEGRA,
            order_field="date",
            order_direction="DESC",
        )

        if not invoice_list_data:
            print("No more invoices to fetch or an error occurred.")
            break

        invoices_to_upsert = []
        stop_sync = False

        for item in invoice_list_data:
            item_date = item.get("date", "")

            if start_date and item_date < start_date:
                stop_sync = True
                break

            if end_date and item_date > end_date:
                continue

            invoices_to_upsert.append(_parse_invoice_item(item))

        if invoices_to_upsert:
            await run_in_threadpool(
                _bulk_upsert_invoices_sync,
                session,
                invoices_to_upsert,
            )
            total_processed += len(invoices_to_upsert)

        if stop_sync or len(invoice_list_data) < BATCH_SIZE_ALEGRA:
            break

        current_start += BATCH_SIZE_ALEGRA

    return total_processed


async def _sync_credit_notes_by_date_range(
    session: Session,
    alegra_client,
    start_date: str,
    end_date: str,
) -> int:
    """
    Optimized sync: iterates day-by-day using Alegra's exact `date` filter.
    Identical logic to invoice synchronization.
    """
    dates = _generate_date_range(start_date, end_date)
    total_processed = 0

    for day_str in dates:
        current_start = 0
        print(f"  [credit_notes] Syncing date: {day_str}")

        while True:
            cn_list_data = await alegra_client.get_credit_notes_page(
                start=current_start,
                limit=BATCH_SIZE_ALEGRA,
                order_field="id",
                order_direction="ASC",
                date=day_str,
            )

            if not cn_list_data:
                break

            cn_to_upsert = [_parse_credit_note_item(item) for item in cn_list_data]

            if cn_to_upsert:
                await run_in_threadpool(
                    _bulk_upsert_credit_notes_sync,
                    session,
                    cn_to_upsert,
                )
                total_processed += len(cn_to_upsert)

            if len(cn_list_data) < BATCH_SIZE_ALEGRA:
                break

            current_start += BATCH_SIZE_ALEGRA

    return total_processed


async def _sync_credit_notes_full(
    session: Session,
    alegra_client,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> int:
    """
    Full sync: paginates through all credit notes ordered DESC and optionally
    filters by date range in memory.
    """
    current_start = 0
    total_processed = 0

    while True:
        cn_list_data = await alegra_client.get_credit_notes_page(
            start=current_start,
            limit=BATCH_SIZE_ALEGRA,
            order_field="date",
            order_direction="DESC",
        )

        if not cn_list_data:
            print(f"[sync_credit_notes] No more credit notes returned by Alegra at offset {current_start}.")
            break

        print(
            f"[sync_credit_notes] Retrieved full sync batch offset={current_start} "
            f"({len(cn_list_data)} records)"
        )

        cn_to_upsert = []
        for item in cn_list_data:
            item_date = item.get("date", "")
            if start_date and item_date < start_date:
                continue
            if end_date and item_date > end_date:
                continue
            cn_to_upsert.append(_parse_credit_note_item(item))

        if cn_to_upsert:
            await run_in_threadpool(
                _bulk_upsert_credit_notes_sync,
                session,
                cn_to_upsert,
            )
            total_processed += len(cn_to_upsert)
            print(
                f"[sync_credit_notes] Upserted {len(cn_to_upsert)} credit notes to PostgreSQL "
                f"(Total processed: {total_processed})"
            )

        if len(cn_list_data) < BATCH_SIZE_ALEGRA:
            break

        current_start += BATCH_SIZE_ALEGRA

    return total_processed


def recalculate_customer_metrics_sync(session: Session) -> int:
    """
    Recalculates customer metrics (total_invoices, total_credit_notes, product_quantity,
    sales_before_tax, sales_after_tax) from invoices and credit_notes tables in PostgreSQL.
    Resolves any missing client_identification by matching client code (client_id) and name (name_client).
    Also clears metrics for any customers without invoices or credit notes.
    """
    # 1. Resolver client_identification faltante en facturas por coincidencia estricta de código (client_id) y nombre
    backfill_by_code_and_name = text("""
        UPDATE invoices i
        SET client_identification = sub.client_identification
        FROM (
            SELECT client_id, TRIM(UPPER(name_client)) as norm_name, client_identification
            FROM (
                SELECT client_id, name_client, client_identification,
                       ROW_NUMBER() OVER(PARTITION BY client_id, TRIM(UPPER(name_client)) ORDER BY date DESC) as rn
                FROM invoices
                WHERE client_identification IS NOT NULL AND TRIM(client_identification) != ''
            ) s WHERE rn = 1
        ) sub
        WHERE (i.client_identification IS NULL OR TRIM(i.client_identification) = '')
          AND i.client_id = sub.client_id
          AND TRIM(UPPER(i.name_client)) = sub.norm_name;
    """)
    session.execute(backfill_by_code_and_name)

    # 2. Resolver client_identification faltante por coincidencia de nombre con tabla customers
    backfill_by_customer_name = text("""
        UPDATE invoices i
        SET client_identification = c.identification
        FROM (
            SELECT DISTINCT ON (TRIM(UPPER(name))) TRIM(UPPER(name)) as norm_name, identification
            FROM customers
            WHERE identification IS NOT NULL AND TRIM(identification) != ''
            ORDER BY TRIM(UPPER(name)), created_at DESC NULLS LAST
        ) c
        WHERE (i.client_identification IS NULL OR TRIM(i.client_identification) = '')
          AND TRIM(UPPER(i.name_client)) = c.norm_name;
    """)
    session.execute(backfill_by_customer_name)

    # 3. Mismo procedimiento preventivo para notas crédito
    backfill_cn = text("""
        UPDATE credit_notes cn
        SET client_identification = sub.client_identification
        FROM (
            SELECT client_id, TRIM(UPPER(name_client)) as norm_name, client_identification
            FROM (
                SELECT client_id, name_client, client_identification,
                       ROW_NUMBER() OVER(PARTITION BY client_id, TRIM(UPPER(name_client)) ORDER BY date DESC) as rn
                FROM invoices
                WHERE client_identification IS NOT NULL AND TRIM(client_identification) != ''
            ) s WHERE rn = 1
        ) sub
        WHERE (cn.client_identification IS NULL OR TRIM(cn.client_identification) = '')
          AND cn.client_id = sub.client_id
          AND TRIM(UPPER(cn.name_client)) = sub.norm_name;
    """)
    session.execute(backfill_cn)
    session.commit()

    update_sql = text("""
        WITH inv_agg AS (
            SELECT 
                TRIM(inv.client_identification) as client_identification,
                COUNT(*) as total_invoices,
                COALESCE(SUM(inv.subtotal), 0) as inv_subtotal,
                COALESCE(SUM(inv.total_amount), 0) as inv_total,
                COALESCE(SUM(item_stats.qty), 0) as product_quantity
            FROM invoices inv
            LEFT JOIN LATERAL (
                SELECT SUM(COALESCE((elem->>'quantity')::numeric, 1)) as qty
                FROM jsonb_array_elements(CASE WHEN inv.items IS NOT NULL AND jsonb_typeof(inv.items) = 'array' THEN inv.items ELSE '[]'::jsonb END) elem
            ) item_stats ON true
            WHERE inv.client_identification IS NOT NULL AND TRIM(inv.client_identification) != ''
            GROUP BY TRIM(inv.client_identification)
        ),
        cn_agg AS (
            SELECT 
                TRIM(client_identification) as client_identification,
                COUNT(*) as total_nc,
                COALESCE(SUM(subtotal), 0) as cn_subtotal,
                COALESCE(SUM(total_amount), 0) as cn_total
            FROM credit_notes
            WHERE client_identification IS NOT NULL AND TRIM(client_identification) != ''
            GROUP BY TRIM(client_identification)
        ),
        combined AS (
            SELECT 
                COALESCE(inv.client_identification, cn.client_identification) as client_id,
                COALESCE(inv.total_invoices, 0) as total_invoices,
                COALESCE(cn.total_nc, 0) as total_credit_notes,
                COALESCE(inv.product_quantity, 0) as product_quantity,
                GREATEST(COALESCE(inv.inv_subtotal, 0) - COALESCE(cn.cn_subtotal, 0), 0) as sales_before_tax,
                GREATEST(COALESCE(inv.inv_total, 0) - COALESCE(cn.cn_total, 0), 0) as sales_after_tax
            FROM inv_agg inv
            FULL OUTER JOIN cn_agg cn ON inv.client_identification = cn.client_identification
        )
        UPDATE customers c
        SET 
            total_invoices = comb.total_invoices,
            total_credit_notes = comb.total_credit_notes,
            product_quantity = comb.product_quantity,
            sales_before_tax = comb.sales_before_tax,
            sales_after_tax = comb.sales_after_tax
        FROM combined comb
        WHERE TRIM(c.identification) = comb.client_id;
    """)
    res = session.execute(update_sql)

    zero_sql = text("""
        UPDATE customers
        SET 
            total_invoices = 0,
            total_credit_notes = 0,
            product_quantity = 0,
            sales_before_tax = 0,
            sales_after_tax = 0
        WHERE TRIM(identification) NOT IN (
            SELECT TRIM(client_identification) FROM invoices WHERE client_identification IS NOT NULL AND TRIM(client_identification) != ''
            UNION
            SELECT TRIM(client_identification) FROM credit_notes WHERE client_identification IS NOT NULL AND TRIM(client_identification) != ''
        );
    """)
    session.execute(zero_sql)
    session.commit()
    return res.rowcount or 0


async def sync_invoices(
    db: Optional[Session] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Asynchronously synchronizes invoices from the Alegra API to the PostgreSQL database.
    Guarded by INVOICE_SYNC_LOCK to prevent overlapping runs.
    """
    if INVOICE_SYNC_LOCK.locked():
        logger.warning("[sync_invoices] Invoice sync task is already running. Skipping execution.")
        print("[sync_invoices] Invoice sync task is already running. Skipping execution.")
        return {"status": "Sync already in progress", "processed": 0}

    async with INVOICE_SYNC_LOCK:
        # Normalize dates if datetime/date objects passed
        if isinstance(start_date, (datetime, date)):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, (datetime, date)):
            end_date = end_date.strftime("%Y-%m-%d")

        # Validate date format (rejects garbage like 'string' from Swagger)
        start_date = _validate_date_str(start_date)
        end_date = _validate_date_str(end_date)

        # If single date provided, treat it as a single-day range
        if start_date and not end_date:
            end_date = start_date
        elif end_date and not start_date:
            start_date = end_date

        session = db if db is not None else await run_in_threadpool(_create_session_sync)
        should_close_session = db is None
        alegra_client = get_alegra_client()

        try:
            use_day_by_day = start_date and end_date
            logger.info(
                f"[sync_invoices] Starting {'day-by-day' if use_day_by_day else 'full'} sync "
                f"(period: {start_date or 'all'} to {end_date or 'all'})"
            )
            print(
                f"[sync_invoices] Starting {'day-by-day' if use_day_by_day else 'full'} sync "
                f"(period: {start_date or 'all'} to {end_date or 'all'})"
            )

            if use_day_by_day:
                total_processed = await _sync_invoices_by_date_range(
                    session, alegra_client, start_date, end_date
                )
            else:
                total_processed = await _sync_invoices_full(
                    session, alegra_client, start_date, end_date
                )

            logger.info(
                f"[sync_invoices] Finished. Total processed: {total_processed} "
                f"(period: {start_date or 'all'} to {end_date or 'all'})."
            )
            print(
                f"[sync_invoices] Finished. Total processed: {total_processed} "
                f"(period: {start_date or 'all'} to {end_date or 'all'})."
            )
            return {"status": "completed", "processed": total_processed}
        except Exception as e:
            logger.error(f"Error in invoice synchronization task: {str(e)}")
            print(f"Error in invoice synchronization task: {str(e)}")
            if session:
                await run_in_threadpool(_rollback_session_sync, session)
            raise e
        finally:
            if should_close_session and session:
                await run_in_threadpool(_close_session_sync, session)


async def sync_credit_notes(
    db: Optional[Session] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Asynchronously synchronizes credit notes from the Alegra API to PostgreSQL.
    Guarded by CREDIT_NOTE_SYNC_LOCK to prevent overlapping runs.
    Identical flow to sync_invoices.
    """
    if CREDIT_NOTE_SYNC_LOCK.locked():
        logger.warning(
            "[sync_credit_notes] Credit note sync task is already running. Skipping execution."
        )
        print(
            "[sync_credit_notes] Credit note sync task is already running. Skipping execution."
        )
        return {"status": "Sync already in progress", "processed": 0}

    async with CREDIT_NOTE_SYNC_LOCK:
        # Normalize dates if datetime/date objects passed
        if isinstance(start_date, (datetime, date)):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, (datetime, date)):
            end_date = end_date.strftime("%Y-%m-%d")

        # Validate date format (rejects garbage like 'string' from Swagger)
        start_date = _validate_date_str(start_date)
        end_date = _validate_date_str(end_date)

        # If single date provided, treat it as a single-day range
        if start_date and not end_date:
            end_date = start_date
        elif end_date and not start_date:
            start_date = end_date

        session = db if db is not None else await run_in_threadpool(_create_session_sync)
        should_close_session = db is None
        alegra_client = get_alegra_client()

        try:
            use_day_by_day = start_date and end_date
            logger.info(
                f"[sync_credit_notes] Starting {'day-by-day' if use_day_by_day else 'full'} sync "
                f"(period: {start_date or 'all'} to {end_date or 'all'})"
            )
            print(
                f"[sync_credit_notes] Starting {'day-by-day' if use_day_by_day else 'full'} sync "
                f"(period: {start_date or 'all'} to {end_date or 'all'})"
            )

            if use_day_by_day:
                total_processed = await _sync_credit_notes_by_date_range(
                    session, alegra_client, start_date, end_date
                )
            else:
                total_processed = await _sync_credit_notes_full(
                    session, alegra_client, start_date, end_date
                )

            logger.info(
                f"[sync_credit_notes] Finished. Total processed: {total_processed} "
                f"(period: {start_date or 'all'} to {end_date or 'all'})."
            )
            print(
                f"[sync_credit_notes] Finished. Total processed: {total_processed} "
                f"(period: {start_date or 'all'} to {end_date or 'all'})."
            )
            return {"status": "completed", "processed": total_processed}
        except Exception as e:
            logger.error(f"Error in credit notes synchronization task: {str(e)}")
            print(f"Error in credit notes synchronization task: {str(e)}")
            if session:
                await run_in_threadpool(_rollback_session_sync, session)
            raise e
        finally:
            if should_close_session and session:
                await run_in_threadpool(_close_session_sync, session)


# Backward compatibility aliases
async def sync_alegra_invoices_task(start_date_str: str, end_date_str: str) -> Dict[str, Any]:
    return await sync_invoices(start_date=start_date_str, end_date=end_date_str)


async def sync_alegra_credit_notes_task(start_date_str: str, end_date_str: str) -> Dict[str, Any]:
    return await sync_credit_notes(start_date=start_date_str, end_date=end_date_str)
