# pyrefly: ignore [missing-import]
from fastapi import APIRouter

from app.api.routes import (
    invoices,
    credit_notes,
    invoice_reconciliations,
    users,
    financial_agent,
    totp,
    customers,
)

api_router = APIRouter()

# Registrar los enrutadores individuales de cada recurso
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(
    credit_notes.router, prefix="/credit-notes", tags=["credit-notes"]
)
api_router.include_router(
    invoice_reconciliations.router,
    prefix="/invoice-reconciliations",
    tags=["invoice-reconciliations"],
)
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(financial_agent.router)
api_router.include_router(totp.router, prefix="/totp", tags=["totp"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])

