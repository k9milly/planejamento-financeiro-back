"""Forma de pagamento, cartões de crédito e fatura mensal

Revision ID: b7e2f4a91c3d
Revises: d985a2a63508

Fase 0 do plano em `docs/PLANO-IMPLEMENTACAO.md`: uma migração só, aditiva,
juntando o schema das quatro mudanças de uma vez (ver ADRs 0001-0003 e a spec
"Pagamentos e cartões" em `docs/specs/`).

Tudo aqui é nullable ou tem um default que preserva o comportamento atual:
- `contas.tipo` nasce `CORRENTE` para toda conta já existente — nenhuma delas
  vira cartão sozinha.
- `lancamentos.forma_pagamento` e `gastos_fixos.forma_pagamento` nascem nulos
  — tratados como débito em todo lugar que olha o campo (ADR-0001). Nenhum
  lançamento histórico muda de comportamento.
- `gastos_fixos.forma_pagamento` (texto livre) é renomeada para
  `forma_pagamento_legado`: continua existindo, só não é mais lida por
  nenhuma regra nova.
- `faturas_mensais` é uma tabela nova, sem dado nenhum ainda.

Não há dado a migrar: é só schema. A aplicação sobe e se comporta exatamente
como antes até que uma tela nova passe a ler os campos novos (fases 1-5).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2f4a91c3d"
down_revision: Union[str, None] = "d985a2a63508"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIPOS_CONTA = ("CORRENTE", "CARTAO_CREDITO")
FORMAS_PAGAMENTO = ("CREDITO", "DEBITO", "PIX", "DINHEIRO")
SITUACOES = ("PENDENTE", "PAGO")


def upgrade() -> None:
    with op.batch_alter_table("contas") as batch:
        batch.add_column(
            sa.Column(
                "tipo",
                sa.Enum(*TIPOS_CONTA, name="tipoconta", native_enum=False),
                nullable=False,
                server_default="CORRENTE",
            )
        )
        batch.add_column(sa.Column("dia_vencimento_fatura", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("conta_pagamento_padrao_id", sa.Integer(), nullable=True)
        )
        batch.create_check_constraint(
            "ck_conta_dia_vencimento_fatura",
            "dia_vencimento_fatura IS NULL OR dia_vencimento_fatura BETWEEN 1 AND 31",
        )
        batch.create_foreign_key(
            "fk_contas_conta_pagamento_padrao_id_contas",
            "contas",
            ["conta_pagamento_padrao_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("lancamentos") as batch:
        batch.add_column(
            sa.Column(
                "forma_pagamento",
                sa.Enum(*FORMAS_PAGAMENTO, name="formapagamento", native_enum=False),
                nullable=True,
            )
        )

    # Em dois `batch_alter_table` separados: renomear e criar uma coluna com o
    # nome antigo dela na mesma passada confunde a reconstrução de tabela do
    # SQLite (`CircularDependencyError` ao ordenar as colunas).
    with op.batch_alter_table("gastos_fixos") as batch:
        batch.alter_column("forma_pagamento", new_column_name="forma_pagamento_legado")

    with op.batch_alter_table("gastos_fixos") as batch:
        batch.add_column(
            sa.Column(
                "forma_pagamento",
                sa.Enum(*FORMAS_PAGAMENTO, name="formapagamento", native_enum=False),
                nullable=True,
            )
        )

    op.create_table(
        "faturas_mensais",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cartao_id", sa.Integer(), nullable=False),
        sa.Column("ano_id", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column(
            "situacao",
            sa.Enum(*SITUACOES, name="situacaogastofixo", native_enum=False),
            nullable=False,
            server_default="PENDENTE",
        ),
        sa.Column("lancamento_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("mes BETWEEN 1 AND 12", name="ck_fatura_mes"),
        sa.ForeignKeyConstraint(["cartao_id"], ["contas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ano_id"], ["anos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["lancamento_id"], ["lancamentos.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cartao_id", "ano_id", "mes", name="uq_fatura_cartao_ano_mes"
        ),
    )
    op.create_index(
        op.f("ix_faturas_mensais_cartao_id"), "faturas_mensais", ["cartao_id"]
    )
    op.create_index(op.f("ix_faturas_mensais_ano_id"), "faturas_mensais", ["ano_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_faturas_mensais_ano_id"), table_name="faturas_mensais")
    op.drop_index(op.f("ix_faturas_mensais_cartao_id"), table_name="faturas_mensais")
    op.drop_table("faturas_mensais")

    with op.batch_alter_table("gastos_fixos") as batch:
        batch.drop_column("forma_pagamento")

    with op.batch_alter_table("gastos_fixos") as batch:
        batch.alter_column("forma_pagamento_legado", new_column_name="forma_pagamento")

    with op.batch_alter_table("lancamentos") as batch:
        batch.drop_column("forma_pagamento")

    with op.batch_alter_table("contas") as batch:
        batch.drop_constraint(
            "fk_contas_conta_pagamento_padrao_id_contas", type_="foreignkey"
        )
        batch.drop_constraint("ck_conta_dia_vencimento_fatura", type_="check")
        batch.drop_column("conta_pagamento_padrao_id")
        batch.drop_column("dia_vencimento_fatura")
        batch.drop_column("tipo")
