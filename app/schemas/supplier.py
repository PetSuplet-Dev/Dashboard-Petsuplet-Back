from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class SupplierRankingItem(BaseModel):
    ranking: int
    id: Optional[str] = None
    nit: Optional[str] = None
    supplier_name: str
    address: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    landline_phone: Optional[str] = None
    website: Optional[str] = None
    annual_revenue: float = 0.0
    current_year_sales_percentage: float = 0.0
    total_products_sold: float = 0.0
    top_products: List[str] = []

    model_config = ConfigDict(from_attributes=True)


class SupplierKPIs(BaseModel):
    annual_revenue: float = 0.0
    current_year_sales_percentage: float = 0.0


class SupplierCommercialBehavior(BaseModel):
    total_products_sold: float = 0.0


class SupplierSummary(BaseModel):
    id: Optional[str] = None
    supplier_name: str
    nit: Optional[str] = None
    kpis: SupplierKPIs
    commercial_behavior: SupplierCommercialBehavior
    top_products: List[str] = []


class SupplierRankingResponse(BaseModel):
    total_records: int
    items: List[SupplierRankingItem]
