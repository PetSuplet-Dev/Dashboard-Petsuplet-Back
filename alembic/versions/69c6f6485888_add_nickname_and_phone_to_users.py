"""add_nickname_and_phone_to_users

Revision ID: 69c6f6485888
Revises: 5b7976dd79c8
Create Date: 2026-10-28 11:08:46.866347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69c6f6485888'
down_revision: Union[str, Sequence[str], None] = '5b7976dd79c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add nickname and phone columns to users table."""
    op.add_column('users', sa.Column('nickname', sa.String(length=100), nullable=True), if_not_exists=True)
    op.add_column('users', sa.Column('phone', sa.String(length=50), nullable=True), if_not_exists=True)


def downgrade() -> None:
    """Downgrade schema: remove nickname and phone columns from users table."""
    op.drop_column('users', 'phone')
    op.drop_column('users', 'nickname')
