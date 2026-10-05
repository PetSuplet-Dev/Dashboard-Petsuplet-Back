import re
import logging
from decimal import Decimal
from typing import List, Dict, Any, Set, Tuple, Optional
import unicodedata
from sqlalchemy.orm import Session, defer
from sqlalchemy import func, select
from sqlalchemy.sql.functions import coalesce
from sqlalchemy.exc import DBAPIError, OperationalError

from app.models.invoice import Invoice
from app.models.credit_note import CreditNote
from app.models.invoice_reconciliations import InvoiceReconciliation

logger = logging.getLogger(__name__)


class ReconciliationServiceError(Exception):
    """Base exception for reconciliation service errors."""

    pass


class DatabasePermissionDeniedError(ReconciliationServiceError):
    """Raised when the database user lacks permission for the query."""

    pass


def get_client_net_balances(db: Session) -> List[Dict[str, Any]]:
    """
    Computes aggregated total invoices, total credit notes, and Net Balance
    (Total Invoices - Total Credit Notes) per client using SQLAlchemy CTEs.

    Filters strictly for clients (Contacts) present in BOTH tables.
    """
    try:
        # CTE 1: Aggregated Invoices per Client
        invoices_cte = (
            select(
                Invoice.name_client.label("client_name"),
                func.sum(coalesce(Invoice.total_amount, 0)).label(
                    "total_invoices_amount"
                ),
                func.count(Invoice.unique_id).label("invoice_count"),
            )
            .where(Invoice.name_client.isnot(None))
            .group_by(Invoice.name_client)
            .cte("invoices_summary")
        )

        # CTE 2: Aggregated Credit Notes per Client
        credit_notes_cte = (
            select(
                CreditNote.name_client.label("client_name"),
                func.sum(coalesce(CreditNote.total_amount, 0)).label(
                    "total_credit_notes_amount"
                ),
                func.count(CreditNote.unique_id).label("credit_note_count"),
            )
            .where(CreditNote.name_client.isnot(None))
            .group_by(CreditNote.name_client)
            .cte("credit_notes_summary")
        )

        # Main Query: INNER JOIN both CTEs to find paired contacts only
        stmt = (
            select(
                invoices_cte.c.client_name,
                invoices_cte.c.total_invoices_amount,
                credit_notes_cte.c.total_credit_notes_amount,
                (
                    invoices_cte.c.total_invoices_amount
                    - credit_notes_cte.c.total_credit_notes_amount
                ).label("net_balance"),
                invoices_cte.c.invoice_count,
                credit_notes_cte.c.credit_note_count,
            )
            .select_from(invoices_cte)
            .join(
                credit_notes_cte,
                invoices_cte.c.client_name == credit_notes_cte.c.client_name,
            )
        )

        results = db.execute(stmt).all()

        return [
            {
                "client_name": row.client_name,
                "total_invoices_amount": Decimal(str(row.total_invoices_amount)),
                "total_credit_notes_amount": Decimal(
                    str(row.total_credit_notes_amount)
                ),
                "net_balance": Decimal(str(row.net_balance)),
                "invoice_count": row.invoice_count,
                "credit_note_count": row.credit_note_count,
            }
            for row in results
        ]

    except (OperationalError, DBAPIError) as e:
        orig_cause = getattr(e, "orig", None)
        sqlstate = getattr(orig_cause, "sqlstate", None) or getattr(e, "code", None)

        if sqlstate == "42501" or "permission denied" in str(e).lower():
            raise DatabasePermissionDeniedError(
                "Database error: Insufficient permissions to execute matching query."
            ) from e
        raise ReconciliationServiceError(
            f"Database query execution failed: {str(e)}"
        ) from e


def _normalize_name(name: str) -> str:
    """
    Normalizes a client name for comparison:
    lowercase, stripped, ASCII-only, multiple whitespace collapsed.
    """
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("utf-8")
    return re.sub(r"\s+", " ", name.lower()).strip()


