from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas
from app.database.session import get_db
from app.services.reconciliation_service import (
    run_reconciliation,
    get_client_net_balances,
    DatabasePermissionDeniedError,
    ReconciliationServiceError,
)
from app.api.dependencies import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/sync", response_model=schemas.ReconciliationSyncResponse)
def sync_reconciliations(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    background: bool = Query(
        False,
        description="If true, run in background (HTTP 202). If false (default), run synchronously and return results.",
    ),
):
    """
    Trigger invoice reconciliation sync.

    - **Default (background=false)**: Runs synchronously (~1-2s) and returns
      a structured response with reconciled_count and total_records.
    - **background=true**: Starts the process in the background and returns
      HTTP 202 immediately.
    """
    if background:
        def task_wrapper():
            try:
                from app.database.session import SessionLocal
                session = SessionLocal()
                try:
                    result = run_reconciliation(session)
                    print(f"Background reconciliation complete. New records: {result}")
                finally:
                    session.close()
            except Exception as e:
                print(f"Error executing reconciliation task: {str(e)}")

        background_tasks.add_task(task_wrapper)

        total_records = db.query(models.InvoiceReconciliation).count()
        return schemas.ReconciliationSyncResponse(
            status="accepted",
            message="Reconciliation process started in the background.",
            reconciled_count=0,
            total_records=total_records,
        )

    # Synchronous execution (default)
    try:
        reconciled_count = run_reconciliation(db)
        total_records = db.query(models.InvoiceReconciliation).count()

        if reconciled_count > 0:
            message = f"Reconciliation completed successfully. {reconciled_count} new records created."
        else:
            message = "Reconciliation completed. No new records to reconcile (all pairs are up to date)."

        return schemas.ReconciliationSyncResponse(
            status="success",
            message=message,
            reconciled_count=reconciled_count,
            total_records=total_records,
        )
    except DatabasePermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ReconciliationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during reconciliation: {str(e)}",
        )


@router.get("/paired-balances", response_model=List[schemas.ClientNetBalanceResponse])
def get_paired_client_balances(db: Session = Depends(get_db)):
    """
    Consolidates and returns the net balance (Total Invoices - Total Credit Notes) 
    for contacts that have BOTH active invoices and credit notes.
    """
    try:
        return get_client_net_balances(db)
    except DatabasePermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ReconciliationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/", response_model=schemas.ReconciliationPaginatedResponse[schemas.ReconciliationResponse])
def get_reconciliations(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
):
    """
    Retrieve paginated invoice reconciliations.
    """
    try:
        skip = (page - 1) * limit
        total_records = db.query(models.InvoiceReconciliation).count()
        reconciliations = (
            db.query(models.InvoiceReconciliation)
            .offset(skip)
            .limit(limit)
            .all()
        )
        
        return {
            "total_records": total_records,
            "page": page,
            "limit": limit,
            "data": reconciliations,
        }
    except Exception as e:
        if "permission denied" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Database permission denied while querying reconciliations."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

