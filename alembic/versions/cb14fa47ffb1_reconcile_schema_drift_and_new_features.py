"""reconcile_schema_drift_and_new_features

Revision ID: cb14fa47ffb1
Revises: cd23d15d884d
Create Date: 2026-10-05 11:15:22.748150

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb14fa47ffb1'
down_revision: Union[str, Sequence[str], None] = 'cd23d15d884d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add missing indexes to customers and remove redundant unique constraint on invoices."""
    op.create_index(op.f('ix_customers_identification'), 'customers', ['identification'], unique=False)
    op.create_index(op.f('ix_customers_name'), 'customers', ['name'], unique=False)
    op.drop_constraint(op.f('unique_id_alegra'), 'invoices', type_='unique')


def downgrade() -> None:
    """Downgrade schema: restore unique constraint on invoices and remove customer indexes."""
    op.create_unique_constraint(op.f('unique_id_alegra'), 'invoices', ['id_alegra'])
    op.drop_index(op.f('ix_customers_name'), table_name='customers')
    op.drop_index(op.f('ix_customers_identification'), table_name='customers')
