"""create_missing_financial_agent_totp_and_metric_tables

Revision ID: 5b7976dd79c8
Revises: cb14fa47ffb1
Create Date: 2026-10-05 13:28:26.902496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5b7976dd79c8'
down_revision: Union[str, Sequence[str], None] = 'cb14fa47ffb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create financial agent tables, add user TOTP columns and customer metric columns."""
    # 1. Financial Agent Tables: conversations
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), server_default='Nueva Conversación', nullable=False),
        sa.Column('selected_db', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint(
            "selected_db IN ('invoices', 'credit_notes', 'invoice_reconciliations')",
            name='chk_conversation_selected_db'
        ),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True
    )
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False, if_not_exists=True)

    # 2. Financial Agent Tables: messages
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('has_artifact', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name='chk_message_role'
        ),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True
    )

    # 3. Financial Agent Tables: canvas_artifacts
    op.create_table(
        'canvas_artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint(
            "type IN ('chart', 'table', 'pdf_preview', 'dashboard_mix')",
            name='chk_canvas_artifact_type'
        ),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id'),
        if_not_exists=True
    )

    # 4. Users Table: TOTP columns
    op.add_column('users', sa.Column('totp_secret', sa.String(), nullable=True), if_not_exists=True)
    op.add_column('users', sa.Column('is_totp_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=True), if_not_exists=True)

    # 5. Customers Table: Calculated metrics fields
    op.add_column('customers', sa.Column('product_quantity', sa.Numeric(precision=14, scale=2), server_default=sa.text('0.0'), nullable=True), if_not_exists=True)
    op.add_column('customers', sa.Column('sales_before_tax', sa.Numeric(precision=18, scale=2), server_default=sa.text('0.0'), nullable=True), if_not_exists=True)
    op.add_column('customers', sa.Column('sales_after_tax', sa.Numeric(precision=18, scale=2), server_default=sa.text('0.0'), nullable=True), if_not_exists=True)
    op.add_column('customers', sa.Column('total_invoices', sa.Integer(), server_default=sa.text('0'), nullable=True), if_not_exists=True)
    op.add_column('customers', sa.Column('total_credit_notes', sa.Integer(), server_default=sa.text('0'), nullable=True), if_not_exists=True)


def downgrade() -> None:
    """Downgrade schema: remove customer metrics, user TOTP columns, and financial agent tables."""
    # Drop customer metrics
    op.drop_column('customers', 'total_credit_notes')
    op.drop_column('customers', 'total_invoices')
    op.drop_column('customers', 'sales_after_tax')
    op.drop_column('customers', 'sales_before_tax')
    op.drop_column('customers', 'product_quantity')

    # Drop user TOTP columns
    op.drop_column('users', 'is_totp_enabled')
    op.drop_column('users', 'totp_secret')

    # Drop financial agent tables
    op.drop_table('canvas_artifacts', if_exists=True)
    op.drop_table('messages', if_exists=True)
    op.drop_index(op.f('ix_conversations_user_id'), table_name='conversations', if_exists=True)
    op.drop_table('conversations', if_exists=True)
