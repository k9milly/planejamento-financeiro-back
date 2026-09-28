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


# check_same_thread só é necessário (e válido) no SQLite.
connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)


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


def criar_tabelas() -> None:
    """Cria o schema. Suficiente enquanto o projeto é local; ao ir para
    Postgres, trocar por migrações Alembic."""
    from app import models  # noqa: F401  (registra os modelos no metadata)

    Base.metadata.create_all(bind=engine)