def _clients_match(inv: Invoice, cn: CreditNote) -> bool:
    """
    Validates whether an invoice and credit note belong to the same client.

    Uses a multi-tier strategy:
      1. Exact normalized name match (covers most cases).
      2. client_id match (Alegra internal ID — same entity, different name/branch).
      3. client_identification match (NIT/CC — same legal entity).
      4. Substring containment (handles branch/sede suffixes).
    """
    inv_name = _normalize_name(inv.name_client)
    cn_name = _normalize_name(cn.name_client)

    # Tier 1: Exact normalized name
    if inv_name and cn_name and inv_name == cn_name:
        return True

    # Tier 2: client_id (Alegra internal ID)
    if inv.client_id and cn.client_id and str(inv.client_id) == str(cn.client_id):
        return True

    # Tier 3: client_identification (NIT/CC)
    if (
        inv.client_identification
        and cn.client_identification
        and str(inv.client_identification) == str(cn.client_identification)
    ):
        return True

    # Tier 4: Substring containment (branch/sede suffixes)
    if inv_name and cn_name and (inv_name in cn_name or cn_name in inv_name):
        return True

    return False


def run_reconciliation(db: Session, batch_size: int = 1000) -> int:
    """
    Cross-matches invoices and credit notes using multi-variable validation.

    Optimized for high data volumes:
      1. Loads all credit notes with associated_invoices (defers heavy JSONB columns).
      2. Collects all needed invoice id_alegra values and loads them in batches.
      3. Validates each (invoice, credit_note) pair against existing reconciliations.
      4. Multi-tier client matching: name, client_id, NIT/CC, substring.
      5. Fallback amount: uses cn.total_applied or cn.total_amount when assoc amount is 0.
      6. Commits new reconciliations in batches to control memory.
    """
    try:
        logger.info("Starting reconciliation process...")

        # 1. Load existing reconciliation pairs in chunks for O(1) duplicate check
        existing_pairs: Set[Tuple[Optional[str], Optional[str]]] = set()
        recon_offset = 0
        recon_chunk_size = 5000
        while True:
            recon_chunk = (
                db.query(InvoiceReconciliation.id_inv, InvoiceReconciliation.id_cn)
                .filter(
                    InvoiceReconciliation.id_inv.isnot(None),
                    InvoiceReconciliation.id_cn.isnot(None),
                )
                .offset(recon_offset)
                .limit(recon_chunk_size)
                .all()
            )
            if not recon_chunk:
                break
            existing_pairs.update(recon_chunk)
            recon_offset += len(recon_chunk)

        logger.info(f"Existing reconciliation pairs: {len(existing_pairs)}")

        # 2. Iterate credit notes in chunks to prevent loading entire table into memory
        total_reconciled = 0
        batch_reconciliations: List[InvoiceReconciliation] = []
        cn_offset = 0
        cn_fetch_limit = 1000

        while True:
            credit_notes = (
                db.query(CreditNote)
                .options(defer(CreditNote.items), defer(CreditNote.cufe))
                .filter(CreditNote.associated_invoices.isnot(None))
                .order_by(CreditNote.unique_id)
                .offset(cn_offset)
                .limit(cn_fetch_limit)
                .all()
            )
            if not credit_notes:
                break
            cn_offset += len(credit_notes)

            # 3. Collect needed invoice id_alegra from associated_invoices in this chunk
            needed_alegra_ids: Set[int] = set()
            candidate_cns: List[CreditNote] = []
            for cn in credit_notes:
                if not isinstance(cn.associated_invoices, list):
                    continue
                for assoc in cn.associated_invoices:
                    if isinstance(assoc, dict):
                        assoc_id = assoc.get("id")
                        if assoc_id:
                            try:
                                needed_alegra_ids.add(int(assoc_id))
                            except (ValueError, TypeError):
                                continue
                candidate_cns.append(cn)

            if not candidate_cns or not needed_alegra_ids:
                continue

            # 4. Load required invoices in batches for this credit note chunk
            invoices_by_alegra: Dict[int, Invoice] = {}
            needed_ids_list = list(needed_alegra_ids)
            for i in range(0, len(needed_ids_list), 1000):
                chunk_ids = needed_ids_list[i : i + 1000]
                invs = (
                    db.query(Invoice)
                    .options(defer(Invoice.items), defer(Invoice.cufe))
                    .filter(Invoice.id_alegra.in_(chunk_ids))
                    .all()
                )
                for inv in invs:
                    if inv.id_alegra:
                        invoices_by_alegra[inv.id_alegra] = inv

            # 5. Match credit notes to invoices
            for cn in candidate_cns:
                for assoc in cn.associated_invoices:
                    if not isinstance(assoc, dict):
                        continue
                    assoc_id = assoc.get("id")
                    if not assoc_id:
                        continue

                    try:
                        assoc_alegra_id = int(assoc_id)
                    except (ValueError, TypeError):
                        continue

                    # Find the invoice via O(1) dictionary lookup
                    inv = invoices_by_alegra.get(assoc_alegra_id)
                    if not inv:
                        continue

                    # Check if reconciliation already exists via O(1) set lookup
                    pair_key = (inv.id_invoice, cn.id_credit_note)
                    if pair_key in existing_pairs:
                        continue

                    # VALIDATION — Client match (multi-tier)
                    if not _clients_match(inv, cn):
                        continue

                    # VALIDATION — Date coherence (CN date >= Invoice date)
                    if inv.date and cn.date and cn.date < inv.date:
                        continue

                    # VALIDATION — Amount reasonableness with fallback
                    try:
                        assoc_amount = Decimal(str(assoc.get("amount", 0)))
                    except Exception:
                        assoc_amount = Decimal(0)

                    # Fallback: use cn.total_applied or cn.total_amount when assoc amount is 0
                    if assoc_amount <= 0:
                        fallback = cn.total_applied or cn.total_amount
                        if fallback:
                            assoc_amount = Decimal(str(fallback))

                    if assoc_amount <= 0:
                        continue

                    # Cap amount at invoice total to avoid over-matching
                    if inv.total_amount and assoc_amount > inv.total_amount:
                        assoc_amount = Decimal(str(inv.total_amount))

                    # All validations passed — create reconciliation
                    recon = InvoiceReconciliation(
                        id_alegra_invoice=inv.id_alegra,
                        id_alegra_credit_note=cn.id_alegra,
                        id_inv=inv.id_invoice,
                        id_cn=cn.id_credit_note,
                        name_client=inv.name_client,
                        matched_amount=assoc_amount,
                    )
                    batch_reconciliations.append(recon)
                    existing_pairs.add(pair_key)

                    # Batch commit if threshold reached
                    if len(batch_reconciliations) >= batch_size:
                        db.add_all(batch_reconciliations)
                        db.commit()
                        total_reconciled += len(batch_reconciliations)
                        logger.info(f"Committed batch of {len(batch_reconciliations)} reconciliations")
                        batch_reconciliations.clear()

        # Commit any remaining pending reconciliations
        if batch_reconciliations:
            db.add_all(batch_reconciliations)
            db.commit()
            total_reconciled += len(batch_reconciliations)
            batch_reconciliations.clear()

        logger.info(f"Reconciliation complete. New records: {total_reconciled}")
        return total_reconciled

    except (OperationalError, DBAPIError) as e:
        db.rollback()
        orig_cause = getattr(e, "orig", None)
        sqlstate = getattr(orig_cause, "sqlstate", None) or getattr(e, "code", None)

        if sqlstate == "42501" or "permission denied" in str(e).lower():
            raise DatabasePermissionDeniedError(
                "Database error: Insufficient write/read permissions on reconciliation tables."
            ) from e
        raise ReconciliationServiceError(
            f"Reconciliation commit failed: {str(e)}"
        ) from e


