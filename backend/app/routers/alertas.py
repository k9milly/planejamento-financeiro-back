"""Contas a vencer que ainda não foram pagas (ADR-06).

Não há tabela de alertas: a resposta é calculada na hora, a partir do dia de
vencimento de cada gasto fixo e cartão e do que já consta como pago no mês.
Persistir alertas obrigaria a mantê-los em dia a cada pagamento, e bastaria um
esquecimento para a lista passar a mentir.
"""

from __future__ import annotations

import calendar
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Ano,
    Conta,
    FaturaMensal,
    GastoFixo,
    GastoFixoMensal,
    SituacaoGastoFixo,
    TipoConta,
)
from app.schemas import AlertaFaturaOut, AlertaGastoFixoOut, AlertaOut

router = APIRouter(prefix="/alertas", tags=["alertas"])

# Quantos dias antes do vencimento a conta começa a aparecer. Constante de
# propósito nesta primeira versão: deixar configurável exigiria mais uma
# preferência de usuário para resolver um problema que ninguém relatou ainda
# (ADR-06).
JANELA_DIAS = 3


@router.get("", response_model=list[AlertaOut], summary="O que vence nos próximos dias")
def listar(db: Session = Depends(get_db)) -> list[AlertaOut]:
    """Só o que vence dentro da janela e ainda não foi pago.

    O que já venceu fica de fora: um alerta de algo atrasado é outra conversa
    (o que fazer com ele, por quanto tempo insistir) e não foi decidida.
    Vencido some da lista sem virar histórico — é o mesmo que já acontece na
    tela de gastos fixos, que mostra situação por mês.
    """
    hoje = date.today()
    ano_ref = db.query(Ano).filter(Ano.ano == hoje.year).one_or_none()
    if ano_ref is None:
        # Ano corrente ainda não criado: não há vencimento a acompanhar.
        return []

    alertas: list[AlertaOut] = [
        *_de_gastos_fixos(ano_ref, hoje, db),
        *_de_faturas(ano_ref, hoje, db),
    ]
    # Mais perto de vencer primeiro — é a ordem em que a pessoa precisa agir.
    # O nome desempata, e vem de campos diferentes conforme a origem.
    return sorted(alertas, key=lambda a: (a.dias_restantes, _rotulo(a)))


def _rotulo(alerta: AlertaOut) -> str:
    return (
        alerta.nome
        if isinstance(alerta, AlertaGastoFixoOut)
        else alerta.nome_cartao
    )


def _dias_ate(dia_vencimento: int, hoje: date) -> int | None:
    """Dias até o vencimento deste mês, ou `None` se estiver fora da janela.

    O dia é ajustado para o último dia do mês quando não existe no calendário
    (vencimento 31 em fevereiro), mesma regra que `gastos_fixos.pagar` já usa
    ao gerar o lançamento — senão o alerta apontaria para uma data inexistente.
    """
    ultimo = calendar.monthrange(hoje.year, hoje.month)[1]
    vencimento = date(hoje.year, hoje.month, min(dia_vencimento, ultimo))
    dias = (vencimento - hoje).days
    return dias if 0 <= dias <= JANELA_DIAS else None


def _de_gastos_fixos(
    ano_ref: Ano, hoje: date, db: Session
) -> list[AlertaGastoFixoOut]:
    pagos = {
        registro.gasto_fixo_id
        for registro in db.query(GastoFixoMensal).filter(
            GastoFixoMensal.mes == hoje.month,
            GastoFixoMensal.situacao == SituacaoGastoFixo.PAGO,
        )
    }

    alertas = []
    for gasto in db.query(GastoFixo).filter(
        GastoFixo.ano_id == ano_ref.id, GastoFixo.ativo.is_(True)
    ):
        if gasto.id in pagos:
            continue
        dias = _dias_ate(gasto.dia_vencimento, hoje)
        if dias is None:
            continue
        alertas.append(
            AlertaGastoFixoOut(
                gasto_fixo_id=gasto.id,
                nome=gasto.descricao,
                dia_vencimento=gasto.dia_vencimento,
                dias_restantes=dias,
                valor=gasto.valor,
            )
        )
    return alertas


def _de_faturas(ano_ref: Ano, hoje: date, db: Session) -> list[AlertaFaturaOut]:
    pagas = {
        registro.cartao_id
        for registro in db.query(FaturaMensal).filter(
            FaturaMensal.ano_id == ano_ref.id,
            FaturaMensal.mes == hoje.month,
            FaturaMensal.situacao == SituacaoGastoFixo.PAGO,
        )
    }

    alertas = []
    for cartao in db.query(Conta).filter(
        Conta.tipo == TipoConta.CARTAO_CREDITO, Conta.ativa.is_(True)
    ):
        # Cartão sem dia de vencimento é dado inconsistente (a API exige o
        # campo); aqui é só ignorado, para um registro estranho não derrubar a
        # lista inteira de alertas.
        if cartao.dia_vencimento_fatura is None or cartao.id in pagas:
            continue
        dias = _dias_ate(cartao.dia_vencimento_fatura, hoje)
        if dias is None:
            continue
        alertas.append(
            AlertaFaturaOut(
                cartao_id=cartao.id,
                nome_cartao=cartao.nome,
                dia_vencimento_fatura=cartao.dia_vencimento_fatura,
                dias_restantes=dias,
                # O valor em aberto depende do cálculo do mês inteiro; quem
                # precisa do número exato chama o endpoint da fatura. Aqui o
                # alerta é sobre a data, não sobre o valor.
                valor=None,
            )
        )
    return alertas
