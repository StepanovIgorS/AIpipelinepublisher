"""use TEXT on error in tasks

Revision ID: c19cb156a808
Revises: 7d8acbc8da85
Create Date: 2026-10-16 14:02:19.732333

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c19cb156a808'
down_revision: Union[str, Sequence[str], None] = '7d8acbc8da85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE public.tasks ALTER COLUMN error TYPE TEXT USING error::TEXT;")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE public.tasks ALTER COLUMN error TYPE VARCHAR(255) USING error::VARCHAR(255);")
