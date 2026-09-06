"""Orçamento por categoria: limite mensal e preferência de exibição

Revision ID: a4d1e7b09c52
Revises: f2c9d6b4a708

ADR-11, que reverte o ADR-0007. Aditiva e pequena: uma coluna nullable em
`categorias` e uma booleana em `usuarios`. Nada muda de comportamento para
quem já existe — categoria sem limite continua sendo categoria normal, e a
preferência nasce ligada.

Nenhuma migração de dados é necessária: `limite_mensal` nasce nulo (que é o
estado "sem orçamento") e `mostrar_orcamento_categoria` nasce `true` pelo
`server_default`, inclusive para as linhas que já estão no banco.

Dois cuidados herdados de migrações anteriores deste projeto:

* o default booleano usa `sa.true()`, e **não** `sa.text("1")` — o SQLite
  aceita o número, o Postgres recusa ("is of type boolean but default
  expression is of type integer") e derruba o deploy em crash-loop;
* o `CHECK` do limite trata `NULL` explicitamente. Em SQL, `NULL > 0` não é
  falso, é desconhecido — e uma restrição desconhecida passa —, mas escrever
  a intenção evita que alguém a "simplifique" depois para `limite_mensal > 0`
  achando que é a mesma coisa em todo dialeto.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4d1e7b09c52"
down_revision: Union[str, None] = "f2c9d6b4a708"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("categorias") as batch:
        batch.add_column(
            sa.Column("limite_mensal", sa.Numeric(precision=12, scale=2), nullable=True)
        )
        batch.create_check_constraint(
            "ck_categoria_limite_positivo",
            "limite_mensal IS NULL OR limite_mensal > 0",
        )

    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(
            sa.Column(
                "mostrar_orcamento_categoria",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as batch:
        batch.drop_column("mostrar_orcamento_categoria")

    with op.batch_alter_table("categorias") as batch:
        batch.drop_constraint("ck_categoria_limite_positivo", type_="check")
        batch.drop_column("limite_mensal")
