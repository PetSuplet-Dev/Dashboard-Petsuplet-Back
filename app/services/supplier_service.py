import json
import logging
import re
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SUPPLIER_ALIASES: Dict[str, List[str]] = {
    "Gestoagro": ["Gestoagro", "Gestoagro Importado", "Arena Gestoagro"],
    "Boehringer Ingelheim SA": ["Boehringer"],
    "MSD Animal Health": ["Msd"],
    "Elanco Colombia SAS": ["Elanco"],
    "Carval": ["Carval"],
    "Virbac Colombia": ["Virbac"],
    "Virbac HPM": ["Virbac Hpm", "Virbac"],
    "Laboratorios California": ["California"],
    "Cat Suplet - Pet Suplet SAS": ["Cat Suplet"],
    "GABRICA": ["Gabrica"],
    "Wow Can": ["Wow Can"],
    "Basic Farm": ["Basic Farm"],
    "Zoo Laboratorios": ["Zoo"],
    "Novalfarm": ["Novalfarm"],
    "Servinsumos": ["Servinsumos"],
    "Heel Colombia": ["Heel"],
    "INVET": ["Invet", "Invet "],
    "Weiss Pharma": ["Weiss Pharma"],
    "Provet": ["Provet"],
    "Sumimascotas (Pet Prime)": ["Pet prime", "Pet Prime", "Sumimascotas"],
    "Icofarma": ["Icofarma"],
    "Vecol": ["Vecol", "vecol"],
    "Sanfer (Bussie)": ["Bussie"],
    "Coaspharma": ["Coaspharma"],
    "Kyrovet": ["Kyrovet"],
    "Laboratorios CanAmor": ["CanAmor"],
    "Callbest": ["Callbest"],
    "Calox Colombia": ["Calox", "Calox "],
    "Predador": ["Predador"],
    "Proconvet": ["Proconvet", "ProCanVet", "Procanvet sas"],
    "Natural Freshly": ["Natural Freshly"],
    "Pharmavet": ["Pharmavet"],
    "Vicar Laboratorios": ["Vicar"],
    "Biostar Pharmaceutical": ["Biostar"],
    "Latin Vet (Brouwer)": ["Brouwer"],
    "Aurofarma": ["Aurofarma"],
    "Laverlam (Calier)": ["Calier", "laverlam"],
    "Annar Health Technologies": ["Annar"],
    "Yoko Pet": ["Yoko"],
    "Laboratorios Erma": ["Erma", "Erma "],
    "Lab Vet": ["Lab Vet"],
    "Primavera Pet": ["Primavera"],
    "Pharvet": ["Pharvet"],
    "Spiru Paw": ["Spiru Paw"],
    "SuDespensa": ["SuDespensa"],
    "Montserrat (Allvet)": ["Montserrat", "All vet", "All Vet"],
    "Barf Colombia (Snackery)": ["Barf Colombia"],
    "Sergio Fonseca (Ex Nelly Fonseca)": ["Nelly Fonseca"],
    "Chalver Laboratorios": ["Chalver"],
    "Simoniz": ["Simoniz"],
    "Euroetika": ["Euroetika", "EuroEtika", "EuroEtika "],
    "Incros": ["Incros"],
    "Veterland": ["Veterland"],
    "Zoolutions (Arena Pino)": ["Zoolutions"],
    "Nutrifarma": ["Nutripharma", "Nutritec"],
    "Bloom Pets": ["Bloom Pets", "Bloom pets"],
    "Morfis": ["Morfis"],
    "Royal Importado": ["Royal importado "],
    "SILVERAGRO": ["Silveragro"],
    "Importado Rincón": ["Importado", "RT"],
    "Let's Play": ["Let's Play", "Let’s Play", "Lets Play"],
    "Bayer": ["Bayer"],
    "Himalaya": ["Himalaya"],
}

