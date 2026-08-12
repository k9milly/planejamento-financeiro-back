"""Aplica mudanças de schema a um banco que já tem dados.

Uso:
    python -m scripts.migrar

`Base.metadata.create_all()` cria tabelas que faltam, mas nunca altera uma
tabela existente: colunas e índices novos não aparecem sozinhos. Este script
cobre essa lacuna de forma idempotente — rodar duas vezes não faz mal.

É deliberadamente simples porque o projeto tem um banco só, de uma pessoa. Se
passar a existir mais de uma instalação, troque isto por Alembic antes que as
migrações fiquem difíceis de rastrear.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.database import criar_tabelas, engine


def _colunas(conexao, tabela: str) -> set[str]:
    return {c["name"] for c in inspect(conexao).get_columns(tabela)}


def _indices(conexao, tabela: str) -> set[str]:
    return {i["name"] for i in inspect(conexao).get_indexes(tabela)}


def migrar() -> None:
    # Primeiro as tabelas novas inteiras (ex.: regras_categorizacao).
    criar_tabelas()
    print("Tabelas novas criadas (se havia alguma).")

    with engine.begin() as conexao:
        colunas = _colunas(conexao, "lancamentos")

        if "fitid" not in colunas:
            conexao.execute(text("ALTER TABLE lancamentos ADD COLUMN fitid VARCHAR(120)"))
            print("  + coluna lancamentos.fitid")
        else:
            print("  = coluna lancamentos.fitid já existe")

        indices = _indices(conexao, "lancamentos")

        if "ix_lancamentos_fitid" not in indices:
            conexao.execute(
                text("CREATE INDEX ix_lancamentos_fitid ON lancamentos (fitid)")
            )
            print("  + índice ix_lancamentos_fitid")

        if "uq_lancamento_fitid_por_ano" not in indices:
            # Índice único em vez de constraint: o SQLite não suporta
            # ADD CONSTRAINT, e um índice único cumpre o mesmo papel. Linhas com
            # fitid NULL (lançamentos manuais) não colidem entre si.
            conexao.execute(
                text(
                    "CREATE UNIQUE INDEX uq_lancamento_fitid_por_ano "
                    "ON lancamentos (ano_id, fitid)"
                )
            )
            print("  + índice único uq_lancamento_fitid_por_ano")

    print("\nMigração concluída.")


if __name__ == "__main__":
    migrar()
