'''
SQLAlchemy model for Supplier Directory.
'''
import uuid
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database.session import Base

class SupplierDirectory(Base):
    '''Supplier Directory model'''
    __tablename__ = "supplier_directory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_name = Column(String(255), index=True)
    nit = Column(String(50), index=True)
    address = Column(Text)
    status = Column(String(50))
    city = Column(String(100))
    department = Column(String(100))
    website = Column(String(255))
    mobile_phone = Column(String(50))
    landline_phone = Column(String(50))
    annual_revenue = Column(String(100))
    current_year_sales_percentage = Column(String(100))
    total_products_sold = Column(String(100))
    top_products = Column(Text)
    created_at = Column(DateTime)
