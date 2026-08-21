"""Endpoints de contas: Nubank, Mercado Pago, dinheiro em espécie.

São globais, não por ano: o Nubank de 2026 é o mesmo de 2027.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conta, FaturaMensal, GastoFixo, Lancamento, TipoConta
from app.schemas import ContaAtualizar, ContaCriar, ContaOut, _validar_coerencia_conta

router = APIRouter(prefix="/contas", tags=["contas"])


@router.get("", response_model=list[ContaOut], summary="Lista as contas")
def listar(
    incluir_inativas: bool = False,
    tipo: TipoConta | None = None,
    db: Session = Depends(get_db),
) -> list[Conta]:
    consulta = db.query(Conta)
    if not incluir_inativas:
        consulta = consulta.filter(Conta.ativa.is_(True))
    if tipo is not None:
        consulta = consulta.filter(Conta.tipo == tipo)
    return consulta.order_by(Conta.ordem, Conta.nome).all()


@router.post(
    "", response_model=ContaOut, status_code=status.HTTP_201_CREATED,
    summary="Cria uma conta",
)
def criar(dados: ContaCriar, db: Session = Depends(get_db)) -> Conta:
    if db.query(Conta).filter(Conta.nome == dados.nome).one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma conta chamada '{dados.nome}'.",
        )
    conta = Conta(**dados.model_dump())
    db.add(conta)
    db.commit()
    db.refresh(conta)
    return conta


@router.patch("/{conta_id}", response_model=ContaOut, summary="Edita uma conta")
def atualizar(
    conta_id: int, dados: ContaAtualizar, db: Session = Depends(get_db)
) -> Conta:
    conta = _obter(conta_id, db)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(conta, campo, valor)

    def erro(mensagem: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=mensagem
        )

    _validar_coerencia_conta(
        conta.tipo, conta.dia_vencimento_fatura, conta.conta_pagamento_padrao_id, erro
    )

    db.commit()
    db.refresh(conta)
    return conta


@router.delete(
    "/{conta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui (ou desativa) uma conta",
)
def excluir(conta_id: int, db: Session = Depends(get_db)) -> None:
    """Contas com movimentação não são apagadas, apenas desativadas.

    Apagar deixaria lançamentos órfãos e mudaria retroativamente os saldos de
    meses já fechados. Uma conta desativada some dos formulários mas continua
    aparecendo no histórico.
    """
    conta = _obter(conta_id, db)

    em_uso = (
        db.query(Lancamento)
        .filter(
            (Lancamento.conta_id == conta_id)
            | (Lancamento.conta_destino_id == conta_id)
        )
        .count()
        or db.query(GastoFixo).filter(GastoFixo.conta_id == conta_id).count()
        or db.query(FaturaMensal).filter(FaturaMensal.cartao_id == conta_id).count()
    )

    if em_uso:
        conta.ativa = False
    else:
        db.delete(conta)
    db.commit()


def _obter(conta_id: int, db: Session) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta {conta_id} não existe.",
        )
    return conta
