import uuid
from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database.session import Base


class InvoiceReconciliation(Base):
    __tablename__ = "invoice_reconciliations"

    unique_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_alegra_invoice = Column(Integer, nullable=True)
    id_alegra_credit_note = Column(Integer, nullable=True)
    id_inv = Column(String(50), index=True, nullable=True)
    id_cn = Column(String(50), index=True, nullable=True)
    name_client = Column(String(150), nullable=True)
    matched_amount = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_id_invoice_id_credit_note", "id_inv", "id_cn"),)
