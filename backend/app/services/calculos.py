"""Regras de negócio dos totais.

Este é o módulo que substitui as fórmulas SUMIF da planilha original. Ele é
puro: recebe lançamentos e devolve números, sem tocar no banco. Isso mantém as
regras testáveis isoladamente (ver `tests/test_calculos.py`).

Diferença importante em relação à planilha: lá o saldo de abertura de cada mês
era digitado à mão em cada aba, o que fazia os meses se desencontrarem. Aqui os
meses são **encadeados**: o fechamento de um é a abertura do seguinte.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Sequence

from app.models import DestinoRendimento, Lancamento, TipoLancamento

ZERO = Decimal("0.00")


def _d(valor) -> Decimal:
    """Converte para Decimal com 2 casas, tolerando float/str vindos do ORM."""
    return Decimal(str(valor)).quantize(Decimal("0.01"))


@dataclass
class TotaisMes:
    """Os números do container 'Total de {mês}'."""

    mes: int
    entradas: Decimal = ZERO
    saidas: Decimal = ZERO
    rendimento_conta: Decimal = ZERO
    rendimento_guardado: Decimal = ZERO
    guardado_bruto: Decimal = ZERO  # quanto foi movido da conta para a reserva
    retirado: Decimal = ZERO  # quanto voltou da reserva para a conta

    saldo_inicial: Decimal = ZERO
    saldo: Decimal = ZERO  # saldo de fechamento da conta

    guardado_no_mes: Decimal = ZERO  # variação líquida da reserva no mês
    guardado_acumulado: Decimal = ZERO  # reserva total ao fim do mês

    gastos_por_categoria: dict[str, Decimal] = field(default_factory=dict)


def calcular_totais_mes(
    mes: int,
    lancamentos: Iterable[Lancamento],
    saldo_inicial: Decimal,
    guardado_inicial: Decimal,
) -> TotaisMes:
    """Totaliza um único mês a partir de seus lançamentos.

    `saldo_inicial` e `guardado_inicial` são os valores de fechamento do mês
    anterior (ou os saldos de abertura do ano, se for o primeiro mês).
    """
    t = TotaisMes(mes=mes, saldo_inicial=saldo_inicial)
    por_categoria: dict[str, Decimal] = defaultdict(lambda: ZERO)

    for lanc in lancamentos:
        valor = _d(lanc.valor)

        if lanc.tipo is TipoLancamento.ENTRADA:
            t.entradas += valor
        elif lanc.tipo is TipoLancamento.SAIDA:
            t.saidas += valor
            nome = lanc.categoria.nome if lanc.categoria else "Sem categoria"
            por_categoria[nome] += valor
        elif lanc.tipo is TipoLancamento.GUARDADO:
            t.guardado_bruto += valor
        elif lanc.tipo is TipoLancamento.RETIRADO:
            t.retirado += valor
        elif lanc.tipo is TipoLancamento.RENDIMENTO:
            if lanc.destino is DestinoRendimento.GUARDADO:
                t.rendimento_guardado += valor
            else:
                # Sem destino explícito assumimos conta — é o caso mais comum e
                # evita que um dado incompleto suma do saldo.
                t.rendimento_conta += valor

    # Conta: entra o que recebi, o que rendeu nela e o que voltou da reserva;
    # sai o que gastei e o que mandei para a reserva.
    t.saldo = (
        saldo_inicial
        + t.entradas
        + t.rendimento_conta
        + t.retirado
        - t.saidas
        - t.guardado_bruto
    )

    # Reserva: entra o que guardei e o que rendeu nela; sai o que retirei.
    t.guardado_no_mes = t.guardado_bruto + t.rendimento_guardado - t.retirado
    t.guardado_acumulado = guardado_inicial + t.guardado_no_mes

    t.gastos_por_categoria = dict(
        sorted(por_categoria.items(), key=lambda kv: kv[1], reverse=True)
    )
    return t


def calcular_ano(
    lancamentos: Sequence[Lancamento],
    saldo_inicial_conta: Decimal,
    saldo_inicial_guardado: Decimal,
) -> list[TotaisMes]:
    """Totaliza os 12 meses em sequência, encadeando os saldos.

    Devolve sempre 12 entradas (janeiro a dezembro), mesmo que alguns meses não
    tenham lançamento algum — a interface precisa das 12 páginas.
    """
    por_mes: dict[int, list[Lancamento]] = defaultdict(list)
    for lanc in lancamentos:
        por_mes[lanc.mes].append(lanc)

    resultado: list[TotaisMes] = []
    saldo = _d(saldo_inicial_conta)
    guardado = _d(saldo_inicial_guardado)

    for mes in range(1, 13):
        totais = calcular_totais_mes(mes, por_mes.get(mes, []), saldo, guardado)
        resultado.append(totais)
        saldo = totais.saldo
        guardado = totais.guardado_acumulado

    return resultado


def total_guardado_geral(meses: Sequence[TotaisMes]) -> Decimal:
    """O campo 'total' do container 'Total guardado': a reserva ao fim do ano."""
    return meses[-1].guardado_acumulado if meses else ZERO
