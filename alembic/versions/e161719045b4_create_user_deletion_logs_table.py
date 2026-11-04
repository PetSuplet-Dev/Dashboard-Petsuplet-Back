"""create_user_deletion_logs_table

Revision ID: e161719045b4
Revises: 69c6f6485888
Create Date: 2026-10-28 11:38:34.831044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e161719045b4'
down_revision: Union[str, Sequence[str], None] = '69c6f6485888'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create user_deletion_logs table."""
    op.create_table(
        'user_deletion_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('original_id_user', sa.Integer(), nullable=False),
        sa.Column('name_user', sa.String(length=100), nullable=False),
        sa.Column('lastname_user', sa.String(length=150), nullable=False),
        sa.Column('email_user', sa.String(length=150), nullable=False),
        sa.Column('rol_user', sa.String(length=50), nullable=False),
        sa.Column('nickname', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('deleted_by', sa.String(length=150), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )
    op.create_index(op.f('ix_user_deletion_logs_email_user'), 'user_deletion_logs', ['email_user'], unique=False, if_not_exists=True)


def downgrade() -> None:
    """Downgrade schema: drop user_deletion_logs table."""
    op.drop_index(op.f('ix_user_deletion_logs_email_user'), table_name='user_deletion_logs')
    op.drop_table('user_deletion_logs')
