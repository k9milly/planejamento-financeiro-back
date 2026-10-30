"""Conexão com o banco.

Usa SQLite por padrão (arquivo local, zero configuração). Para migrar para
Postgres basta apontar DATABASE_URL — nenhum outro arquivo muda.
"""

from __future__ import annotations

from collections.abc import Generator

import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def criar_engine(url: str) -> Engine:
    """A engine da aplicação, numa função para o teste poder construir outra.

    Sem isto, a única engine seria a do módulo, criada a partir de
    `settings.database_url` no import — e aí a configuração do pool só poderia
    ser conferida lendo atributos, nunca exercitada. O defeito que motivou isto
    (ver `pool_pre_ping` abaixo) é de comportamento, não de valor de atributo.
    """
    # check_same_thread só é necessário (e válido) no SQLite.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}

    return create_engine(
        url,
        connect_args=connect_args,
        future=True,
        # Testa a conexão antes de entregá-la, e troca por uma nova se estiver
        # morta.
        #
        # O Postgres de produção é serverless (Neon): ele encerra a conexão
        # quando o banco fica ocioso, e a máquina no Fly também dorme. O pool
        # do SQLAlchemy não sabe disso e guarda o socket morto, então a
        # **primeira** requisição depois de um tempo parado estourava com
        # `OperationalError` e um `500` — e a seguinte funcionava, porque o pool
        # já havia descartado a conexão ruim.
        #
        # Visto no log de produção em 13/10/2026: `GET /contas` respondeu `500`
        # na primeira chamada depois de a máquina religar, e `200` em todas as
        # outras. Para quem usa, aparecia como "abri o app e deu erro, recarreguei
        # e funcionou" — intermitente, sem causa visível e fácil de culpar a
        # internet.
        #
        # Custa um `SELECT 1` por conexão retirada do pool, o que é barato perto
        # de uma tela de erro. Não entra `pool_recycle`: o pre-ping já cobre a
        # conexão encerrada do outro lado, e um tempo fixo de reciclagem seria um
        # número arbitrário a manter.
        pool_pre_ping=True,
    )


engine = criar_engine(settings.database_url)


@event.listens_for(Engine, "connect")
def _ligar_chaves_estrangeiras(conexao, _registro) -> None:
    """O SQLite ignora chave estrangeira se ninguém pedir.

    Sem isto, `ON DELETE SET NULL`, `CASCADE` e `RESTRICT` não fazem nada aqui
    e fazem tudo no Postgres de produção — a pior divergência possível, porque
    a suíte passa e o comportamento real é outro. Foi assim que o `SET NULL` do
    vínculo meta↔wishlist (ADR-13) passou despercebido até alguém escrever o
    teste que o cobrava.

    Registrado no `Engine` genérico, e não nesta `engine`: os testes criam a
    própria engine por arquivo de banco descartável, e precisam da mesma regra
    — senão o problema continua, só que escondido.
    """
    if isinstance(conexao, sqlite3.Connection):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Dependência do FastAPI: uma sessão por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def exigir_schema() -> None:
    """Confere que o banco já foi migrado — e não cria tabela nenhuma.

    Antes isto era `criar_tabelas()`, com `Base.metadata.create_all`. O
    `app/main.py` explica por que a aplicação parou de fazer isso quando o
    Alembic entrou: `create_all` cria a tabela que falta e **ignora coluna
    nova**, então um banco desatualizado passa por bom e só quebra na
    primeira consulta. Os scripts continuaram chamando, o que era a mesma
    armadilha pela porta dos fundos.

    Com um agravante próprio: um banco criado por `create_all` nasce sem
    linha em `alembic_version`, e o primeiro `alembic upgrade head` depois
    disso falha dizendo que as tabelas já existem — o banco fica num estado
    que nenhum dos dois caminhos conserta sozinho.

    Levanta `SystemExit` em vez de devolver um booleano porque quem chama são
    os scripts de linha de comando, e a mensagem é para a pessoa que está no
    terminal.
    """
    from sqlalchemy import inspect

    from app import models  # noqa: F401  (registra os modelos no metadata)

    if not inspect(engine).has_table("usuarios"):
        raise SystemExit(
            "O banco ainda não tem schema.\n"
            "Rode `python -m alembic upgrade head` antes — é o mesmo comando "
            "que roda no deploy."
        )
