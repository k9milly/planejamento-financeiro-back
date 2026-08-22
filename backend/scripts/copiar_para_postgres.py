"""Copia os dados do SQLite local para o Postgres de produção.

Uso:
    python -m scripts.copiar_para_postgres "postgresql+psycopg://..." --simular

A URL de destino é o "connection string" que o Neon mostra ao criar o banco.
Troque o prefixo `postgresql://` por `postgresql+psycopg://` — é o que diz ao
SQLAlchemy qual driver usar.

A origem é sempre o SQLite local, independente de `DATABASE_URL`. Use
`--origem` para copiar de outro lugar.

O destino precisa estar com o schema criado (`alembic upgrade head` apontando
para ele) e **vazio**: o script se recusa a copiar sobre tabelas com dados,
para não misturar dois históricos.

A ordem de cópia respeita as chaves estrangeiras: um lançamento não pode ser
inserido antes do ano a que pertence.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.config import RAIZ
from app.models import (
    Ano,
    Categoria,
    Conta,
    CorFormaPagamento,
    FaturaMensal,
    GastoFixo,
    GastoFixoMensal,
    ItemWishlist,
    Lancamento,
    RegraCategorizacao,
    SaldoInicial,
    Usuario,
)

# Da tabela sem dependências para a mais dependente. Uma conta precisa existir
# antes de qualquer lançamento ou saldo apontar para ela.
ORDEM = [
    Usuario,
    Categoria,
    Conta,
    Ano,
    SaldoInicial,
    RegraCategorizacao,
    GastoFixo,
    Lancamento,
    GastoFixoMensal,
    FaturaMensal,
    ItemWishlist,
    CorFormaPagamento,
]

# A origem é o banco local, e não `settings.database_url`: na hora de copiar, a
# variável DATABASE_URL costuma já estar apontando para o destino — foi assim
# que uma execução copiou o banco novo (vazio) sobre ele mesmo.
ORIGEM_PADRAO = f"sqlite:///{RAIZ / 'dados.db'}"

# Tabelas que o destino precisa ter vazias. `contas` fica de fora porque a
# própria migração já cria as duas contas iniciais — um destino recém-migrado
# tem linhas ali por construção, e exigi-lo vazio impediria qualquer cópia.
DEVEM_ESTAR_VAZIAS = [m for m in ORDEM if m is not Conta]


def colunas(modelo) -> list[str]:
    return [coluna.name for coluna in modelo.__table__.columns]


def copiar(origem_url: str, destino_url: str, simular: bool) -> None:
    if origem_url == destino_url:
        print(
            "ERRO: origem e destino são o mesmo banco. Confira se a variável "
            "DATABASE_URL não está apontando para o destino.",
            file=sys.stderr,
        )
        sys.exit(1)

    origem = create_engine(origem_url)
    destino = create_engine(destino_url)

    SessaoOrigem = sessionmaker(bind=origem)
    SessaoDestino = sessionmaker(bind=destino)

    with SessaoOrigem() as leitura, SessaoDestino() as escrita:
        # Recusa destino sujo antes de escrever qualquer coisa.
        ocupadas = [
            modelo.__tablename__
            for modelo in DEVEM_ESTAR_VAZIAS
            if escrita.scalar(select(func.count()).select_from(modelo)) > 0
        ]
        if ocupadas:
            print(
                "ERRO: o banco de destino já tem dados em: "
                f"{', '.join(ocupadas)}.\n"
                "Esvazie-o antes de copiar, para não misturar dois históricos.",
                file=sys.stderr,
            )
            sys.exit(1)

        total = 0
        for modelo in ORDEM:
            registros = leitura.scalars(select(modelo)).all()
            nomes = colunas(modelo)

            for registro in registros:
                # `merge` em vez de `add`: preserva os ids, de que as chaves
                # estrangeiras dependem, e sobrescreve linhas que já existam —
                # o caso das contas criadas pela migração. Sem isso, a cópia
                # esbarraria em conflito de chave primária.
                escrita.merge(
                    modelo(**{nome: getattr(registro, nome) for nome in nomes})
                )

            print(f"  {modelo.__tablename__:<24} {len(registros):>5}")
            total += len(registros)

        if simular:
            escrita.rollback()
            print(f"\n[SIMULAÇÃO] {total} registros seriam copiados. Nada foi salvo.")
            return

        escrita.commit()
        print(f"\n{total} registros copiados.")

        _corrigir_sequencias(escrita, destino_url)


def _corrigir_sequencias(sessao, destino_url: str) -> None:
    """Reposiciona os contadores de id do Postgres.

    Inserir registros com id explícito não move a sequência que gera os
    próximos. Sem este ajuste, o primeiro lançamento criado pelo app tentaria
    usar o id 1 — que já existe — e falharia com violação de chave primária.
    """
    if not destino_url.startswith("postgresql"):
        return

    from sqlalchemy import text

    for modelo in ORDEM:
        # Só tabelas com id autoincrementado têm sequência a corrigir —
        # `cores_forma_pagamento` usa a própria forma de pagamento como chave.
        if "id" not in colunas(modelo):
            continue
        tabela = modelo.__tablename__
        sessao.execute(
            text(
                "SELECT setval("
                "  pg_get_serial_sequence(:tabela, 'id'),"
                "  COALESCE((SELECT MAX(id) FROM " + tabela + "), 1),"
                "  (SELECT MAX(id) IS NOT NULL FROM " + tabela + ")"
                ")"
            ),
            {"tabela": tabela},
        )
    sessao.commit()
    print("Contadores de id ajustados.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "destino", help="URL do Postgres (postgresql+psycopg://usuario:senha@host/banco)"
    )
    parser.add_argument(
        "--origem",
        default=ORIGEM_PADRAO,
        help="Banco de onde copiar (padrão: o SQLite local do projeto)",
    )
    parser.add_argument(
        "--simular", action="store_true", help="Mostra o que seria copiado sem gravar"
    )
    args = parser.parse_args()

    # Esconde a senha: a URL do Postgres é uma credencial.
    print(f"Origem : {args.origem.split('@')[-1]}")
    print(f"Destino: {args.destino.split('@')[-1]}\n")

    copiar(args.origem, args.destino, args.simular)


if __name__ == "__main__":
    main()
