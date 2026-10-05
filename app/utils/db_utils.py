from typing import Any, Dict, List, Optional, Sequence, Union
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError


def bulk_upsert_objects(
    db: Session,
    model: Any,
    records: Optional[List[Union[Dict[str, Any], Any]]] = None,
    index_elements: Optional[Sequence[str]] = None,
    batch_size: int = 1000,
    unique_id_attribute: Optional[str] = None,
) -> int:
    """
    Performs atomic batch upsert operations using PostgreSQL's native ON CONFLICT DO UPDATE mechanics.

    Args:
        db: The active SQLAlchemy database session.
        model: The SQLAlchemy model class (e.g., Invoice, CreditNote) or legacy list of objects.
        records: List of dictionaries (or model instances) to upsert.
        index_elements: Unique constraint or primary key column names for conflict target (e.g., ["id_alegra"]).
        batch_size: Number of records to insert per batch statement (default: 1000).
        unique_id_attribute: Legacy parameter for backward compatibility.

    Returns:
        int: Total number of records processed.
    """
    # Handle legacy call signature: (db, objects, unique_id_attribute="...")
    if isinstance(model, list):
        records = model
        if not records:
            return 0
        model = records[0].__class__
        if unique_id_attribute and not index_elements:
            index_elements = [unique_id_attribute]

    if not records:
        return 0

    if not index_elements:
        if unique_id_attribute:
            index_elements = [unique_id_attribute]
        else:
            raise ValueError("index_elements must be provided for PostgreSQL ON CONFLICT upsert.")

    # Convert records into clean dictionaries
    dict_records: List[Dict[str, Any]] = []
    for item in records:
        if isinstance(item, dict):
            dict_records.append(item)
        elif hasattr(item, "__table__"):
            dict_records.append({
                c.name: getattr(item, c.name)
                for c in item.__table__.columns
                if getattr(item, c.name, None) is not None
            })
        else:
            dict_records.append(dict(item))

    # In-memory deduplication of incoming payload by index_elements.
    # In PostgreSQL, a single INSERT with duplicate conflict keys in VALUES raises:
    # "ON CONFLICT DO UPDATE command cannot affect row a second time".
    deduped_map: Dict[tuple, Dict[str, Any]] = {}
    for rec in dict_records:
        key = tuple(rec.get(col) for col in index_elements)
        if any(k is None for k in key):
            continue
        deduped_map[key] = rec

    deduped_records = list(deduped_map.values())
    total_records = len(deduped_records)
    if total_records == 0:
        return 0

    processed_count = 0
    try:
        # Process in batches to prevent exceeding SQL statement size limits
        for i in range(0, total_records, batch_size):
            chunk = deduped_records[i : i + batch_size]
            if not chunk:
                continue

            stmt = insert(model).values(chunk)

            # Automatically map non-primary key fields using stmt.excluded for the set_ dictionary
            update_dict = {
                c.name: c for c in stmt.excluded if not c.primary_key
            }

            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_=update_dict,
            )

            db.execute(upsert_stmt)
            db.commit()
            processed_count += len(chunk)
            print(
                f"Successfully upserted batch of {len(chunk)} records into {getattr(model, '__tablename__', model)} "
                f"({processed_count}/{total_records})."
            )

        return processed_count

    except SQLAlchemyError as e:
        db.rollback()
        table_name = getattr(model, "__tablename__", str(model))
        print(f"Error during bulk upsert on {table_name}: {e}. Batch rolled back.")
        raise
