from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.supplier import (
    SupplierRankingItem,
    SupplierRankingResponse,
    SupplierSummary,
)
from app.services.supplier_service import (
    get_supplier_ranking_data,
    get_supplier_summary_by_id_or_nit,
    recalculate_supplier_metrics_sync,
)
from app.api.dependencies import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/ranking", response_model=SupplierRankingResponse)
def get_suppliers_ranking(
    start_date: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Término de búsqueda"),
    limit: Optional[int] = Query(100, description="Cantidad máxima de registros"),
    offset: int = Query(0, description="Desplazamiento para paginación"),
    db: Session = Depends(get_db),
):
    """
    Retorna el ranking de proveedores desde supplier_directory,
    asociado a sus métricas de ventas y productos.
    """
    total_records, items_dict = get_supplier_ranking_data(
        session=db,
        start_date=start_date,
        end_date=end_date,
        search=search,
        limit=limit,
        offset=offset,
    )

    items = [SupplierRankingItem(**item) for item in items_dict]
    return SupplierRankingResponse(total_records=total_records, items=items)


@router.post("/recalculate-metrics")
def recalculate_supplier_metrics(db: Session = Depends(get_db)):
    """
    Recalcula y actualiza en la tabla supplier_directory:
    annual_revenue, current_year_sales_percentage, total_products_sold, top_products
    haciendo el cruce de invoices y products.
    """
    count = recalculate_supplier_metrics_sync(db)
    return {
        "status": "success",
        "message": f"Métricas de proveedores actualizadas exitosamente ({count} registros actualizados)",
    }


@router.get("/{id_or_nit}/summary", response_model=SupplierSummary)
def get_supplier_summary(id_or_nit: str, db: Session = Depends(get_db)):
    """
    Obtiene el resumen detallado de un proveedor para el panel lateral (Aside).
    """
    summary = get_supplier_summary_by_id_or_nit(session=db, supplier_key=id_or_nit)
    if not summary:
        raise HTTPException(
            status_code=404, detail="Proveedor no encontrado en el directorio"
        )
    return SupplierSummary(**summary)
