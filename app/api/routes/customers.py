from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database.session import get_db

from app.schemas.customer import (
    CustomerRankingItem,
    CustomerRankingResponse,
    CustomerSummary,
    CustomerKPIs,
    CustomerCommercialBehavior,
    CustomerTransaction,
)
from app.api.dependencies import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])

SPANISH_MONTHS = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
}


def format_spanish_date(d) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except Exception:
            return d
    month_str = SPANISH_MONTHS.get(d.month, str(d.month))
    return f"{d.day:02d} - {month_str} - {d.year}"


@router.get("/ranking", response_model=CustomerRankingResponse)
def get_customers_ranking(
    start_date: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Término de búsqueda"),
    limit: Optional[int] = Query(100, description="Cantidad máxima de registros"),
    offset: int = Query(0, description="Desplazamiento para paginación"),
    db: Session = Depends(get_db),
):
    """
    Retorna el ranking de clientes naturales o empresas, combinando datos de clientes
    con agregaciones de Invoices y Credit_Notes para obtener precios y cantidades reales.
    """
    params: Dict[str, Any] = {}

    date_filter_inv = ""
    date_filter_cn = ""
    if start_date:
        date_filter_inv += " AND date >= :start_date"
        date_filter_cn += " AND date >= :start_date"
        params["start_date"] = start_date
    if end_date:
        date_filter_inv += " AND date <= :end_date"
        date_filter_cn += " AND date <= :end_date"
        params["end_date"] = end_date

    search_filter = ""
    if search and search.strip():
        search_filter = """
            AND (
                LOWER(c.name) LIKE :search_query
                OR LOWER(c.identification) LIKE :search_query
                OR LOWER(c.city) LIKE :search_query
                OR LOWER(COALESCE(c.salesperson, '')) LIKE :search_query
            )
        """
        params["search_query"] = f"%{search.strip().lower()}%"

    count_query_str = f"""
        SELECT COUNT(DISTINCT c.identification)
        FROM customers c
        WHERE c.identification IS NOT NULL {search_filter}
    """
    total_records = db.execute(text(count_query_str), params).scalar() or 0

    has_date_filter = bool(start_date or end_date)
    prod_qty_expr = "COALESCE(inv.product_quantity, 0)" if has_date_filter else "COALESCE(inv.product_quantity, c.product_quantity, 0)"
    subtotal_expr = "COALESCE(inv.inv_subtotal, 0)" if has_date_filter else "COALESCE(inv.inv_subtotal, c.sales_before_tax, 0)"
    total_expr = "COALESCE(inv.inv_total, 0)" if has_date_filter else "COALESCE(inv.inv_total, c.sales_after_tax, 0)"
    invoices_expr = "COALESCE(inv.total_invoices, 0)" if has_date_filter else "COALESCE(inv.total_invoices, c.total_invoices, 0)"
    cn_expr = "COALESCE(cn.total_nc, 0)" if has_date_filter else "COALESCE(cn.total_nc, c.total_credit_notes, 0)"

    ranking_query_str = f"""
        WITH inv_agg AS (
            SELECT 
                inv.client_identification,
                COUNT(*) as total_invoices,
                COALESCE(SUM(inv.subtotal), 0) as inv_subtotal,
                COALESCE(SUM(inv.total_amount), 0) as inv_total,
                COALESCE(SUM(item_stats.qty), 0) as product_quantity
            FROM invoices inv
            LEFT JOIN LATERAL (
                SELECT SUM(COALESCE((elem->>'quantity')::numeric, 1)) as qty
                FROM jsonb_array_elements(CASE WHEN inv.items IS NOT NULL AND jsonb_typeof(inv.items) = 'array' THEN inv.items ELSE '[]'::jsonb END) elem
            ) item_stats ON true
            WHERE inv.client_identification IS NOT NULL {date_filter_inv}
            GROUP BY inv.client_identification
        ),
        cn_agg AS (
            SELECT 
                client_identification,
                COUNT(*) as total_nc,
                COALESCE(SUM(subtotal), 0) as cn_subtotal,
                COALESCE(SUM(total_amount), 0) as cn_total
            FROM credit_notes
            WHERE client_identification IS NOT NULL {date_filter_cn}
            GROUP BY client_identification
        ),
        deduped_customers AS (
            SELECT DISTINCT ON (identification)
                id, identification, name, address, phone, email,
                latitude, longitude, city, locality, neighborhood,
                geographic_zone, route, zones, reporting_salesperson,
                salesperson, salesperson_type, segment,
                product_quantity, sales_before_tax, sales_after_tax,
                total_invoices, total_credit_notes
            FROM customers
            WHERE identification IS NOT NULL
            ORDER BY identification, LENGTH(TRIM(name)) ASC, name ASC
        )
        SELECT 
            c.id,
            c.identification,
            TRIM(c.name) as name,
            c.address,
            c.phone,
            c.email,
            c.latitude,
            c.longitude,
            c.city,
            c.locality,
            c.neighborhood,
            c.geographic_zone,
            COALESCE(NULLIF(c.route, 'ELIMINAR'), c.geographic_zone) as region,
            c.zones as zone,
            c.reporting_salesperson,
            c.salesperson,
            c.salesperson_type,
            c.segment,
            {prod_qty_expr} as product_quantity,
            GREATEST({subtotal_expr} - COALESCE(cn.cn_subtotal, 0), 0) as sales_before_tax,
            GREATEST({total_expr} - COALESCE(cn.cn_total, 0), 0) as sales_after_tax,
            {invoices_expr} as total_invoices,
            {cn_expr} as total_credit_notes
        FROM deduped_customers c
        LEFT JOIN inv_agg inv ON c.identification = inv.client_identification
        LEFT JOIN cn_agg cn ON c.identification = cn.client_identification
        WHERE 1=1 {search_filter}
        ORDER BY sales_after_tax DESC NULLS LAST, name ASC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit or 100
    params["offset"] = offset

    rows = db.execute(text(ranking_query_str), params).fetchall()

    items: List[CustomerRankingItem] = []
    for idx, r in enumerate(rows, start=offset + 1):
        items.append(
            CustomerRankingItem(
                ranking=idx,
                id=str(r.id) if r.id else None,
                identification=r.identification,
                name=r.name or "Sin Nombre",
                address=r.address,
                phone=r.phone,
                email=r.email,
                latitude=r.latitude,
                longitude=r.longitude,
                city=r.city,
                locality=r.locality,
                neighborhood=r.neighborhood,
                geographic_zone=r.geographic_zone,
                region=r.region,
                zone=r.zone,
                reporting_salesperson=r.reporting_salesperson,
                salesperson=r.salesperson,
                salesperson_type=r.salesperson_type,
                segment=r.segment,
                product_quantity=float(r.product_quantity or 0),
                sales_before_tax=float(r.sales_before_tax or 0),
                sales_after_tax=float(r.sales_after_tax or 0),
                total_invoices=int(r.total_invoices or 0),
                total_credit_notes=int(r.total_credit_notes or 0),
            )
        )

    return CustomerRankingResponse(total_records=total_records, items=items)


@router.post("/recalculate-metrics")
def recalculate_customer_metrics(db: Session = Depends(get_db)):
    """
    Recalcula y actualiza en la tabla customers los campos:
    - total_invoices
    - total_credit_notes
    - product_quantity
    - sales_before_tax
    - sales_after_tax
    haciendo el cruce de todas las facturas y notas crédito registradas.
    """
    from app.core.tasks import recalculate_customer_metrics_sync
    affected = recalculate_customer_metrics_sync(db)
    return {
        "status": "success",
        "message": f"Métricas de clientes actualizadas exitosamente ({affected} registros afectados)",
    }


@router.get("/{identification}/summary", response_model=CustomerSummary)
def get_customer_summary(identification: str, db: Session = Depends(get_db)):
    """
    Obtiene el resumen detallado para el div lateral a partir exclusivamente
    de las bases de datos de Invoices y Credit_Notes:
    - KPIs del cliente (Total facturado histórico, NC asociadas, Ticket promedio por pedido)
    - Comportamiento comercial (Días promedio de pago, Frecuencia de compra A, AA, AAA, AAAA)
    - Últimas transacciones (código, fecha, precio)

    Performance: Consolidates 5 individual DB roundtrips into 1 CTE-based SQL statement
    (KPIs + NC count + avg payment days + purchase frequency + customer name) plus 1
    query for ordered recent transactions — total of 2 DB interactions per request.
    """
    # -------------------------------------------------------------------------
    # QUERY 1 (of 2): Single CTE consolidating all KPIs and commercial behavior.
    # Replaces 5 previous individual roundtrips:
    #   - Customer name lookup
    #   - Invoice count + SUM(total_amount)
    #   - Credit note COUNT
    #   - AVG(due_date - date)
    #   - Weekly purchase frequency (last 3 months)
    # -------------------------------------------------------------------------
    summary_query = text("""
        WITH
        -- Customer profile (name and fallback purchase frequency)
        customer_profile AS (
            SELECT
                TRIM(name) AS name,
                salesperson_type
            FROM customers
            WHERE identification = :id
            LIMIT 1
        ),

        -- Invoice KPIs: count, total revenue, average payment lag
        invoice_kpis AS (
            SELECT
                COUNT(*)                                            AS total_invoices,
                COALESCE(SUM(total_amount), 0)                     AS total_historic_invoiced,
                COALESCE(AVG(
                    CASE
                        WHEN due_date IS NOT NULL AND date IS NOT NULL
                        THEN (due_date - date)
                        ELSE NULL
                    END
                ), 0)                                              AS avg_payment_days
            FROM invoices
            WHERE client_identification = :id
        ),

        -- Credit note count
        cn_kpis AS (
            SELECT COALESCE(COUNT(*), 0) AS total_nc
            FROM credit_notes
            WHERE client_identification = :id
        ),

        -- Purchase frequency: average distinct weeks per month over last 3 months
        -- Subquery returns one row per month with distinct-week count, limited to 3.
        monthly_freq AS (
            SELECT
                COALESCE(AVG(weeks_in_month), 0) AS avg_weeks_per_month
            FROM (
                SELECT
                    COUNT(DISTINCT EXTRACT(WEEK FROM date)) AS weeks_in_month
                FROM invoices
                WHERE client_identification = :id
                GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
                ORDER BY EXTRACT(YEAR FROM date) DESC, EXTRACT(MONTH FROM date) DESC
                LIMIT 3
            ) monthly_buckets
        )

        SELECT
            cp.name                                 AS customer_name,
            cp.salesperson_type                     AS salesperson_type,
            ik.total_invoices,
            ik.total_historic_invoiced,
            ik.avg_payment_days,
            cn.total_nc,
            mf.avg_weeks_per_month
        FROM invoice_kpis ik
        CROSS JOIN cn_kpis cn
        CROSS JOIN monthly_freq mf
        LEFT JOIN customer_profile cp ON true
    """)

    row = db.execute(summary_query, {"id": identification}).fetchone()

    # --- Derive KPI values from the single result row ---
    customer_name: str = "Cliente"
    total_invoices: int = 0
    total_historic: float = 0.0
    avg_ticket: float = 0.0
    total_nc: int = 0
    avg_payment_days: int = 0
    purchase_freq: str = "A"

    if row:
        customer_name = row.customer_name.strip() if row.customer_name else "Cliente"
        total_invoices = int(row.total_invoices or 0)
        total_historic = float(row.total_historic_invoiced or 0)
        avg_ticket = round(total_historic / total_invoices, 2) if total_invoices > 0 else 0.0
        total_nc = int(row.total_nc or 0)
        avg_payment_days = int(round(float(row.avg_payment_days or 0)))

        # Map average weeks/month → purchase frequency tier
        avg_weeks = float(row.avg_weeks_per_month or 0)
        rounded_weeks = int(round(avg_weeks))
        if rounded_weeks >= 4:
            purchase_freq = "AAAA"
        elif rounded_weeks == 3:
            purchase_freq = "AAA"
        elif rounded_weeks == 2:
            purchase_freq = "AA"
        elif rounded_weeks >= 1:
            purchase_freq = "A"
        else:
            # No invoice history — fall back to stored salesperson_type classification
            raw_type = row.salesperson_type or "A"
            purchase_freq = raw_type if raw_type in ("A", "AA", "AAA", "AAAA") else "A"

    # -------------------------------------------------------------------------
    # QUERY 2 (of 2): Ordered recent transactions (requires LIMIT + row iteration)
    # -------------------------------------------------------------------------
    tx_query = text("""
        SELECT id_invoice, date, total_amount
        FROM invoices
        WHERE client_identification = :id
        ORDER BY date DESC NULLS LAST, due_date DESC NULLS LAST
        LIMIT 5
    """)
    tx_rows = db.execute(tx_query, {"id": identification}).fetchall()

    recent_transactions: List[CustomerTransaction] = []
    for tx in tx_rows:
        code_str = str(tx.id_invoice or "")
        if not code_str.startswith("#"):
            code_str = f"#{code_str}"
        recent_transactions.append(
            CustomerTransaction(
                code=code_str,
                date=format_spanish_date(tx.date),
                price=float(tx.total_amount or 0),
            )
        )

    return CustomerSummary(
        identification=identification,
        name=customer_name,
        kpis=CustomerKPIs(
            total_historic_invoiced=total_historic,
            total_nc_associated=total_nc,
            average_ticket=avg_ticket,
        ),
        commercial_behavior=CustomerCommercialBehavior(
            average_payment_days=avg_payment_days,
            purchase_frequency=purchase_freq,
        ),
        recent_transactions=recent_transactions,
    )
