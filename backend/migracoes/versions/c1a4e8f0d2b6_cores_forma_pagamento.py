"""Cores da forma de pagamento

Revision ID: c1a4e8f0d2b6
Revises: b7e2f4a91c3d

Tabela nova, sem dado nenhum ainda: a cor de cada forma de pagamento passa a
morar no banco (não mais em `localStorage` do navegador) para aparecer igual
no celular e no PC. Uma linha só existe aqui depois que a usuária troca a cor
pela primeira vez; até lá o padrão vem do código (ver
`app/routers/preferencias.py`).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a4e8f0d2b6"
down_revision: Union[str, None] = "b7e2f4a91c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORMAS_PAGAMENTO = ("CREDITO", "DEBITO", "PIX", "DINHEIRO")


def upgrade() -> None:
    op.create_table(
        "cores_forma_pagamento",
        sa.Column(
            "forma_pagamento",
            sa.Enum(*FORMAS_PAGAMENTO, name="formapagamento", native_enum=False),
            nullable=False,
        ),
        sa.Column("cor", sa.String(length=7), nullable=False),
        sa.PrimaryKeyConstraint("forma_pagamento"),
    )


def downgrade() -> None:
    op.drop_table("cores_forma_pagamento")
