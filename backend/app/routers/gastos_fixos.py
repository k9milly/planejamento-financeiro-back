"""Endpoints dos gastos fixos (despesas recorrentes)."""

from __future__ import annotations

import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import obter_ano, obter_ano_editavel
from app.models import (
    Ano,
    GastoFixo,
    GastoFixoMensal,
    Lancamento,
    SituacaoGastoFixo,
    TipoLancamento,
)
from app.schemas import GastoFixoAtualizar, GastoFixoCriar, GastoFixoOut, LancamentoOut

router = APIRouter(prefix="/anos/{ano}/gastos-fixos", tags=["gastos fixos"])


@router.get("", response_model=list[GastoFixoOut], summary="Lista os gastos fixos")
def listar(
    ano_ref: Ano = Depends(obter_ano), db: Session = Depends(get_db)
) -> list[GastoFixo]:
    # A Query legada já deduplica as linhas do joinedload sozinha; `.unique()`
    # existe só em Result, e chamá-la aqui levanta AttributeError.
    return (
        db.query(GastoFixo)
        .options(joinedload(GastoFixo.meses))
        .filter(GastoFixo.ano_id == ano_ref.id)
        .order_by(GastoFixo.dia_vencimento, GastoFixo.descricao)
        .all()
    )


@router.post(
    "", response_model=GastoFixoOut, status_code=status.HTTP_201_CREATED,
    summary="Cria um gasto fixo",
)
def criar(
    dados: GastoFixoCriar,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> GastoFixo:
    gasto = GastoFixo(ano_id=ano_ref.id, **dados.model_dump())
    db.add(gasto)
    db.commit()
    db.refresh(gasto)
    return gasto


@router.patch("/{gasto_id}", response_model=GastoFixoOut, summary="Edita um gasto fixo")
def atualizar(
    gasto_id: int,
    dados: GastoFixoAtualizar,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> GastoFixo:
    gasto = _obter(gasto_id, ano_ref, db)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(gasto, campo, valor)
    db.commit()
    db.refresh(gasto)
    return gasto


@router.delete(
    "/{gasto_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Exclui um gasto fixo"
)
def excluir(
    gasto_id: int,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> None:
    """Remove o modelo. Os lançamentos já gerados por ele permanecem — eles
    representam dinheiro que de fato saiu da conta."""
    db.delete(_obter(gasto_id, ano_ref, db))
    db.commit()


@router.post(
    "/{gasto_id}/meses/{mes}/pagar",
    response_model=LancamentoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Marca como pago e gera o lançamento do mês",
)
def pagar(
    gasto_id: int,
    mes: int = Path(..., ge=1, le=12),
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> Lancamento:
    """Transforma o gasto fixo daquele mês em uma saída real na conta.

    É idempotente: chamar duas vezes não duplica o lançamento.
    """
    gasto = _obter(gasto_id, ano_ref, db)
    registro = (
        db.query(GastoFixoMensal)
        .filter(GastoFixoMensal.gasto_fixo_id == gasto.id, GastoFixoMensal.mes == mes)
        .one_or_none()
    )

    if registro and registro.lancamento_id:
        existente = db.get(Lancamento, registro.lancamento_id)
        if existente is not None:
            return existente

    # O dia de vencimento pode não existir no mês (ex.: dia 31 em fevereiro).
    ultimo_dia = calendar.monthrange(ano_ref.ano, mes)[1]
    vencimento = date(ano_ref.ano, mes, min(gasto.dia_vencimento, ultimo_dia))

    lancamento = Lancamento(
        ano_id=ano_ref.id,
        mes=mes,
        data=vencimento,
        valor=gasto.valor,
        tipo=TipoLancamento.SAIDA,
        categoria_id=gasto.categoria_id,
        descricao=gasto.descricao,
    )
    db.add(lancamento)
    db.flush()  # precisa do id antes de vincular

    if registro is None:
        registro = GastoFixoMensal(gasto_fixo_id=gasto.id, mes=mes)
        db.add(registro)
    registro.situacao = SituacaoGastoFixo.PAGO
    registro.lancamento_id = lancamento.id

    db.commit()
    db.refresh(lancamento)
    return lancamento


@router.post(
    "/{gasto_id}/meses/{mes}/desfazer",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desfaz o pagamento e remove o lançamento gerado",
)
def desfazer(
    gasto_id: int,
    mes: int = Path(..., ge=1, le=12),
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> None:
    gasto = _obter(gasto_id, ano_ref, db)
    registro = (
        db.query(GastoFixoMensal)
        .filter(GastoFixoMensal.gasto_fixo_id == gasto.id, GastoFixoMensal.mes == mes)
        .one_or_none()
    )
    if registro is None:
        return

    if registro.lancamento_id:
        lancamento = db.get(Lancamento, registro.lancamento_id)
        if lancamento is not None:
            db.delete(lancamento)
    registro.lancamento_id = None
    registro.situacao = SituacaoGastoFixo.PENDENTE
    db.commit()


def _obter(gasto_id: int, ano_ref: Ano, db: Session) -> GastoFixo:
    gasto = (
        db.query(GastoFixo)
        .filter(GastoFixo.id == gasto_id, GastoFixo.ano_id == ano_ref.id)
        .one_or_none()
    )
    if gasto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gasto fixo {gasto_id} não existe em {ano_ref.ano}.",
        )
    return gasto
