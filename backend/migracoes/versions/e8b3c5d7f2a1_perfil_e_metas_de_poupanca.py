"""Perfil (nome, alertas por e-mail) e metas de poupança

Revision ID: e8b3c5d7f2a1
Revises: d4f7a2c9e1b8

ADR-06. Aditiva: duas colunas novas em `usuarios` e uma tabela nova. Nada
muda de comportamento para quem já existe — `nome` nasce nulo (a pessoa
continua identificada pelo e-mail) e `alertas_email_ativo` nasce desligado.

Os alertas de vencimento **não** ganham tabela: são calculados sob demanda a
partir de `GastoFixo.dia_vencimento`, `Conta.dia_vencimento_fatura` e do
status pago/pendente que já vem de existir ou não o lançamento do mês.
Persistir alerta obrigaria a manter essa cópia em dia a cada pagamento, e ela
sairia errada no primeiro esquecimento.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8b3c5d7f2a1"
down_revision: Union[str, None] = "d4f7a2c9e1b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIPOS_META = ("MENSAL", "PRAZO")


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(sa.Column("nome", sa.String(length=120), nullable=True))
        batch.add_column(
            sa.Column(
                "alertas_email_ativo",
                sa.Boolean(),
                nullable=False,
                # `sa.false()`, e não `text("0")`: o SQLite aceita 0 como
                # booleano, o Postgres recusa ("is of type boolean but default
                # expression is of type integer") e derruba a migração. O
                # construto do SQLAlchemy é traduzido por dialeto — vira `0`
                # aqui e `false` lá.
                server_default=sa.false(),
            )
        )

    op.create_table(
        "metas_poupanca",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(*TIPOS_META, name="tipometapoupanca", native_enum=False),
            nullable=False,
        ),
        sa.Column("valor_alvo", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("data_alvo", sa.Date(), nullable=True),
        sa.Column(
            "criada_em", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("valor_alvo > 0", name="ck_meta_valor_positivo"),
        sa.CheckConstraint(
            "(tipo = 'PRAZO' AND data_alvo IS NOT NULL) OR "
            "(tipo = 'MENSAL' AND data_alvo IS NULL)",
            name="ck_meta_data_alvo_coerente",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metas_poupanca_tipo"), "metas_poupanca", ["tipo"])


def downgrade() -> None:
    op.drop_index(op.f("ix_metas_poupanca_tipo"), table_name="metas_poupanca")
    op.drop_table("metas_poupanca")

    with op.batch_alter_table("usuarios") as batch:
        batch.drop_column("alertas_email_ativo")
        batch.drop_column("nome")
