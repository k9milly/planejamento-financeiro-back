"""Separa o dinheiro em contas

Revision ID: d985a2a63508
Revises: e5f1f124bb69

Antes desta migração o sistema conhecia uma conta só. Transferir dinheiro entre
duas contas suas virava uma saída em uma e uma entrada na outra, inflando os
dois totais do mês sem que nada tivesse sido gasto ou recebido.

A migração é escrita à mão, e não pelo autogenerate, por três motivos:

1. `lancamentos.conta_id` é obrigatória, e as linhas existentes precisam de um
   valor antes da restrição valer. Aqui elas são preenchidas antes.
2. Os saldos de abertura viviam em `anos` e precisam virar linhas de
   `saldos_iniciais` — o autogenerate simplesmente apagaria as colunas.
3. Uma conta precisa existir antes de qualquer lançamento apontar para ela.

**Toda a movimentação existente é atribuída ao Mercado Pago**, conforme a
origem real do histórico importado da planilha. O Nubank é criado zerado.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d985a2a63508"
down_revision: Union[str, None] = "e5f1f124bb69"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTA_PADRAO = "Mercado Pago"
CONTA_SECUNDARIA = "Nubank"

TIPOS = (
    "ENTRADA", "SAIDA", "GUARDADO", "RETIRADO",
    "RENDIMENTO", "PERDA", "TRANSFERENCIA",
)


def upgrade() -> None:
    conexao = op.get_bind()

    # 1. Tabela de contas, e as duas contas reais.
    contas = op.create_table(
        "contas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("cor", sa.String(length=7), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome"),
    )
    op.bulk_insert(
        contas,
        [
            {"id": 1, "nome": CONTA_PADRAO, "cor": "#00b1ea", "ordem": 0,
             "ativa": True},
            {"id": 2, "nome": CONTA_SECUNDARIA, "cor": "#820ad1", "ordem": 1,
             "ativa": True},
        ],
    )
    conta_padrao_id = 1

    # 2. Aberturas por ano e conta.
    op.create_table(
        "saldos_iniciais",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ano_id", sa.Integer(), nullable=False),
        sa.Column("conta_id", sa.Integer(), nullable=False),
        sa.Column("saldo", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("guardado", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["ano_id"], ["anos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conta_id"], ["contas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ano_id", "conta_id", name="uq_saldo_inicial_ano_conta"),
    )
    with op.batch_alter_table("saldos_iniciais") as batch:
        batch.create_index("ix_saldos_iniciais_ano_id", ["ano_id"])
        batch.create_index("ix_saldos_iniciais_conta_id", ["conta_id"])

    # 3. Leva as aberturas que estavam em `anos` para a conta padrão, antes de
    #    as colunas serem removidas.
    conexao.execute(
        sa.text(
            "INSERT INTO saldos_iniciais (ano_id, conta_id, saldo, guardado) "
            "SELECT id, :conta, saldo_inicial_conta, saldo_inicial_guardado "
            "FROM anos"
        ),
        {"conta": conta_padrao_id},
    )

    with op.batch_alter_table("anos") as batch:
        batch.drop_column("saldo_inicial_conta")
        batch.drop_column("saldo_inicial_guardado")

    # 4. Lançamentos ganham conta. A coluna nasce aceitando nulo para as linhas
    #    existentes serem preenchidas; só então vira obrigatória.
    with op.batch_alter_table("lancamentos") as batch:
        batch.add_column(sa.Column("conta_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("conta_destino_id", sa.Integer(), nullable=True))

    conexao.execute(
        sa.text("UPDATE lancamentos SET conta_id = :conta WHERE conta_id IS NULL"),
        {"conta": conta_padrao_id},
    )

    with op.batch_alter_table("lancamentos") as batch:
        batch.alter_column("conta_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column(
            "tipo",
            existing_type=sa.VARCHAR(length=10),
            type_=sa.Enum(*TIPOS, name="tipolancamento", native_enum=False),
            existing_nullable=False,
        )
        batch.create_index("ix_lancamentos_conta_id", ["conta_id"])
        batch.create_foreign_key(
            "fk_lancamentos_conta", "contas", ["conta_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_lancamentos_conta_destino", "contas", ["conta_destino_id"], ["id"],
            ondelete="RESTRICT",
        )

    # 5. Mesmo tratamento para os gastos fixos.
    with op.batch_alter_table("gastos_fixos") as batch:
        batch.add_column(sa.Column("conta_id", sa.Integer(), nullable=True))

    conexao.execute(
        sa.text("UPDATE gastos_fixos SET conta_id = :conta WHERE conta_id IS NULL"),
        {"conta": conta_padrao_id},
    )

    with op.batch_alter_table("gastos_fixos") as batch:
        batch.alter_column("conta_id", existing_type=sa.Integer(), nullable=False)
        batch.create_index("ix_gastos_fixos_conta_id", ["conta_id"])
        batch.create_foreign_key(
            "fk_gastos_fixos_conta", "contas", ["conta_id"], ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    conexao = op.get_bind()

    with op.batch_alter_table("gastos_fixos") as batch:
        batch.drop_constraint("fk_gastos_fixos_conta", type_="foreignkey")
        batch.drop_index("ix_gastos_fixos_conta_id")
        batch.drop_column("conta_id")

    with op.batch_alter_table("lancamentos") as batch:
        batch.drop_constraint("fk_lancamentos_conta_destino", type_="foreignkey")
        batch.drop_constraint("fk_lancamentos_conta", type_="foreignkey")
        batch.drop_index("ix_lancamentos_conta_id")
        batch.drop_column("conta_destino_id")
        batch.drop_column("conta_id")

    # Devolve as aberturas para `anos`, somando as contas: a informação de qual
    # conta tinha o quê se perde, porque o modelo antigo não sabia representá-la.
    with op.batch_alter_table("anos") as batch:
        batch.add_column(
            sa.Column(
                "saldo_inicial_conta", sa.Numeric(12, 2),
                nullable=False, server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "saldo_inicial_guardado", sa.Numeric(12, 2),
                nullable=False, server_default="0",
            )
        )

    conexao.execute(
        sa.text(
            "UPDATE anos SET "
            "  saldo_inicial_conta = COALESCE(("
            "    SELECT SUM(saldo) FROM saldos_iniciais WHERE ano_id = anos.id), 0),"
            "  saldo_inicial_guardado = COALESCE(("
            "    SELECT SUM(guardado) FROM saldos_iniciais WHERE ano_id = anos.id), 0)"
        )
    )

    with op.batch_alter_table("saldos_iniciais") as batch:
        batch.drop_index("ix_saldos_iniciais_conta_id")
        batch.drop_index("ix_saldos_iniciais_ano_id")

    op.drop_table("saldos_iniciais")
    op.drop_table("contas")