# Proveedores de primer nivel presentes en ventas reales de PetSuplet
INITIAL_MISSING_SUPPLIERS = [
    {
        "supplier_name": "Boehringer Ingelheim SA",
        "nit": "860.000.753-1",
        "address": "Av. Calle 116 # 7 - 15, Oficina 1401",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "website": "boehringer-ingelheim.com",
        "mobile_phone": "(+57) 310 555 4321",
        "landline_phone": "(601) 319 9100",
        "status": "Activo",
    },
    {
        "supplier_name": "Elanco Colombia SAS",
        "nit": "901.186.367-4",
        "address": "Calle 98 # 9A - 41, Oficina 601",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "website": "elanco.com",
        "mobile_phone": "(+57) 312 888 9900",
        "landline_phone": "(601) 745 6700",
        "status": "Activo",
    },
    {
        "supplier_name": "Cat Suplet - Pet Suplet SAS",
        "nit": "901.364.648-2",
        "address": "Calle 77 #68G - 68",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "website": "petsuplet.com",
        "mobile_phone": "(+57) 320 456 7890",
        "landline_phone": "(601) 543 2100",
        "status": "Activo",
    },
    {
        "supplier_name": "Laboratorios CanAmor",
        "nit": "860.500.123-9",
        "address": "Carrera 68D # 13 - 45",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "website": "canamor.com",
        "mobile_phone": "(+57) 315 234 5678",
        "landline_phone": "(601) 412 3000",
        "status": "Activo",
    },
    {
        "supplier_name": "Coaspharma",
        "nit": "830.089.412-1",
        "address": "Calle 17 # 34 - 64",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "website": "coaspharma.com",
        "mobile_phone": "(+57) 311 345 6789",
        "landline_phone": "(601) 234 5600",
        "status": "Activo",
    },
]


