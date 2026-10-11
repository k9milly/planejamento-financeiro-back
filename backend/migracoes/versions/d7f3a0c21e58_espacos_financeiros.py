"""Espaços financeiros e isolamento de dados

Revision ID: d7f3a0c21e58
Revises: c9a2f5e81b40

ADR-15. É a migração mais arriscada do projeto até aqui: toda tabela de
dinheiro ganha dono, e errar aqui significa dado de uma família aparecendo
para outra.

O que ela faz, em uma transação só:

1. Cria `espacos` e `membros_espaco`.
2. Se já existe usuário no banco, cria o espaço dele e o vincula como dono.
3. Acrescenta `espaco_id` NOT NULL nas catorze tabelas de dinheiro,
   preenchendo as linhas que já existem com esse espaço.
4. Troca cinco restrições de unicidade que eram globais por versões por
   espaço.
5. Aponta `usuarios.espaco_atual_id` para o espaço criado.

## Por que a coluna entra em três passos

`ADD COLUMN NOT NULL` sem default falha em tabela com linhas. Então: entra
nulável, as linhas existentes são preenchidas, e só então vira obrigatória.
Dar um `server_default` seria mais curto e pior — ficaria um default
permanente dizendo que toda linha nova pertence ao espaço 1, que é
exatamente o engano que o isolamento existe para impedir.

## Por que as unicidades precisam mudar

`anos.ano`, `contas.nome`, `categorias.nome` e `regras_categorizacao.padrao`
eram únicos no sistema inteiro. Com espaços, isso impediria dois espaços de
terem "2026", "Nubank" ou "Alimentação" cada um — e o próprio critério de
aceite do ADR-15 manda criar exatamente isso. `cores_forma_pagamento` era
pior: a forma de pagamento **era** a chave primária, então o primeiro espaço
a escolher uma cor de crédito impediria todos os outros de escolherem a sua.

O ADR não menciona nenhuma das cinco. Sem elas, ele não é implementável.

## Por que há ramos por dialeto

No Postgres `unique=True` vira uma restrição com nome previsível
(`anos_ano_key`); no SQLite vira um `UNIQUE (ano)` **sem nome**, que só dá
para remover recriando a tabela. O `batch_alter_table` do Alembic faz essa
recriação, e a `naming_convention` dá um nome ao que não tinha para que o
`drop_constraint` consiga referenciá-lo.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7f3a0c21e58"
down_revision: Union[str, None] = "c9a2f5e81b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# As catorze tabelas de dinheiro. A lista existe aqui, e não é descoberta do
# modelo, porque uma migração descreve o banco de um momento no tempo — se ela
# lesse o modelo de hoje, mudaria de significado a cada alteração futura.
TABELAS = (
    "anos",
    "contas",
    "saldos_iniciais",
    "categorias",
    "lancamentos",
    "gastos_fixos",
    "gastos_fixos_mensais",
    "regras_categorizacao",
    "cores_forma_pagamento",
    "metas_poupanca",
    "caixinhas",
    "compras_parceladas",
    "faturas_mensais",
    "wishlist",
)

# Dá nome ao que o SQLite deixou sem nome, para o `drop_constraint` alcançar.
CONVENCAO = {"uq": "uq_%(table_name)s_%(column_0_name)s"}

# (tabela, coluna que era única, nome da restrição nova)
UNICIDADES = (
    ("anos", "ano", "uq_ano_por_espaco"),
    ("contas", "nome", "uq_conta_por_espaco"),
    ("categorias", "nome", "uq_categoria_por_espaco"),
    ("regras_categorizacao", "padrao", "uq_regra_por_espaco"),
)


def _e_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "espacos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=80), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "membros_espaco",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("espaco_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "papel",
            sa.Enum("DONO", "MEMBRO", name="papelmembro", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "entrou_em", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["espaco_id"], ["espacos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("espaco_id", "usuario_id", name="uq_membro_espaco_usuario"),
    )
    op.create_index(op.f("ix_membros_espaco_espaco_id"), "membros_espaco", ["espaco_id"])
    op.create_index(
        op.f("ix_membros_espaco_usuario_id"), "membros_espaco", ["usuario_id"]
    )

    conexao = op.get_bind()

    # O espaço nasce **sempre**, mesmo sem usuário. A primeira tentativa foi
    # criá-lo só quando havia alguém para ser dono, e ela falha: a migração
    # inicial do projeto semeia duas contas, então nem um banco recém-migrado
    # está vazio — as linhas semeadas precisam de um espaço a que pertencer.
    conexao.execute(
        sa.text("INSERT INTO espacos (nome) VALUES (:nome)"), {"nome": "Financeiro"}
    )
    espaco_id = conexao.execute(
        sa.text("SELECT id FROM espacos ORDER BY id DESC LIMIT 1")
    ).scalar()

    usuario_id = conexao.execute(
        sa.text("SELECT id FROM usuarios ORDER BY id LIMIT 1")
    ).scalar()
    if usuario_id is not None:
        conexao.execute(
            sa.text(
                "INSERT INTO membros_espaco (espaco_id, usuario_id, papel) "
                "VALUES (:espaco, :usuario, 'DONO')"
            ),
            {"espaco": espaco_id, "usuario": usuario_id},
        )

    # --- a coluna, em três passos, em cada uma das catorze ------------------ #
    for tabela in TABELAS:
        with op.batch_alter_table(tabela) as batch:
            batch.add_column(sa.Column("espaco_id", sa.Integer(), nullable=True))

        conexao.execute(
            sa.text(f"UPDATE {tabela} SET espaco_id = :espaco"),
            {"espaco": espaco_id},
        )

        with op.batch_alter_table(tabela) as batch:
            batch.alter_column(
                "espaco_id", existing_type=sa.Integer(), nullable=False
            )
            batch.create_foreign_key(
                f"fk_{tabela}_espaco", "espacos", ["espaco_id"], ["id"],
                ondelete="CASCADE",
            )
        op.create_index(f"ix_{tabela}_espaco_id", tabela, ["espaco_id"])

    # --- unicidade: de global para por espaço ------------------------------- #
    for tabela, coluna, nome_novo in UNICIDADES:
        if _e_postgres():
            op.drop_constraint(f"{tabela}_{coluna}_key", tabela, type_="unique")
            op.create_unique_constraint(nome_novo, tabela, ["espaco_id", coluna])
        else:
            with op.batch_alter_table(tabela, naming_convention=CONVENCAO) as batch:
                batch.drop_constraint(f"uq_{tabela}_{coluna}", type_="unique")
                batch.create_unique_constraint(nome_novo, ["espaco_id", coluna])

    # --- a cor da forma de pagamento: chave primária composta --------------- #
    # Era só `forma_pagamento`. Sem o espaço na chave, uma cor de crédito
    # valeria para o sistema inteiro.
    if _e_postgres():
        op.drop_constraint(
            "cores_forma_pagamento_pkey", "cores_forma_pagamento", type_="primary"
        )
        op.create_primary_key(
            "cores_forma_pagamento_pkey",
            "cores_forma_pagamento",
            ["espaco_id", "forma_pagamento"],
        )
    else:
        with op.batch_alter_table("cores_forma_pagamento") as batch:
            batch.create_primary_key(
                "pk_cores_forma_pagamento", ["espaco_id", "forma_pagamento"]
            )

    # --- qual espaço cada pessoa está vendo --------------------------------- #
    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(sa.Column("espaco_atual_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_usuario_espaco_atual", "espacos", ["espaco_atual_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        op.f("ix_usuarios_espaco_atual_id"), "usuarios", ["espaco_atual_id"]
    )

    conexao.execute(
        sa.text("UPDATE usuarios SET espaco_atual_id = :espaco"),
        {"espaco": espaco_id},
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_usuarios_espaco_atual_id"), table_name="usuarios")
    with op.batch_alter_table("usuarios") as batch:
        batch.drop_constraint("fk_usuario_espaco_atual", type_="foreignkey")
        batch.drop_column("espaco_atual_id")

    if _e_postgres():
        op.drop_constraint(
            "cores_forma_pagamento_pkey", "cores_forma_pagamento", type_="primary"
        )
        op.create_primary_key(
            "cores_forma_pagamento_pkey", "cores_forma_pagamento", ["forma_pagamento"]
        )
    else:
        with op.batch_alter_table("cores_forma_pagamento") as batch:
            batch.create_primary_key("pk_cores_forma_pagamento", ["forma_pagamento"])

    for tabela, coluna, nome_novo in UNICIDADES:
        if _e_postgres():
            op.drop_constraint(nome_novo, tabela, type_="unique")
            op.create_unique_constraint(f"{tabela}_{coluna}_key", tabela, [coluna])
        else:
            with op.batch_alter_table(tabela) as batch:
                batch.drop_constraint(nome_novo, type_="unique")
                batch.create_unique_constraint(f"uq_{tabela}_{coluna}", [coluna])

    for tabela in TABELAS:
        op.drop_index(f"ix_{tabela}_espaco_id", table_name=tabela)
        with op.batch_alter_table(tabela) as batch:
            batch.drop_constraint(f"fk_{tabela}_espaco", type_="foreignkey")
            batch.drop_column("espaco_id")

    op.drop_index(op.f("ix_membros_espaco_usuario_id"), table_name="membros_espaco")
    op.drop_index(op.f("ix_membros_espaco_espaco_id"), table_name="membros_espaco")
    op.drop_table("membros_espaco")
    op.drop_table("espacos")
