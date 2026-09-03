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

from app.models import DestinoRendimento, Lancamento, TipoConta, TipoLancamento

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

    # Fechamento por conta e consolidado. Só contas do tipo `corrente` — dívida
    # de cartão fica em `por_cartao`, para nunca se misturar com dinheiro
    # disponível (ver ADR-0002 e a spec "Saldo inteligente").
    por_conta: dict[int, Carteiras] = field(default_factory=dict)
    abertura_por_conta: dict[int, Carteiras] = field(default_factory=dict)

    # Fechamento de cada conta-cartão. `saldo` aqui é sempre <= 0: é a fatura
    # em aberto, não dinheiro disponível. `guardado` fica sempre zero (um
    # cartão não tem reserva).
    por_cartao: dict[int, Carteiras] = field(default_factory=dict)

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
    tipos_conta: dict[int, TipoConta] | None = None,
) -> TotaisMes:
    """Totaliza um único mês a partir de seus lançamentos.

    `abertura` traz as carteiras de cada conta (correntes e cartões juntos) no
    fechamento do mês anterior. `tipos_conta` diz qual é qual — só assim dá
    para separar `por_conta` (dinheiro disponível) de `por_cartao` (dívida)
    sem que um bug de filtro esquecido em algum consumidor volte a somar
    dívida como saldo.
    """
    tipos_conta = tipos_conta or {}

    def _e_cartao(conta_id: int) -> bool:
        return tipos_conta.get(conta_id) is TipoConta.CARTAO_CREDITO

    abertura_correntes = {
        cid: c for cid, c in abertura.items() if not _e_cartao(cid)
    }
    abertura_cartoes = {cid: c for cid, c in abertura.items() if _e_cartao(cid)}

    totais = TotaisMes(
        mes=mes,
        abertura_por_conta=_copiar(abertura_correntes),
        por_conta=_copiar(abertura_correntes),
        por_cartao=_copiar(abertura_cartoes),
    )
    por_categoria: dict[str, Decimal] = defaultdict(lambda: ZERO)

    def carteiras(conta_id: int) -> Carteiras:
        """Contas criadas depois do início do ano começam zeradas."""
        if _e_cartao(conta_id):
            return totais.por_cartao.setdefault(conta_id, Carteiras())
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

        elif lanc.tipo is TipoLancamento.TRANSFERENCIA_CAIXINHA:
            # Não faz nada, e isso é a regra — não um caso esquecido (ADR-10).
            # O dinheiro continua guardado na mesma conta; só mudou de qual
            # caixinha ele é. Saldo, guardado, entradas e saídas ficam iguais.
            # Quem reparte o guardado entre as caixinhas é
            # `services/caixinhas.py`, não este cálculo.
            pass

    totais.gastos_por_categoria = dict(
        sorted(por_categoria.items(), key=lambda kv: kv[1], reverse=True)
    )
    return totais


def calcular_ano(
    lancamentos: Sequence[Lancamento],
    aberturas: dict[int, Carteiras],
    tipos_conta: dict[int, TipoConta] | None = None,
) -> list[TotaisMes]:
    """Totaliza os 12 meses em sequência, encadeando os saldos.

    `aberturas` mapeia conta -> carteiras no começo do ano (correntes e
    cartões juntos). `tipos_conta` mapeia conta -> tipo, para separar saldo
    disponível de dívida de cartão em cada mês (ver `calcular_totais_mes`).

    Devolve sempre 12 entradas (janeiro a dezembro), mesmo que alguns meses não
    tenham lançamento algum — a interface precisa das 12 páginas.
    """
    por_mes: dict[int, list[Lancamento]] = defaultdict(list)
    for lanc in lancamentos:
        por_mes[lanc.mes].append(lanc)

    resultado: list[TotaisMes] = []
    atual = _copiar(aberturas)

    for mes in range(1, 13):
        totais = calcular_totais_mes(mes, por_mes.get(mes, []), atual, tipos_conta)
        resultado.append(totais)
        atual = {**_copiar(totais.por_conta), **_copiar(totais.por_cartao)}

    return resultado


def total_guardado_geral(meses: Sequence[TotaisMes]) -> Decimal:
    """O campo 'total' do container 'Total guardado': a reserva ao fim do ano."""
    return meses[-1].guardado_acumulado if meses else ZERO


def variacao_do_guardado(lancamentos: Iterable[Lancamento]) -> Decimal:
    """Quanto a reserva cresceu (ou encolheu) num conjunto de lançamentos.

    Diferente de `TotaisMes.guardado_acumulado`, que é um saldo — o total que
    existe na reserva num dado momento, incluindo tudo o que veio antes. Aqui é
    o movimento: só o efeito dos lançamentos recebidos.

    Serve para medir o progresso de uma meta com prazo, que pergunta "quanto
    juntei desde que decidi juntar" — usar o saldo ali daria a uma meta recém
    criada o progresso de toda a reserva já existente.

    Os quatro tipos que mexem na reserva estão aqui, e só aqui, para a regra
    não divergir da usada em `calcular_totais_mes`. `transferencia_caixinha`
    não é um deles de propósito: ela realoca entre caixinhas da mesma conta,
    sem mudar quanto a conta tem guardado (ADR-10).
    """
    total = ZERO
    for lanc in lancamentos:
        valor = _d(lanc.valor)
        if lanc.tipo is TipoLancamento.GUARDADO:
            total += valor
        elif lanc.tipo is TipoLancamento.RETIRADO:
            total -= valor
        elif lanc.destino is DestinoRendimento.GUARDADO:
            if lanc.tipo is TipoLancamento.RENDIMENTO:
                total += valor
            elif lanc.tipo is TipoLancamento.PERDA:
                total -= valor
    return total
