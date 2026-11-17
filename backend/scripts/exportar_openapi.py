"""Exporta o `openapi.json` da API para um arquivo.

Uso:
    python -m scripts.exportar_openapi ../openapi.json

Existe por causa do `ADR-20`. O frontend guarda uma cópia deste arquivo e
roda um teste que confere **cada URL que o `api-client` monta** contra os
caminhos publicados aqui. É o teste que teria pego, em agosto, a chamada a
`/fatura?mes=11` numa rota que sempre foi `/fatura/{mes}`: ela respondia
`404` havia quase três meses, e ninguém via porque a tela caía num plano B
que mostrava outro número.

**Não baixa nada da internet.** Monta o esquema a partir do código, aqui
mesmo, então não depende de o Fly estar acordado (a máquina hiberna) nem de
rede. Também não toca no banco: o FastAPI constrói o esquema a partir das
rotas e dos modelos, e `app.openapi()` é puro.

Rodar de novo sempre que um endpoint mudar, e levar o arquivo para o
frontend — é uma cópia versionada lá, não um download automático, justamente
para o teste ser previsível.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.main import app


def principal(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "destino",
        type=Path,
        help="Arquivo a escrever, por exemplo ../openapi.json",
    )
    analisador.add_argument(
        "--compacto",
        action="store_true",
        help="Sem indentação. O padrão é indentado, para o diff ser legível.",
    )
    opcoes = analisador.parse_args(argumentos)

    esquema = app.openapi()

    # `indent=2` e `sort_keys` de propósito: o arquivo é versionado no front,
    # e um esquema em linha única transformaria qualquer mudança num diff de
    # uma linha só, ilegível na revisão.
    texto = json.dumps(
        esquema,
        ensure_ascii=False,
        indent=None if opcoes.compacto else 2,
        sort_keys=True,
    )

    destino: Path = opcoes.destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto + "\n", encoding="utf-8")

    caminhos = len(esquema.get("paths", {}))
    print(f"{destino}: {caminhos} caminhos, {len(texto)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
