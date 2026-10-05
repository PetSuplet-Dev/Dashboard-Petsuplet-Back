from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class CustomerRankingItem(BaseModel):
    ranking: int
    id: Optional[str] = None
    identification: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    neighborhood: Optional[str] = None
    geographic_zone: Optional[str] = None
    region: Optional[str] = None
    zone: Optional[str] = None
    reporting_salesperson: Optional[str] = None
    salesperson: Optional[str] = None
    salesperson_type: Optional[str] = None
    segment: Optional[str] = None
    product_quantity: float = 0.0
    sales_before_tax: float = 0.0
    sales_after_tax: float = 0.0
    total_invoices: int = 0
    total_credit_notes: int = 0

    model_config = ConfigDict(from_attributes=True)


class CustomerTransaction(BaseModel):
    code: str
    date: Optional[str] = None
    price: float = 0.0


class CustomerKPIs(BaseModel):
    total_historic_invoiced: float = 0.0
    total_nc_associated: int = 0
    average_ticket: float = 0.0


class CustomerCommercialBehavior(BaseModel):
    average_payment_days: int = 0
    purchase_frequency: str = "A"


class CustomerSummary(BaseModel):
    identification: str
    name: str
    kpis: CustomerKPIs
    commercial_behavior: CustomerCommercialBehavior
    recent_transactions: List[CustomerTransaction] = []


class CustomerRankingResponse(BaseModel):
    total_records: int
    items: List[CustomerRankingItem]
