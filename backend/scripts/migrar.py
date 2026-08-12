"""Coloca o banco no schema mais recente.

Uso:
    python -m scripts.migrar

É um atalho para `alembic upgrade head`, para quem não quer decorar o comando
do Alembic. Rodar duas vezes não faz mal: migrações já aplicadas são puladas.

Faça uma cópia do banco antes de rodar em dados que você não quer perder.
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

RAIZ = Path(__file__).resolve().parent.parent


def migrar() -> None:
    config = Config(str(RAIZ / "alembic.ini"))
    # O caminho precisa ser absoluto: sem isto o comando só funciona se rodado
    # de dentro da pasta backend.
    config.set_main_option("script_location", str(RAIZ / "migracoes"))
    command.upgrade(config, "head")
    print("\nBanco atualizado.")


if __name__ == "__main__":
    try:
        migrar()
    except Exception as erro:  # noqa: BLE001 - a mensagem do Alembic é o que importa
        print(f"\nA migração falhou: {erro}", file=sys.stderr)
        sys.exit(1)
