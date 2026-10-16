"""use bigint for telegram ids

Revision ID: 7d8acbc8da85
Revises: 62701a6ca6ee
Create Date: 2026-10-16 13:37:45.359581

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d8acbc8da85'
down_revision: Union[str, Sequence[str], None] = '62701a6ca6ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TABLE ONLY public.payments DROP CONSTRAINT payments_users_telegram_id_fk;"
    )
    op.execute(
        "ALTER TABLE ONLY public.tasks DROP CONSTRAINT tasks_users_telegram_id_fk;"
    )
    op.execute(
        "ALTER TABLE ONLY public.users DROP CONSTRAINT users_telegram_id_key;"
    )
    op.execute("ALTER TABLE public.users ALTER COLUMN telegram_id TYPE bigint USING telegram_id::bigint;")
    op.execute("ALTER TABLE public.payments ALTER COLUMN user_id TYPE bigint USING user_id::bigint;")
    op.execute("ALTER TABLE public.tasks ALTER COLUMN telegram_id TYPE bigint USING telegram_id::bigint;")
    op.execute(
        "ALTER TABLE ONLY public.users ADD CONSTRAINT users_telegram_id_key UNIQUE (telegram_id);"
    )
    op.execute(
        "ALTER TABLE ONLY public.payments ADD CONSTRAINT payments_users_telegram_id_fk FOREIGN KEY (user_id) REFERENCES public.users(telegram_id);"
    )
    op.execute(
        "ALTER TABLE ONLY public.tasks ADD CONSTRAINT tasks_users_telegram_id_fk FOREIGN KEY (telegram_id) REFERENCES public.users(telegram_id);"
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "ALTER TABLE ONLY public.payments DROP CONSTRAINT payments_users_telegram_id_fk;"
    )
    op.execute(
        "ALTER TABLE ONLY public.tasks DROP CONSTRAINT tasks_users_telegram_id_fk;"
    )
    op.execute(
        "ALTER TABLE ONLY public.users DROP CONSTRAINT users_telegram_id_key;"
    )

    op.execute("ALTER TABLE public.users ALTER COLUMN telegram_id TYPE int USING telegram_id::int;")
    op.execute("ALTER TABLE public.payments ALTER COLUMN user_id TYPE int USING user_id::int;")
    op.execute("ALTER TABLE public.tasks ALTER COLUMN telegram_id TYPE int USING telegram_id::int;")
    op.execute(
        "ALTER TABLE ONLY public.users ADD CONSTRAINT users_telegram_id_key UNIQUE (telegram_id);"
    )
    op.execute(
        "ALTER TABLE ONLY public.payments ADD CONSTRAINT payments_users_telegram_id_fk FOREIGN KEY (user_id) REFERENCES public.users(telegram_id);"
    )
    op.execute(
        "ALTER TABLE ONLY public.tasks ADD CONSTRAINT tasks_users_telegram_id_fk FOREIGN KEY (telegram_id) REFERENCES public.users(telegram_id);"
    )
