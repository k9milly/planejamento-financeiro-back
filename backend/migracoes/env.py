"""Configuração do Alembic.

A URL do banco vem de `app.config`, e não do `alembic.ini`: assim a migração
sempre aponta para o mesmo banco que a aplicação, sem risco de migrar um e
rodar contra outro.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base

# Importar os modelos registra as tabelas no metadata; sem isto o autogenerate
# acharia que o banco inteiro sobra e geraria migrações que apagam tudo.
from app import models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def executar_offline() -> None:
    """Gera o SQL sem conectar, para revisar antes de aplicar."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # O SQLite não sabe ALTER TABLE de verdade; o batch mode recria a
        # tabela por baixo dos panos. No Postgres é ignorado.
        render_as_batch=settings.database_url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def executar_online() -> None:
    conexao_config = config.get_section(config.config_ini_section, {})
    engine = engine_from_config(
        conexao_config, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    with engine.connect() as conexao:
        context.configure(
            connection=conexao,
            target_metadata=target_metadata,
            render_as_batch=settings.database_url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    executar_offline()
else:
    executar_online()
