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

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.database import Base

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
