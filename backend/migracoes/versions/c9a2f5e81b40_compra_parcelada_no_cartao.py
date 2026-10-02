"""Compra parcelada no cartão de crédito

Revision ID: c9a2f5e81b40
Revises: b6e4f0a91d37

ADR-14. Aditiva: tabela nova e duas colunas nuláveis em `lancamentos`. Todo
lançamento que já existe nasce com as duas nulas e continua se comportando
exatamente como hoje.

Nenhum enum existente ganha valor novo, então `lancamentos.tipo` não precisa
ser alargado — o cuidado que a migração das caixinhas teve de tomar. As
parcelas são `saida` com `forma_pagamento=credito`, valores que já existiam.

`ON DELETE CASCADE` nas parcelas é intencional e diferente do `RESTRICT` usado
nas caixinhas: apagar a compra é a ação "desfazer a compra inteira", e as
parcelas só existem por causa dela.

Defaults booleanos com `sa.false()`, e não `sa.text("0")` — o SQLite aceita o
número e o Postgres derruba o deploy (ver a migração `e8b3c5d7f2a1`).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9a2f5e81b40"
down_revision: Union[str, None] = "b6e4f0a91d37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODOS_JUROS = ("VALOR", "PERCENTUAL")


def upgrade() -> None:
    op.create_table(
        "compras_parceladas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.String(length=120), nullable=False),
        sa.Column("conta_id", sa.Integer(), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=True),
        sa.Column("numero_parcelas", sa.Integer(), nullable=False),
        sa.Column(
            "tem_juros", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "modo_juros",
            sa.Enum(*MODOS_JUROS, name="modojuros", native_enum=False),
            nullable=True,
        ),
        sa.Column("taxa_juros_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("valor_parcela", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("valor_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "numero_parcelas BETWEEN 2 AND 24", name="ck_compra_parcelada_numero"
        ),
        sa.CheckConstraint("valor_parcela > 0", name="ck_compra_parcelada_valor_parcela"),
        sa.CheckConstraint("valor_total > 0", name="ck_compra_parcelada_valor_total"),
        sa.ForeignKeyConstraint(["conta_id"], ["contas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["categoria_id"], ["categorias.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_compras_parceladas_conta_id"), "compras_parceladas", ["conta_id"]
    )

    with op.batch_alter_table("lancamentos") as batch:
        batch.add_column(sa.Column("compra_parcelada_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("numero_parcela", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_lancamento_compra_parcelada",
            "compras_parceladas",
            ["compra_parcelada_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_index(
        op.f("ix_lancamentos_compra_parcelada_id"),
        "lancamentos",
        ["compra_parcelada_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_lancamentos_compra_parcelada_id"), table_name="lancamentos"
    )
    with op.batch_alter_table("lancamentos") as batch:
        batch.drop_constraint("fk_lancamento_compra_parcelada", type_="foreignkey")
        batch.drop_column("numero_parcela")
        batch.drop_column("compra_parcelada_id")

    op.drop_index(
        op.f("ix_compras_parceladas_conta_id"), table_name="compras_parceladas"
    )
    op.drop_table("compras_parceladas")
