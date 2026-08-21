"""Endpoints da fatura do cartão de crédito: vencimento, pagar, desfazer.

Molde de `routers/gastos_fixos.py` — mesma ideia de "modelo + situação mensal
+ pagar/desfazer idempotentes" — só que a fatura não guarda um valor: ele é
sempre recalculado a partir dos lançamentos (ver ADR-0003, "Por que não
calcular 'em aberto' a partir de um campo guardado").
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import obter_ano, obter_ano_editavel
from app.models import (
    Ano,
    Conta,
    FaturaMensal,
    Lancamento,
    SituacaoGastoFixo,
    TipoConta,
    TipoLancamento,
)
from app.routers.anos import aberturas_do_ano
from app.schemas import FaturaOut, FaturaPagar, LancamentoOut
from app.services.calculos import calcular_ano

router = APIRouter(
    prefix="/anos/{ano}/cartoes/{cartao_id}/fatura", tags=["fatura do cartão"]
)


@router.get("/{mes}", response_model=FaturaOut, summary="Fatura em aberto do mês")
def obter(
    cartao_id: int,
    mes: int = Path(..., ge=1, le=12),
    ano_ref: Ano = Depends(obter_ano),
    db: Session = Depends(get_db),
) -> FaturaOut:
    cartao = _obter_cartao(cartao_id, db)
    registro = _registro(cartao.id, ano_ref.id, mes, db)
    return FaturaOut(
        cartao_id=cartao.id,
        ano=ano_ref.ano,
        mes=mes,
        valor_em_aberto=_valor_em_aberto(cartao.id, mes, ano_ref, db),
        situacao=registro.situacao if registro else SituacaoGastoFixo.PENDENTE,
        lancamento_id=registro.lancamento_id if registro else None,
    )


@router.post(
    "/{mes}/pagar",
    response_model=LancamentoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Paga a fatura em aberto e gera a transferência",
)
def pagar(
    cartao_id: int,
    mes: int = Path(..., ge=1, le=12),
    dados: FaturaPagar | None = None,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> Lancamento:
    """Transforma a fatura em aberto numa transferência de verdade.

    É idempotente: chamar duas vezes não duplica o lançamento nem desconta o
    saldo da conta pagadora duas vezes.
    """
    cartao = _obter_cartao(cartao_id, db)
    registro = _registro(cartao.id, ano_ref.id, mes, db)

    if registro and registro.lancamento_id:
        existente = db.get(Lancamento, registro.lancamento_id)
        if existente is not None:
            return existente

    conta_pagamento_id = (
        dados.conta_pagamento_id if dados else None
    ) or cartao.conta_pagamento_padrao_id
    if conta_pagamento_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Este cartão não tem conta de pagamento padrão — informe de "
                "qual conta a fatura sai."
            ),
        )
    conta_pagamento = db.get(Conta, conta_pagamento_id)
    if conta_pagamento is None or conta_pagamento.tipo is not TipoConta.CORRENTE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A conta de pagamento precisa ser uma conta corrente.",
        )

    valor = _valor_em_aberto(cartao.id, mes, ano_ref, db)
    if valor <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Não há fatura em aberto para pagar neste mês.",
        )

    # O dia de vencimento pode não existir no mês (ex.: dia 31 em fevereiro).
    ultimo_dia = calendar.monthrange(ano_ref.ano, mes)[1]
    dia = min(cartao.dia_vencimento_fatura or ultimo_dia, ultimo_dia)

    lancamento = Lancamento(
        ano_id=ano_ref.id,
        conta_id=conta_pagamento.id,
        conta_destino_id=cartao.id,
        mes=mes,
        data=date(ano_ref.ano, mes, dia),
        valor=valor,
        tipo=TipoLancamento.TRANSFERENCIA,
        descricao=f"Pagamento da fatura — {cartao.nome}",
    )
    db.add(lancamento)
    db.flush()  # precisa do id antes de vincular

    if registro is None:
        registro = FaturaMensal(cartao_id=cartao.id, ano_id=ano_ref.id, mes=mes)
        db.add(registro)
    registro.situacao = SituacaoGastoFixo.PAGO
    registro.lancamento_id = lancamento.id

    db.commit()
    db.refresh(lancamento)
    return lancamento


@router.post(
    "/{mes}/desfazer",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desfaz o pagamento e remove o lançamento gerado",
)
def desfazer(
    cartao_id: int,
    mes: int = Path(..., ge=1, le=12),
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> None:
    cartao = _obter_cartao(cartao_id, db)
    registro = _registro(cartao.id, ano_ref.id, mes, db)
    if registro is None:
        return

    if registro.lancamento_id:
        lancamento = db.get(Lancamento, registro.lancamento_id)
        if lancamento is not None:
            db.delete(lancamento)
    registro.lancamento_id = None
    registro.situacao = SituacaoGastoFixo.PENDENTE
    db.commit()


def _obter_cartao(cartao_id: int, db: Session) -> Conta:
    cartao = db.get(Conta, cartao_id)
    if cartao is None or cartao.tipo is not TipoConta.CARTAO_CREDITO:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cartão {cartao_id} não existe.",
        )
    return cartao


def _registro(
    cartao_id: int, ano_id: int, mes: int, db: Session
) -> FaturaMensal | None:
    return (
        db.query(FaturaMensal)
        .filter(
            FaturaMensal.cartao_id == cartao_id,
            FaturaMensal.ano_id == ano_id,
            FaturaMensal.mes == mes,
        )
        .one_or_none()
    )


def _valor_em_aberto(cartao_id: int, mes: int, ano_ref: Ano, db: Session) -> Decimal:
    """Quanto devo no cartão naquele mês: sempre recalculado, nunca guardado."""
    lancamentos = (
        db.query(Lancamento)
        .options(joinedload(Lancamento.categoria))
        .filter(Lancamento.ano_id == ano_ref.id)
        .all()
    )
    tipos_conta = {c.id: c.tipo for c in db.query(Conta)}
    meses = calcular_ano(lancamentos, aberturas_do_ano(ano_ref, db), tipos_conta)
    carteira = meses[mes - 1].por_cartao.get(cartao_id)
    saldo = carteira.saldo if carteira else Decimal("0.00")
    return -saldo
