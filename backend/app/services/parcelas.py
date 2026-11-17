"""Datas de parcela e leitura de "Parcela N de M" — uma regra só.

Dois caminhos registram a mesma compra parcelada: o botão Parcelar
(`ADR-14`), que gera as parcelas na hora da compra, e a fatura importada
(`ADR-19`), onde cada fatura traz uma parcela já cobrada.

Até o `ADR-19` eles discordavam, e de um jeito que ninguém via: o botão
colocava a "Parcela 2 de 2" de uma compra de 13/11 em 13/12, e a importação
colocava em 13/11, porque é a data que a fatura imprime. Importando as quatro
faturas de uma compra em 4x, as quatro parcelas terminavam empilhadas no mês
da compra — e os meses em que o dinheiro de fato sai ficavam vazios.

Este módulo existe para a regra ser **uma**. Duas implementações da mesma
regra voltam a divergir; a pergunta não é se, é quando.
"""

from __future__ import annotations

import calendar
import re
from datetime import date

# "Parcela 3 de 4", como o Mercado Pago imprime na descrição da linha. Aceita
# acento e caixa variada porque a descrição vem do banco, não de nós, e um
# layout que mude "de" para "De" não deve apagar o parcelamento em silêncio.
_PARCELA = re.compile(r"\bParcela\s+(\d{1,2})\s+de\s+(\d{1,2})\b", re.IGNORECASE)


def datas_das_parcelas(primeira: date, quantidade: int) -> list[date]:
    """Uma por mês, a partir da primeira, no mesmo dia.

    Dia que não existe no mês de destino cai no último dia dele — mesmo
    tratamento que `gastos_fixos.py` já dá ao vencimento (dia 31 em fevereiro).
    """
    datas = []
    for passo in range(quantidade):
        mes_total = primeira.month - 1 + passo
        ano = primeira.year + mes_total // 12
        mes = mes_total % 12 + 1
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        datas.append(date(ano, mes, min(primeira.day, ultimo_dia)))
    return datas


def ler_parcela(descricao: str) -> tuple[int, int] | None:
    """`(N, M)` de "Parcela N de M" na descrição, ou `None` se não houver.

    Devolve o par inteiro, e não só o `N`, para quem chama poder recusar o
    absurdo — uma "Parcela 5 de 3" é erro de leitura, não parcelamento.
    """
    achado = _PARCELA.search(descricao or "")
    if achado is None:
        return None
    numero, total = int(achado.group(1)), int(achado.group(2))
    if numero < 1 or total < 1 or numero > total:
        return None
    return numero, total


def data_da_parcela(data_impressa: date, numero: int) -> date:
    """Onde a parcela `numero` de fato cai, dada a data da compra.

    A fatura imprime **sempre a data da compra original**, repetida em toda
    fatura até a última parcela. A parcela 3 de uma compra de 26/07 é cobrada
    em setembro, e é em setembro que o dinheiro sai — é lá que ela pertence.
    """
    return datas_das_parcelas(data_impressa, numero)[-1]
