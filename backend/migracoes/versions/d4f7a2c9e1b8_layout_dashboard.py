"""Layout do painel por usuário

Revision ID: d4f7a2c9e1b8
Revises: c1a4e8f0d2b6

Fase 7 do `docs/PLANO-BACKEND.md`. Uma coluna só, nullable: `NULL` significa
"nunca arrumou o painel", e o frontend usa a disposição padrão dele. Aditiva —
nenhum usuário existente muda de comportamento.

O conteúdo é JSON serializado pelo frontend, guardado como texto opaco: o
backend não valida o formato de propósito (ver `Usuario.layout_dashboard`).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f7a2c9e1b8"
down_revision: Union[str, None] = "c1a4e8f0d2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(sa.Column("layout_dashboard", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as batch:
        batch.drop_column("layout_dashboard")
