"""Leitor de extratos OFX.

OFX existe em duas gerações incompatíveis na forma, mas equivalentes no
conteúdo:

* **1.x** é SGML: as tags não fecham (`<TRNAMT>-45.60` e ponto final), e o
  arquivo começa com um cabeçalho `CHAVE:VALOR`.
* **2.x** é XML bem formado, com tags fechando normalmente.

Bancos brasileiros ainda exportam quase sempre 1.x, e em ISO-8859-1. Em vez de
usar um parser XML — que engasga no 1.x — extraímos os campos por expressão
regular, o que funciona nos dois formatos: `<TAG>valor` casa tanto com
`<TAG>valor` quanto com `<TAG>valor</TAG>`.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.services.extrato import (
    ErroExtrato,
    TransacaoExtrato,
    identificador_sintetico,
)

# Um lançamento no extrato. `</STMTTRN>` fecha mesmo no formato 1.x.
_TRANSACAO = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.DOTALL | re.IGNORECASE)

# Para o valor de uma tag: tudo até o próximo '<' ou quebra de linha.
def _campo(bloco: str, tag: str) -> str | None:
    achado = re.search(rf"<{tag}>([^<\r\n]*)", bloco, re.IGNORECASE)
    return achado.group(1).strip() if achado else None


class ErroOFX(ErroExtrato):
    """Arquivo ilegível ou sem transações."""


def _decodificar(conteudo: bytes) -> str:
    """Converte os bytes em texto respeitando o charset declarado.

    O cabeçalho do OFX 1.x traz `CHARSET:1252` ou `ENCODING:USASCII`. Quando
    não dá para confiar nele, tentamos UTF-8 e caímos para Latin-1, que nunca
    falha e é o que os bancos brasileiros usam na prática.
    """
    inicio = conteudo[:512].decode("ascii", errors="ignore").upper()

    if "CHARSET:UTF-8" in inicio or "ENCODING=" in inicio and "UTF-8" in inicio:
        try:
            return conteudo.decode("utf-8")
        except UnicodeDecodeError:
            pass
    if "CHARSET:1252" in inicio or "CHARSET:ISO-8859-1" in inicio:
        return conteudo.decode("cp1252", errors="replace")

    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return conteudo.decode("latin-1")


def _para_data(bruto: str) -> date | None:
    """DTPOSTED vem como AAAAMMDD, opcionalmente seguido de hora e fuso."""
    digitos = re.sub(r"\D", "", bruto)[:8]
    if len(digitos) != 8:
        return None
    try:
        return date(int(digitos[:4]), int(digitos[4:6]), int(digitos[6:8]))
    except ValueError:
        return None


def ler_ofx(conteudo: bytes) -> list[TransacaoExtrato]:
    """Extrai as transações do extrato.

    Levanta `ErroOFX` se o arquivo não tiver nenhuma transação — quase sempre
    sinal de que foi enviado o arquivo errado (um PDF ou CSV renomeado).
    """
    texto = _decodificar(conteudo)
    blocos = _TRANSACAO.findall(texto)

    if not blocos:
        raise ErroOFX(
            "Nenhuma transação encontrada. Confira se o arquivo é mesmo um "
            "extrato OFX exportado pelo banco."
        )

    transacoes: list[TransacaoExtrato] = []
    for bloco in blocos:
        bruto_valor = _campo(bloco, "TRNAMT")
        quando = _para_data(_campo(bloco, "DTPOSTED") or "")

        if bruto_valor is None or quando is None:
            continue  # transação incompleta: sem valor ou sem data não dá para usar

        try:
            # Alguns bancos exportam com vírgula decimal.
            valor = Decimal(bruto_valor.replace(",", ".")).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            continue

        if valor == 0:
            continue  # estornos casados que se anulam não viram lançamento

        # MEMO é o campo livre; NAME é o nome do estabelecimento. Bancos
        # diferentes preenchem um ou outro, então usamos o que houver.
        descricao = _campo(bloco, "MEMO") or _campo(bloco, "NAME") or ""

        transacoes.append(
            TransacaoExtrato(
                # Sem FITID não há como deduplicar; o par data+valor+descrição é
                # o identificador menos ruim disponível — o mesmo que CSV e XLSX
                # usam sempre, já que nesses formatos ele nunca existe.
                fitid=_campo(bloco, "FITID")
                or identificador_sintetico(quando, valor, descricao),
                data=quando,
                valor=abs(valor),
                saida=valor < 0,
                descricao=" ".join(descricao.split()),
            )
        )

    return sorted(transacoes, key=lambda t: t.data)
