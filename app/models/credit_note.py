'''
SQLAlchemy model for Credit Notes.
'''
import uuid
from sqlalchemy import Column, Integer, String, Date, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database.session import Base

class CreditNote(Base):
    '''CreditNote model'''
    __tablename__ = "credit_notes"

    unique_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_alegra = Column(Integer, unique=True, nullable=False, index=True)
    id_credit_note = Column(String, index=True, nullable=False)
    id_invoice = Column(String, index=True, nullable=True)
    date = Column(Date, index=True, nullable=False)
    invoice_date = Column(Date, index=True, nullable=True)
    time_only = Column(String)
    status = Column(String)
    type = Column(String)
    client_id = Column(String)
    name_client = Column(String)
    client_identification = Column(String, index=True)
    warehouse_name = Column(String)
    associated_invoices = Column(JSONB)
    subtotal = Column(Numeric)
    discount = Column(Numeric)
    tax = Column(Numeric)
    total_amount = Column(Numeric)
    total_applied = Column(Numeric)
    balance = Column(Numeric)
    cufe = Column(Text)
    items = Column(JSONB)
