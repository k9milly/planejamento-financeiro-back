"""Vocabulário comum aos leitores de extrato.

Cada formato tem seu próprio módulo (`ofx.py` para OFX, `tabular.py` para CSV
e XLSX), mas todos entregam a mesma coisa: uma lista de `TransacaoExtrato`. O
resto do sistema — dedupe, sugestão de categoria, prévia — não sabe de qual
arquivo a transação veio, e é justamente isso que permitiu acrescentar dois
formatos sem tocar no fluxo de importação (ver ADR-08).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


class ErroExtrato(ValueError):
    """Arquivo ilegível, no formato errado, ou sem transações.

    A mensagem chega ao usuário como `detail` de um 422, então precisa dizer o
    que fazer, não em que linha do parser deu errado.
    """


@dataclass(frozen=True)
class TransacaoExtrato:
    """Uma transação do extrato, já normalizada.

    `valor` é sempre positivo; `saida` diz o sentido — a mesma convenção do
    resto do sistema, onde o sinal vem do tipo e não do número.
    """

    fitid: str
    data: date
    valor: Decimal
    saida: bool
    descricao: str


def para_decimal(bruto: str) -> Decimal | None:
    """Lê um valor monetário escrito por gente, ou devolve `None`.

    Mora aqui, e não em cada leitor, porque CSV, XLSX e PDF esbarram nas mesmas
    variações: `R$`, separador de milhar, e as duas convenções decimais que
    convivem na prática — `-1.234,56` e `-1,234.56` são o mesmo número.

    Devolve `None` em vez de levantar: quem chama decide se um valor ilegível é
    erro (uma planilha, onde toda linha deveria ser transação) ou apenas uma
    linha que não interessa (um PDF, onde a maior parte do texto não é).
    """
    limpo = re.sub(r"[^\d,.\-]", "", bruto or "")
    if not limpo or not any(c.isdigit() for c in limpo):
        return None

    # Quem estiver mais à direita é o separador decimal; o outro é milhar.
    if "," in limpo and "." in limpo:
        decimal_e_virgula = limpo.rfind(",") > limpo.rfind(".")
        limpo = (
            limpo.replace(".", "").replace(",", ".")
            if decimal_e_virgula
            else limpo.replace(",", "")
        )
    elif "," in limpo:
        limpo = limpo.replace(",", ".")

    try:
        return Decimal(limpo).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def identificador_sintetico(quando: date, valor_com_sinal: Decimal, descricao: str) -> str:
    """Identificador estável para transação sem identificador do banco.

    CSV e XLSX **nunca** trazem um identificador de transação; OFX às vezes
    também não (`FITID` ausente). Os dois casos usam esta mesma chave em vez de
    cada formato inventar a sua — duas estratégias de dedupe coexistindo dariam
    resultados diferentes para o mesmo extrato baixado em formatos diferentes.

    O valor entra **com sinal**: sem isso, uma entrada e uma saída de mesmo dia
    e mesmo montante colidiriam e a segunda seria descartada como duplicata.
    """
    return f"{quando.isoformat()}|{valor_com_sinal}|{descricao[:40]}"