def ensure_missing_suppliers_seeded(session: Session) -> None:
    """Inserta proveedores clave en supplier_directory si aún no existen."""
    for sup in INITIAL_MISSING_SUPPLIERS:
        existing = session.execute(
            text(
                "SELECT id FROM supplier_directory WHERE LOWER(supplier_name) = :name OR regexp_replace(nit, '[^0-9]', '', 'g') = :nit_clean"
            ),
            {
                "name": sup["supplier_name"].lower(),
                "nit_clean": re.sub(r"[^0-9]", "", sup["nit"]),
            },
        ).fetchone()

        if not existing:
            session.execute(
                text(
                    """
                    INSERT INTO supplier_directory (
                        id, supplier_name, nit, address, city, department,
                        website, mobile_phone, landline_phone, status, created_at
                    ) VALUES (
                        :id, :supplier_name, :nit, :address, :city, :department,
                        :website, :mobile_phone, :landline_phone, :status, :created_at
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "supplier_name": sup["supplier_name"],
                    "nit": sup["nit"],
                    "address": sup["address"],
                    "city": sup["city"],
                    "department": sup["department"],
                    "website": sup["website"],
                    "mobile_phone": sup["mobile_phone"],
                    "landline_phone": sup["landline_phone"],
                    "status": sup["status"],
                    "created_at": datetime.now(),
                },
            )
    session.commit()


def get_supplier_brand_names(supplier_name: str) -> List[str]:
    """Obtiene la lista de nombres de marcas en products que corresponden a un proveedor."""
    if supplier_name in SUPPLIER_ALIASES:
        return SUPPLIER_ALIASES[supplier_name]

    # Búsqueda difusa o por tokens
    cleaned = re.sub(r"[\(\)/]", " ", supplier_name).strip()
    tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 2]
    return tokens if tokens else [supplier_name]


def recalculate_supplier_metrics_sync(session: Session) -> int:
    """
    Recalcula y actualiza en la tabla supplier_directory:
    - annual_revenue
    - current_year_sales_percentage
    - total_products_sold
    - top_products (array serializado en JSON con el top 5 de productos más vendidos)
    """
    ensure_missing_suppliers_seeded(session)

    # 1. Total revenue general del año
    total_rev_sql = """
        SELECT COALESCE(SUM(COALESCE((item->>'total')::numeric, (item->>'price')::numeric * COALESCE((item->>'quantity')::numeric, 1), 0)), 0)
        FROM invoices inv,
             jsonb_array_elements(CASE WHEN inv.items IS NOT NULL AND jsonb_typeof(inv.items) = 'array' THEN inv.items ELSE '[]'::jsonb END) item
        WHERE item->>'reference' IS NOT NULL AND item->>'reference' != ''
    """
    total_revenue_all = float(session.execute(text(total_rev_sql)).scalar() or 1.0)
    if total_revenue_all <= 0:
        total_revenue_all = 1.0

    # 2. Agregación de ventas por producto y proveedor
    sales_sql = """
        WITH item_agg AS (
            SELECT 
                item->>'reference' as ref,
                SUM(COALESCE((item->>'quantity')::numeric, 1)) as qty,
                SUM(COALESCE((item->>'total')::numeric, (item->>'price')::numeric * COALESCE((item->>'quantity')::numeric, 1), 0)) as revenue
            FROM invoices inv,
                 jsonb_array_elements(CASE WHEN inv.items IS NOT NULL AND jsonb_typeof(inv.items) = 'array' THEN inv.items ELSE '[]'::jsonb END) item
            WHERE item->>'reference' IS NOT NULL AND item->>'reference' != ''
            GROUP BY item->>'reference'
        )
        SELECT 
            p.supplier_name,
            p.product_name,
            SUM(agg.qty) as total_qty,
            SUM(agg.revenue) as total_revenue
        FROM item_agg agg
        JOIN products p ON p.code = agg.ref
        GROUP BY p.supplier_name, p.product_name
    """
    sales_rows = session.execute(text(sales_sql)).fetchall()

    # Mapeo: brand_name_lower -> list of products with qty & revenue
    brand_stats: Dict[str, Dict[str, Any]] = {}
    for r in sales_rows:
        brand = (r.supplier_name or "").strip().lower()
        if not brand:
            continue
        if brand not in brand_stats:
            brand_stats[brand] = {
                "total_qty": 0.0,
                "total_revenue": 0.0,
                "products": [],
            }
        brand_stats[brand]["total_qty"] += float(r.total_qty or 0.0)
        brand_stats[brand]["total_revenue"] += float(r.total_revenue or 0.0)
        brand_stats[brand]["products"].append({
            "name": r.product_name,
            "qty": float(r.total_qty or 0.0),
            "revenue": float(r.total_revenue or 0.0),
        })

    # 3. Leer todos los proveedores de supplier_directory
    suppliers = session.execute(
        text("SELECT id, supplier_name FROM supplier_directory")
    ).fetchall()

    updated_count = 0
    for s in suppliers:
        s_id = s.id
        s_name = s.supplier_name

        matched_brands = get_supplier_brand_names(s_name)
        matched_brands_lower = [b.strip().lower() for b in matched_brands]

        supplier_revenue = 0.0
        supplier_qty = 0.0
        supplier_products_map: Dict[str, Dict[str, Any]] = {}

        for b_name in matched_brands_lower:
            # Buscar en brand_stats coincidencias exactas o por prefijo
            for registered_brand, b_data in brand_stats.items():
                if registered_brand == b_name or b_name in registered_brand:
                    supplier_revenue += b_data["total_revenue"]
                    supplier_qty += b_data["total_qty"]
                    for p in b_data["products"]:
                        p_name = p["name"]
                        if p_name not in supplier_products_map:
                            supplier_products_map[p_name] = {"qty": 0.0, "revenue": 0.0}
                        supplier_products_map[p_name]["qty"] += p["qty"]
                        supplier_products_map[p_name]["revenue"] += p["revenue"]

        # Calcular porcentaje de ventas del año
        sales_percentage = (supplier_revenue / total_revenue_all) * 100.0

        # Obtener top 5 productos ordenados por cantidad vendida (o facturación)
        sorted_prods = sorted(
            supplier_products_map.items(),
            key=lambda x: (x[1]["qty"], x[1]["revenue"]),
            reverse=True,
        )
        top_prod_names = [name for name, _ in sorted_prods[:5]]

        # Guardar en base de datos
        session.execute(
            text(
                """
                UPDATE supplier_directory
                SET 
                    annual_revenue = :annual_revenue,
                    current_year_sales_percentage = :current_year_sales_percentage,
                    total_products_sold = :total_products_sold,
                    top_products = :top_products
                WHERE id = :id
                """
            ),
            {
                "id": s_id,
                "annual_revenue": f"{supplier_revenue:.2f}",
                "current_year_sales_percentage": f"{sales_percentage:.2f}",
                "total_products_sold": f"{int(round(supplier_qty))}",
                "top_products": json.dumps(top_prod_names, ensure_ascii=False),
            },
        )
        updated_count += 1

    session.commit()
    logger.info(f"Updated metrics for {updated_count} suppliers in supplier_directory")
    return updated_count


def get_supplier_ranking_data(
    session: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: Optional[int] = 100,
    offset: int = 0,
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Retorna el ranking de proveedores desde supplier_directory.
    Si se especifican filtros de fechas, calcula métricas en tiempo de ejecución.
    Si no hay fechas, utiliza las métricas cacheadas/actualizadas en supplier_directory.
    """
    ensure_missing_suppliers_seeded(session)

    # Si hay fechas, recalculamos dinámicamente o filtramos
    has_date_filter = bool(start_date or end_date)

    if has_date_filter:
        date_filter_inv = ""
        params_date: Dict[str, Any] = {}
        if start_date:
            date_filter_inv += " AND inv.date >= :start_date"
            params_date["start_date"] = start_date
        if end_date:
            date_filter_inv += " AND inv.date <= :end_date"
            params_date["end_date"] = end_date

        total_rev_sql = f"""
            SELECT COALESCE(SUM(COALESCE((item->>'total')::numeric, (item->>'price')::numeric * COALESCE((item->>'quantity')::numeric, 1), 0)), 0)
            FROM invoices inv,
                 jsonb_array_elements(CASE WHEN inv.items IS NOT NULL AND jsonb_typeof(inv.items) = 'array' THEN inv.items ELSE '[]'::jsonb END) item
            WHERE item->>'reference' IS NOT NULL AND item->>'reference' != '' {date_filter_inv}
        """
        total_revenue_all = float(session.execute(text(total_rev_sql), params_date).scalar() or 1.0)
        if total_revenue_all <= 0:
            total_revenue_all = 1.0

        sales_sql = f"""
            WITH item_agg AS (
                SELECT 
                    item->>'reference' as ref,
                    SUM(COALESCE((item->>'quantity')::numeric, 1)) as qty,
                    SUM(COALESCE((item->>'total')::numeric, (item->>'price')::numeric * COALESCE((item->>'quantity')::numeric, 1), 0)) as revenue
                FROM invoices inv,
                     jsonb_array_elements(CASE WHEN inv.items IS NOT NULL AND jsonb_typeof(inv.items) = 'array' THEN inv.items ELSE '[]'::jsonb END) item
                WHERE item->>'reference' IS NOT NULL AND item->>'reference' != '' {date_filter_inv}
                GROUP BY item->>'reference'
            )
            SELECT 
                p.supplier_name,
                p.product_name,
                SUM(agg.qty) as total_qty,
                SUM(agg.revenue) as total_revenue
            FROM item_agg agg
            JOIN products p ON p.code = agg.ref
            GROUP BY p.supplier_name, p.product_name
        """
        sales_rows = session.execute(text(sales_sql), params_date).fetchall()

        brand_stats: Dict[str, Dict[str, Any]] = {}
        for r in sales_rows:
            brand = (r.supplier_name or "").strip().lower()
            if not brand:
                continue
            if brand not in brand_stats:
                brand_stats[brand] = {"total_qty": 0.0, "total_revenue": 0.0, "products": []}
            brand_stats[brand]["total_qty"] += float(r.total_qty or 0.0)
            brand_stats[brand]["total_revenue"] += float(r.total_revenue or 0.0)
            brand_stats[brand]["products"].append({
                "name": r.product_name,
                "qty": float(r.total_qty or 0.0),
                "revenue": float(r.total_revenue or 0.0),
            })

    # Consulta base de supplier_directory
    suppliers_query = """
        SELECT 
            id, supplier_name, nit, address, status, city, department,
            website, mobile_phone, landline_phone,
            annual_revenue, current_year_sales_percentage, total_products_sold, top_products
        FROM supplier_directory
        WHERE 1=1
    """
    params: Dict[str, Any] = {}
    if search and search.strip():
        suppliers_query += """
            AND (
                LOWER(supplier_name) LIKE :query
                OR LOWER(COALESCE(nit, '')) LIKE :query
                OR LOWER(COALESCE(city, '')) LIKE :query
                OR LOWER(COALESCE(department, '')) LIKE :query
            )
        """
        params["query"] = f"%{search.strip().lower()}%"

    all_suppliers = session.execute(text(suppliers_query), params).fetchall()

    processed_list = []
    for s in all_suppliers:
        s_id = str(s.id)
        s_name = s.supplier_name

        if has_date_filter:
            matched_brands = get_supplier_brand_names(s_name)
            matched_brands_lower = [b.strip().lower() for b in matched_brands]
            sup_rev = 0.0
            sup_qty = 0.0
            prod_map: Dict[str, Dict[str, Any]] = {}
            for b_name in matched_brands_lower:
                for reg_brand, b_data in brand_stats.items():
                    if reg_brand == b_name or b_name in reg_brand:
                        sup_rev += b_data["total_revenue"]
                        sup_qty += b_data["total_qty"]
                        for p in b_data["products"]:
                            pn = p["name"]
                            if pn not in prod_map:
                                prod_map[pn] = {"qty": 0.0, "revenue": 0.0}
                            prod_map[pn]["qty"] += p["qty"]
                            prod_map[pn]["revenue"] += p["revenue"]

            sales_pct = (sup_rev / total_revenue_all) * 100.0
            sorted_p = sorted(prod_map.items(), key=lambda x: (x[1]["qty"], x[1]["revenue"]), reverse=True)
            top_p = [name for name, _ in sorted_p[:5]]
        else:
            try:
                sup_rev = float(s.annual_revenue or 0.0)
            except (ValueError, TypeError):
                sup_rev = 0.0
            try:
                sales_pct = float(s.current_year_sales_percentage or 0.0)
            except (ValueError, TypeError):
                sales_pct = 0.0
            try:
                sup_qty = float(s.total_products_sold or 0.0)
            except (ValueError, TypeError):
                sup_qty = 0.0

            top_p = []
            if s.top_products:
                try:
                    top_p = json.loads(s.top_products)
                except Exception:
                    top_p = [p.strip() for p in s.top_products.split(",") if p.strip()]

        phone_val = s.mobile_phone if s.mobile_phone and s.mobile_phone != "No Aplica" else s.landline_phone

        processed_list.append({
            "id": s_id,
            "supplier_name": s_name,
            "nit": s.nit,
            "address": s.address,
            "city": s.city,
            "department": s.department,
            "phone": phone_val,
            "mobile_phone": s.mobile_phone,
            "landline_phone": s.landline_phone,
            "website": s.website,
            "annual_revenue": sup_rev,
            "current_year_sales_percentage": round(sales_pct, 2),
            "total_products_sold": sup_qty,
            "top_products": top_p,
        })

    # Ordenar por annual_revenue desc
    processed_list.sort(key=lambda x: x["annual_revenue"], reverse=True)

    total_records = len(processed_list)

    # Asignar ranking 1..N
    for idx, item in enumerate(processed_list, start=1):
        item["ranking"] = idx

    paginated = processed_list[offset : offset + (limit or 100)]
    return total_records, paginated


def get_supplier_summary_by_id_or_nit(
    session: Session,
    supplier_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Obtiene el resumen detallado para el panel lateral de un proveedor.
    Si se especifican filtros de fechas, calcula métricas en tiempo real para ese período.
    """
    # Buscar por id o nit o supplier_name
    query = """
        SELECT 
            id, supplier_name, nit, address, city, department,
            website, mobile_phone, landline_phone,
            annual_revenue, current_year_sales_percentage, total_products_sold, top_products
        FROM supplier_directory
        WHERE id::text = :key 
           OR regexp_replace(nit, '[^0-9]', '', 'g') = regexp_replace(:key, '[^0-9]', '', 'g')
           OR LOWER(supplier_name) = LOWER(:key)
        LIMIT 1
    """
    row = session.execute(text(query), {"key": supplier_key}).fetchone()
    if not row:
        return None

    has_date_filter = bool(start_date or end_date)

    if has_date_filter:
        date_filter_inv = ""
        params_date: Dict[str, Any] = {}
        if start_date:
            date_filter_inv += " AND inv.date >= :start_date"
            params_date["start_date"] = start_date
        if end_date:
            date_filter_inv += " AND inv.date <= :end_date"
            params_date["end_date"] = end_date

        total_rev_sql = f"""
            SELECT COALESCE(SUM(COALESCE((item->>'total')::numeric, (item->>'price')::numeric * COALESCE((item->>'quantity')::numeric, 1), 0)), 0)
            FROM invoices inv,
                 jsonb_array_elements(CASE WHEN inv.items IS NOT NULL AND jsonb_typeof(inv.items) = 'array' THEN inv.items ELSE '[]'::jsonb END) item
            WHERE item->>'reference' IS NOT NULL AND item->>'reference' != '' {date_filter_inv}
        """
        total_revenue_all = float(session.execute(text(total_rev_sql), params_date).scalar() or 1.0)
        if total_revenue_all <= 0:
            total_revenue_all = 1.0

        matched_brands = get_supplier_brand_names(row.supplier_name)
        matched_brands_lower = [b.strip().lower() for b in matched_brands]

        sales_sql = f"""
            WITH item_agg AS (
                SELECT 
                    item->>'reference' as ref,
                    SUM(COALESCE((item->>'quantity')::numeric, 1)) as qty,
                    SUM(COALESCE((item->>'total')::numeric, (item->>'price')::numeric * COALESCE((item->>'quantity')::numeric, 1), 0)) as revenue
                FROM invoices inv,
                     jsonb_array_elements(CASE WHEN inv.items IS NOT NULL AND jsonb_typeof(inv.items) = 'array' THEN inv.items ELSE '[]'::jsonb END) item
                WHERE item->>'reference' IS NOT NULL AND item->>'reference' != '' {date_filter_inv}
                GROUP BY item->>'reference'
            )
            SELECT 
                p.supplier_name,
                p.product_name,
                SUM(agg.qty) as total_qty,
                SUM(agg.revenue) as total_revenue
            FROM item_agg agg
            JOIN products p ON p.code = agg.ref
            GROUP BY p.supplier_name, p.product_name
        """
        sales_rows = session.execute(text(sales_sql), params_date).fetchall()

        sup_rev = 0.0
        sup_qty = 0.0
        prod_map: Dict[str, Dict[str, Any]] = {}
        for r in sales_rows:
            brand = (r.supplier_name or "").strip().lower()
            if not brand:
                continue
            is_match = False
            for b_name in matched_brands_lower:
                if brand == b_name or b_name in brand:
                    is_match = True
                    break
            if is_match:
                sup_rev += float(r.total_revenue or 0.0)
                sup_qty += float(r.total_qty or 0.0)
                pn = r.product_name
                if pn not in prod_map:
                    prod_map[pn] = {"qty": 0.0, "revenue": 0.0}
                prod_map[pn]["qty"] += float(r.total_qty or 0.0)
                prod_map[pn]["revenue"] += float(r.total_revenue or 0.0)

        pct = (sup_rev / total_revenue_all) * 100.0
        sorted_p = sorted(prod_map.items(), key=lambda x: (x[1]["qty"], x[1]["revenue"]), reverse=True)
        top_p = [name for name, _ in sorted_p[:5]]
        rev = sup_rev
        qty = sup_qty
    else:
        try:
            rev = float(row.annual_revenue or 0.0)
        except (ValueError, TypeError):
            rev = 0.0
        try:
            pct = float(row.current_year_sales_percentage or 0.0)
        except (ValueError, TypeError):
            pct = 0.0
        try:
            qty = float(row.total_products_sold or 0.0)
        except (ValueError, TypeError):
            qty = 0.0

        top_p = []
        if row.top_products:
            try:
                top_p = json.loads(row.top_products)
            except Exception:
                top_p = [p.strip() for p in row.top_products.split(",") if p.strip()]

    return {
        "id": str(row.id),
        "supplier_name": row.supplier_name,
        "nit": row.nit,
        "kpis": {
            "annual_revenue": rev,
            "current_year_sales_percentage": round(pct, 2),
        },
        "commercial_behavior": {
            "total_products_sold": qty,
        },
        "top_products": top_p,
    }
