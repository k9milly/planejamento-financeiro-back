"""Endpoints dos lançamentos — o container principal de cada mês."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Ano, Categoria, Conta, Lancamento, TipoLancamento
from app.deps import obter_ano, obter_ano_editavel
from app.schemas import (
    LancamentoAtualizar,
    LancamentoCriar,
    LancamentoOut,
    validar_coerencia,
)

router = APIRouter(prefix="/anos/{ano}/lancamentos", tags=["lançamentos"])


@router.get("", response_model=list[LancamentoOut], summary="Lista lançamentos")
def listar(
    mes: int | None = Query(default=None, ge=1, le=12),
    tipo: TipoLancamento | None = None,
    categoria_id: int | None = None,
    conta_id: int | None = None,
    ano_ref: Ano = Depends(obter_ano),
    db: Session = Depends(get_db),
) -> list[Lancamento]:
    consulta = (
        db.query(Lancamento)
        .options(joinedload(Lancamento.categoria), joinedload(Lancamento.conta))
        .filter(Lancamento.ano_id == ano_ref.id)
    )
    if mes is not None:
        consulta = consulta.filter(Lancamento.mes == mes)
    if tipo is not None:
        consulta = consulta.filter(Lancamento.tipo == tipo)
    if categoria_id is not None:
        consulta = consulta.filter(Lancamento.categoria_id == categoria_id)
    if conta_id is not None:
        # Numa transferência a conta aparece nos dois lados: filtrar só pela
        # origem esconderia o dinheiro que entrou na conta consultada.
        consulta = consulta.filter(
            (Lancamento.conta_id == conta_id)
            | (Lancamento.conta_destino_id == conta_id)
        )

    return consulta.order_by(Lancamento.data, Lancamento.id).all()


@router.post(
    "", response_model=LancamentoOut, status_code=status.HTTP_201_CREATED,
    summary="Cria um lançamento",
)
def criar(
    dados: LancamentoCriar,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> Lancamento:
    _validar_data_no_ano(dados.data.year, ano_ref)
    _validar_categoria(dados.categoria_id, db)
    _validar_conta(dados.conta_id, db)
    _validar_conta(dados.conta_destino_id, db)

    lanc = Lancamento(
        ano_id=ano_ref.id,
        # O mês vem da data, nunca é informado à parte: assim eles não divergem.
        mes=dados.data.month,
        **dados.model_dump(),
    )
    db.add(lanc)
    db.commit()
    db.refresh(lanc)
    return lanc


@router.patch(
    "/{lancamento_id}", response_model=LancamentoOut, summary="Edita um lançamento"
)
def atualizar(
    lancamento_id: int,
    dados: LancamentoAtualizar,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> Lancamento:
    lanc = _obter(lancamento_id, ano_ref, db)
    alteracoes = dados.model_dump(exclude_unset=True)

    for campo, valor in alteracoes.items():
        setattr(lanc, campo, valor)

    if "data" in alteracoes:
        _validar_data_no_ano(lanc.data.year, ano_ref)
        lanc.mes = lanc.data.month
    if "categoria_id" in alteracoes:
        _validar_categoria(lanc.categoria_id, db)
    if "conta_id" in alteracoes:
        _validar_conta(lanc.conta_id, db)
    if "conta_destino_id" in alteracoes:
        _validar_conta(lanc.conta_destino_id, db)

    _validar_coerencia(lanc)

    db.commit()
    db.refresh(lanc)
    return lanc


@router.delete(
    "/{lancamento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um lançamento",
)
def excluir(
    lancamento_id: int,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> None:
    db.delete(_obter(lancamento_id, ano_ref, db))
    db.commit()


def _obter(lancamento_id: int, ano_ref: Ano, db: Session) -> Lancamento:
    lanc = (
        db.query(Lancamento)
        .filter(Lancamento.id == lancamento_id, Lancamento.ano_id == ano_ref.id)
        .one_or_none()
    )
    if lanc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lançamento {lancamento_id} não existe em {ano_ref.ano}.",
        )
    return lanc


def _validar_data_no_ano(ano_da_data: int, ano_ref: Ano) -> None:
    if ano_da_data != ano_ref.ano:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"A data é de {ano_da_data}, mas o lançamento está sendo salvo "
                f"em {ano_ref.ano}."
            ),
        )


def _validar_categoria(categoria_id: int | None, db: Session) -> None:
    if categoria_id is None:
        return
    if db.get(Categoria, categoria_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Categoria {categoria_id} não existe.",
        )


def _validar_conta(conta_id: int | None, db: Session) -> None:
    if conta_id is None:
        return
    if db.get(Conta, conta_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Conta {conta_id} não existe.",
        )


def _validar_coerencia(lanc: Lancamento) -> None:
    """Mesmas regras do schema de criação, aplicadas ao objeto já mesclado.

    Necessário porque um PATCH pode mudar só o tipo, deixando um `destino`, uma
    `categoria` ou uma conta de destino que eram válidos antes e deixaram de
    ser.
    """

    def erro(mensagem: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=mensagem
        )

    validar_coerencia(
        lanc.tipo,
        lanc.destino,
        lanc.categoria_id,
        lanc.conta_id,
        lanc.conta_destino_id,
        erro,
    )
