'''
SQLAlchemy model for Customers.
'''
import uuid
from sqlalchemy import Column, String, DateTime, Text, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.database.session import Base

class Customer(Base):
    '''Customer model'''
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identification = Column(String(100), index=True)
    name = Column(String(255), index=True)
    drivin_customer = Column(String(255))
    address = Column(Text)
    phone = Column(String(100))
    email = Column(String(255))
    latitude = Column(String(100))
    longitude = Column(String(100))
    city = Column(String(100))
    locality = Column(String(100))
    neighborhood = Column(String(100))
    geographic_zone = Column(String(100))
    reporting_salesperson = Column(String(150))
    reporting_salesperson_details = Column(String(255))
    segment_number = Column(String(50))
    segment = Column(String(100))
    database_source = Column(String(100))
    salesperson = Column(String(150))
    route_index = Column(String(100))
    salesperson_type = Column(String(100))
    route = Column(String(100))
    zones = Column(String(100))
    assigned_salesperson = Column(String(150))
    modified_by = Column(String(150))
    comment = Column(Text)
    last_comment_date = Column(String(50))
    alegra_creation_date = Column(String(50))
    address_code = Column(String(100))
    felipe_comment = Column(Text)
    created_at = Column(DateTime(timezone=True))

    # Métricas cruzadas desde Invoices y Credit Notes
    product_quantity = Column(Numeric(14, 2), default=0.0)
    sales_before_tax = Column(Numeric(18, 2), default=0.0)
    sales_after_tax = Column(Numeric(18, 2), default=0.0)
    total_invoices = Column(Integer, default=0)
    total_credit_notes = Column(Integer, default=0)
