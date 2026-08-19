"""Sugestão de categoria a partir de texto livre, por regras ensinadas pelo
usuário.

Compartilhado entre a importação de extrato (OFX) e o lançamento rápido por
Telegram: a mesma regra "ifood é Comida" vale nos dois lugares, e o usuário só
precisa ensiná-la uma vez.
"""

from __future__ import annotations

import unicodedata

from app.models import Categoria


def normalizar(texto: str) -> str:
    """Maiúsculas e sem acento, para casar regras independente de digitação."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).upper()


def sugerir_categoria(
    descricao: str, regras: list[tuple[str, Categoria]]
) -> Categoria | None:
    """Regra cujo padrão aparece na descrição.

    Em empate, vence o padrão mais longo — o mais específico. Sem isso, uma
    regra genérica como "MERCADO" ganharia de "MERCADO LIVRE" por acaso da
    ordem de inserção.

    Recebe pares já normalizados em vez das entidades: normalizar o atributo do
    objeto ORM o marcaria como alterado e o SQLAlchemy gravaria a mudança no
    banco no próximo flush.
    """
    alvo = normalizar(descricao)
    candidatas = [(p, c) for p, c in regras if p in alvo]
    if not candidatas:
        return None
    return max(candidatas, key=lambda par: len(par[0]))[1]
