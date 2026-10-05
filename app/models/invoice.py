'''
SQLAlchemy model for Invoices.
'''
import uuid
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database.session import Base

class Invoice(Base):
    '''Invoice model'''
    __tablename__ = "invoices"

    unique_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_alegra = Column(Integer, unique=True, nullable=False, index=True)
    id_invoice = Column(String, index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    due_date = Column(Date)
    date_time = Column(DateTime)
    status = Column(String)
    payment_form = Column(String)
    term = Column(String)
    client_id = Column(String)
    name_client = Column(String)
    client_identification = Column(String, index=True)
    warehouse_id = Column(String)
    warehouse_name = Column(String)
    seller_name = Column(String)
    subtotal = Column(Numeric)
    discount = Column(Numeric)
    tax = Column(Numeric)
    total_amount = Column(Numeric)
    total_paid = Column(Numeric)
    balance = Column(Numeric)
    cufe = Column(Text)
    legal_status = Column(String)
    items = Column(JSONB)
