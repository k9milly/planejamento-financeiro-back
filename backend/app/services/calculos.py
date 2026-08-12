"""Regras de negócio dos totais.

Este é o módulo que substitui as fórmulas SUMIF da planilha original. Ele é
puro: recebe lançamentos e devolve números, sem tocar no banco. Isso mantém as
regras testáveis isoladamente (ver `tests/test_calculos.py`).

Duas diferenças em relação à planilha:

* Os meses são **encadeados** — o fechamento de um é a abertura do seguinte.
  Na planilha, cada aba trazia o saldo de abertura digitado à mão, e eles se
  desencontravam.
* O dinheiro vive em **contas**, cada uma com saldo disponível e reserva. Mover
  dinheiro entre contas suas não é receita nem despesa, e não entra nos totais
  de entradas e saídas do mês.
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
class Carteiras:
    """O que uma conta tem: disponível para gastar e reservado."""

    saldo: Decimal = ZERO
    guardado: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.saldo + self.guardado


@dataclass
class TotaisMes:
    """Os números do container 'Total de {mês}'."""

    mes: int

    # Movimentações de verdade: só o que entrou ou saiu do seu patrimônio.
    # Transferências entre contas suas ficam fora de propósito.
    entradas: Decimal = ZERO
    saidas: Decimal = ZERO
    rendimentos: Decimal = ZERO
    perdas: Decimal = ZERO

    guardado_bruto: Decimal = ZERO  # movido do saldo para a reserva
    retirado: Decimal = ZERO  # devolvido da reserva para o saldo
    transferido: Decimal = ZERO  # circulou entre contas suas

    # Fechamento por conta e consolidado.
    por_conta: dict[int, Carteiras] = field(default_factory=dict)
    abertura_por_conta: dict[int, Carteiras] = field(default_factory=dict)

    gastos_por_categoria: dict[str, Decimal] = field(default_factory=dict)

    @property
    def saldo(self) -> Decimal:
        """Disponível somando todas as contas."""
        return sum((c.saldo for c in self.por_conta.values()), ZERO)

    @property
    def saldo_inicial(self) -> Decimal:
        return sum((c.saldo for c in self.abertura_por_conta.values()), ZERO)

    @property
    def guardado_acumulado(self) -> Decimal:
        """Reserva somando todas as contas."""
        return sum((c.guardado for c in self.por_conta.values()), ZERO)

    @property
    def guardado_no_mes(self) -> Decimal:
        """Quanto a reserva variou no mês, somando todas as contas."""
        anterior = sum((c.guardado for c in self.abertura_por_conta.values()), ZERO)
        return self.guardado_acumulado - anterior


def _copiar(origem: dict[int, Carteiras]) -> dict[int, Carteiras]:
    return {
        conta_id: Carteiras(saldo=c.saldo, guardado=c.guardado)
        for conta_id, c in origem.items()
    }


def calcular_totais_mes(
    mes: int,
    lancamentos: Iterable[Lancamento],
    abertura: dict[int, Carteiras],
) -> TotaisMes:
    """Totaliza um único mês a partir de seus lançamentos.

    `abertura` traz as carteiras de cada conta no fechamento do mês anterior.
    """
    totais = TotaisMes(
        mes=mes,
        abertura_por_conta=_copiar(abertura),
        por_conta=_copiar(abertura),
    )
    por_categoria: dict[str, Decimal] = defaultdict(lambda: ZERO)

    def carteiras(conta_id: int) -> Carteiras:
        """Contas criadas depois do início do ano começam zeradas."""
        return totais.por_conta.setdefault(conta_id, Carteiras())

    for lanc in lancamentos:
        valor = _d(lanc.valor)
        conta = carteiras(lanc.conta_id)

        if lanc.tipo is TipoLancamento.ENTRADA:
            conta.saldo += valor
            totais.entradas += valor

        elif lanc.tipo is TipoLancamento.SAIDA:
            conta.saldo -= valor
            totais.saidas += valor
            nome = lanc.categoria.nome if lanc.categoria else "Sem categoria"
            por_categoria[nome] += valor

        elif lanc.tipo is TipoLancamento.GUARDADO:
            conta.saldo -= valor
            conta.guardado += valor
            totais.guardado_bruto += valor

        elif lanc.tipo is TipoLancamento.RETIRADO:
            conta.guardado -= valor
            conta.saldo += valor
            totais.retirado += valor

        elif lanc.tipo is TipoLancamento.RENDIMENTO:
            # Sem destino explícito assumimos conta — é o caso mais comum e
            # evita que um dado incompleto suma do saldo.
            if lanc.destino is DestinoRendimento.GUARDADO:
                conta.guardado += valor
            else:
                conta.saldo += valor
            totais.rendimentos += valor

        elif lanc.tipo is TipoLancamento.PERDA:
            if lanc.destino is DestinoRendimento.GUARDADO:
                conta.guardado -= valor
            else:
                conta.saldo -= valor
            totais.perdas += valor

        elif lanc.tipo is TipoLancamento.TRANSFERENCIA:
            # O patrimônio não muda: o dinheiro só troca de conta. Por isso não
            # entra em entradas nem em saídas.
            conta.saldo -= valor
            if lanc.conta_destino_id is not None:
                carteiras(lanc.conta_destino_id).saldo += valor
            totais.transferido += valor

    totais.gastos_por_categoria = dict(
        sorted(por_categoria.items(), key=lambda kv: kv[1], reverse=True)
    )
    return totais


def calcular_ano(
    lancamentos: Sequence[Lancamento],
    aberturas: dict[int, Carteiras],
) -> list[TotaisMes]:
    """Totaliza os 12 meses em sequência, encadeando os saldos.

    `aberturas` mapeia conta -> carteiras no começo do ano.

    Devolve sempre 12 entradas (janeiro a dezembro), mesmo que alguns meses não
    tenham lançamento algum — a interface precisa das 12 páginas.
    """
    por_mes: dict[int, list[Lancamento]] = defaultdict(list)
    for lanc in lancamentos:
        por_mes[lanc.mes].append(lanc)

    resultado: list[TotaisMes] = []
    atual = _copiar(aberturas)

    for mes in range(1, 13):
        totais = calcular_totais_mes(mes, por_mes.get(mes, []), atual)
        resultado.append(totais)
        atual = _copiar(totais.por_conta)

    return resultado


def total_guardado_geral(meses: Sequence[TotaisMes]) -> Decimal:
    """O campo 'total' do container 'Total guardado': a reserva ao fim do ano."""
    return meses[-1].guardado_acumulado if meses else ZERO
