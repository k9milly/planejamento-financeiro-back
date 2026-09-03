"""Caixinhas por conta, vinculáveis a metas

Revision ID: f2c9d6b4a708
Revises: e8b3c5d7f2a1

ADR-10. Aditiva: uma tabela nova e duas colunas nulláveis em `lancamentos`.
Nenhum lançamento existente muda de comportamento — sem `caixinha_id`, o
guardado continua entrando na conta sem rótulo, exatamente como antes.

`TipoLancamento` ganha o valor `transferencia_caixinha`, e **isso exige mexer
na coluna**. O enum é mapeado com `native_enum=False`, então `lancamentos.tipo`
é um VARCHAR dimensionado pelo nome mais longo do enum: a migração
`d985a2a63508` a deixou em `VARCHAR(13)`, do tamanho de `TRANSFERENCIA`. O
nome novo, `TRANSFERENCIA_CAIXINHA`, tem 22 caracteres.

O SQLite ignora o tamanho declarado e aceitaria a gravação; o Postgres recusa
com *value too long for type character varying(13)*. Sem o `alter_column`
abaixo, a suíte passaria inteira aqui e a primeira transferência entre
caixinhas falharia só em produção — o mesmo formato do incidente do default
booleano.

Não há CHECK a recriar: `create_constraint` fica desligado por padrão desde a
SQLAlchemy 1.4. Se isso mudar, esta migração precisa passar a recriá-lo.

Não existe coluna `saldo` na caixinha, de propósito: o saldo é derivado de
`saldo_inicial` mais os lançamentos que apontam para ela (ver
`app/services/caixinhas.py`). Uma coluna precisaria ser mantida em dia a cada
criação, edição e exclusão de lançamento.

Cuidado herdado da migração anterior: defaults booleanos usam `sa.true()`, e
não `sa.text("1")` — o SQLite aceita o número, o Postgres recusa e derruba o
deploy.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2c9d6b4a708"
down_revision: Union[str, None] = "e8b3c5d7f2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Os nomes (não os valores) do enum, que é como o SQLAlchemy grava a coluna.
TIPOS_ANTES = (
    "ENTRADA", "SAIDA", "GUARDADO", "RETIRADO",
    "RENDIMENTO", "PERDA", "TRANSFERENCIA",
)
TIPOS_DEPOIS = TIPOS_ANTES + ("TRANSFERENCIA_CAIXINHA",)


def upgrade() -> None:
    op.create_table(
        "caixinhas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conta_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("meta_id", sa.Integer(), nullable=True),
        sa.Column(
            "saldo_inicial",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "criada_em", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("saldo_inicial >= 0", name="ck_caixinha_saldo_inicial"),
        # RESTRICT na conta: apagar a conta deixaria a divisão da reserva
        # apontando para o vazio. SET NULL na meta: desativar uma meta não deve
        # levar a caixinha junto — ela continua guardando dinheiro, só deixa de
        # alimentar um objetivo.
        sa.ForeignKeyConstraint(["conta_id"], ["contas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["meta_id"], ["metas_poupanca.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_caixinhas_conta_id"), "caixinhas", ["conta_id"])
    op.create_index(op.f("ix_caixinhas_meta_id"), "caixinhas", ["meta_id"])

    with op.batch_alter_table("lancamentos") as batch:
        # Alarga a coluna do enum: `TRANSFERENCIA_CAIXINHA` não cabe nos 13
        # caracteres que `TRANSFERENCIA` deixou. Ver o cabeçalho deste arquivo.
        batch.alter_column(
            "tipo",
            existing_type=sa.Enum(
                *TIPOS_ANTES, name="tipolancamento", native_enum=False
            ),
            type_=sa.Enum(*TIPOS_DEPOIS, name="tipolancamento", native_enum=False),
            existing_nullable=False,
        )
        batch.add_column(sa.Column("caixinha_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("caixinha_destino_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_lancamento_caixinha",
            "caixinhas",
            ["caixinha_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_lancamento_caixinha_destino",
            "caixinhas",
            ["caixinha_destino_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        op.f("ix_lancamentos_caixinha_id"), "lancamentos", ["caixinha_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lancamentos_caixinha_id"), table_name="lancamentos")
    with op.batch_alter_table("lancamentos") as batch:
        batch.drop_constraint("fk_lancamento_caixinha_destino", type_="foreignkey")
        batch.drop_constraint("fk_lancamento_caixinha", type_="foreignkey")
        batch.drop_column("caixinha_destino_id")
        batch.drop_column("caixinha_id")
        # Só cabe estreitar de volta porque `downgrade` pressupõe que nenhum
        # lançamento do tipo novo sobreviva — os que existissem apontariam para
        # caixinhas, e a tabela delas some logo abaixo.
        batch.alter_column(
            "tipo",
            existing_type=sa.Enum(
                *TIPOS_DEPOIS, name="tipolancamento", native_enum=False
            ),
            type_=sa.Enum(*TIPOS_ANTES, name="tipolancamento", native_enum=False),
            existing_nullable=False,
        )

    op.drop_index(op.f("ix_caixinhas_meta_id"), table_name="caixinhas")
    op.drop_index(op.f("ix_caixinhas_conta_id"), table_name="caixinhas")
    op.drop_table("caixinhas")
