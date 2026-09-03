"""O schema precisa ser válido no Postgres, não só no SQLite.

Os testes rodam contra SQLite, produção roda Postgres. O SQLite é permissivo
com tipos; o Postgres não. Sem um teste que olhe pelo dialeto de produção, uma
migração pode passar aqui e derrubar o deploy — foi o que aconteceu com
`server_default=text("0")` numa coluna booleana:

    column "alertas_email_ativo" is of type boolean but default expression is
    of type integer

O erro só apareceu no `alembic upgrade` de produção, com a aplicação em
crash-loop até o `server_default` virar `sa.false()`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.database import Base

# A raiz de `backend/`, onde moram `alembic.ini` e `migracoes/`.
RAIZ = Path(__file__).resolve().parents[1]

# `DEFAULT 0`/`DEFAULT 1` numa coluna BOOLEAN — o que o Postgres recusa.
BOOLEANO_COM_DEFAULT_NUMERICO = re.compile(
    r"\bBOOLEAN\b[^,)]*\bDEFAULT\s+[01]\b", re.IGNORECASE
)


@pytest.mark.parametrize(
    "tabela", Base.metadata.tables.values(), ids=lambda t: t.name
)
def test_tabela_compila_para_postgres(tabela):
    """Nenhuma coluna booleana pode ter default numérico.

    Use `sa.false()`/`sa.true()`, que o SQLAlchemy traduz por dialeto (`0` no
    SQLite, `false` no Postgres), em vez de `text("0")`, que sai igual nos dois
    e só é aceito por um.
    """
    ddl = str(CreateTable(tabela).compile(dialect=postgresql.dialect()))
    achado = BOOLEANO_COM_DEFAULT_NUMERICO.search(ddl)
    assert achado is None, (
        f"`{tabela.name}` tem coluna booleana com default numérico "
        f"({achado.group(0)!r}) — o Postgres recusa. Troque por "
        "`sa.false()`/`sa.true()`."
    )


def test_a_regressao_seria_detectada():
    """Garante que o teste acima falharia de verdade com o erro original.

    Sem isto, uma mudança no regex poderia deixar o teste passando sempre, e a
    proteção viraria enfeite.
    """
    ruim = sa.Table(
        "exemplo_ruim",
        sa.MetaData(),
        sa.Column("b", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    ddl = str(CreateTable(ruim).compile(dialect=postgresql.dialect()))
    assert BOOLEANO_COM_DEFAULT_NUMERICO.search(ddl) is not None


# --------------------------------------------------------------------------- #
# O banco que as migrações produzem precisa bater com os modelos
# --------------------------------------------------------------------------- #
def _banco_migrado(tmp_path):
    """Sobe um banco do zero rodando todas as migrações, e devolve a engine.

    Em subprocesso, e não chamando `alembic.command` aqui, porque
    `migracoes/env.py` resolve a URL a partir de `settings.database_url` — que
    já foi lido quando o teste importou a aplicação. Passar `sqlalchemy.url`
    pela `Config` seria ignorado, e o teste rodaria contra o banco errado.
    Como efeito colateral, isto exercita exatamente o comando que o Dockerfile
    roda no deploy.
    """
    import os
    import subprocess
    import sys

    url = f"sqlite:///{tmp_path / 'migrado.db'}"
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=RAIZ,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, (
        "`alembic upgrade head` falhou. Saída: "
        + resultado.stdout
        + resultado.stderr
    )
    return sa.create_engine(url)


def test_migracoes_produzem_o_schema_dos_modelos(tmp_path):
    """As migrações e os modelos precisam descrever o mesmo banco.

    Os testes criam as tabelas por `Base.metadata.create_all`, não pelas
    migrações — então um modelo pode ganhar uma coluna, ou mudar o tamanho de
    uma, sem que nenhuma migração acompanhe, e a suíte inteira continua verde.
    Produção, que roda `alembic upgrade`, é quem descobre.

    Foi o que quase aconteceu ao acrescentar `TRANSFERENCIA_CAIXINHA` ao
    `TipoLancamento` (ADR-10): `lancamentos.tipo` é um VARCHAR dimensionado
    pelo nome mais longo do enum, estava em `VARCHAR(13)`, e o nome novo tem 22
    caracteres. O SQLite ignora o tamanho declarado e aceitaria a gravação; o
    Postgres recusaria com *value too long*.
    """
    engine = _banco_migrado(tmp_path)
    inspetor = sa.inspect(engine)

    esperado = Base.metadata.tables
    faltando = set(esperado) - set(inspetor.get_table_names())
    assert not faltando, (
        f"As migrações não criam {sorted(faltando)}. Um modelo novo precisa de "
        "uma migração — os testes criam as tabelas sozinhos e não avisariam."
    )

    divergencias: list[str] = []
    for nome, tabela in esperado.items():
        real = {c["name"]: c for c in inspetor.get_columns(nome)}

        for coluna in tabela.columns:
            if coluna.name not in real:
                divergencias.append(f"{nome}.{coluna.name} não existe no banco migrado")
                continue

            declarado = getattr(coluna.type, "length", None)
            no_banco = getattr(real[coluna.name]["type"], "length", None)
            if declarado and no_banco and declarado > no_banco:
                divergencias.append(
                    f"{nome}.{coluna.name}: o modelo quer {declarado} caracteres, "
                    f"a migração deixou {no_banco}"
                )

    assert not divergencias, "\n".join(divergencias)


def test_a_regressao_do_enum_seria_detectada(tmp_path):
    """O teste acima precisa pegar de verdade uma coluna curta demais.

    Sem isto, um erro na comparação de tamanhos passaria despercebido e a
    proteção viraria enfeite — mesmo motivo do teste equivalente lá em cima.
    """
    engine = _banco_migrado(tmp_path)
    with engine.begin() as conexao:
        conexao.execute(sa.text("ALTER TABLE lancamentos RENAME TO lancamentos_x"))
        conexao.execute(sa.text("CREATE TABLE lancamentos (tipo VARCHAR(13))"))

    inspetor = sa.inspect(engine)
    largura = [
        c["type"].length
        for c in inspetor.get_columns("lancamentos")
        if c["name"] == "tipo"
    ][0]
    declarado = Base.metadata.tables["lancamentos"].columns["tipo"].type.length

    assert declarado > largura, (
        "O enum deixou de ser maior que 13 caracteres — se `TipoLancamento` "
        "encolheu, este teste precisa de outro exemplo."
    )
