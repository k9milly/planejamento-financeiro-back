"""Regras de categorização usadas pela importação de extrato."""

from __future__ import annotations

import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Categoria, RegraCategorizacao
from app.schemas import RegraCriar, RegraOut

router = APIRouter(prefix="/regras", tags=["regras"])


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).upper()


@router.get("", response_model=list[RegraOut], summary="Lista as regras")
def listar(db: Session = Depends(get_db)) -> list[RegraCategorizacao]:
    return (
        db.query(RegraCategorizacao)
        .options(joinedload(RegraCategorizacao.categoria))
        .order_by(RegraCategorizacao.padrao)
        .all()
    )


@router.post(
    "", response_model=RegraOut, status_code=status.HTTP_201_CREATED,
    summary="Cria ou atualiza uma regra",
)
def criar(dados: RegraCriar, db: Session = Depends(get_db)) -> RegraCategorizacao:
    """Se o padrão já existir, aponta para a nova categoria em vez de recusar —
    corrigir uma regra é mais comum do que criar uma duplicada por engano."""
    if db.get(Categoria, dados.categoria_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Categoria {dados.categoria_id} não existe.",
        )

    padrao = normalizar(dados.padrao.strip())
    regra = (
        db.query(RegraCategorizacao)
        .filter(RegraCategorizacao.padrao == padrao)
        .one_or_none()
    )

    if regra is None:
        regra = RegraCategorizacao(padrao=padrao, categoria_id=dados.categoria_id)
        db.add(regra)
    else:
        regra.categoria_id = dados.categoria_id

    db.commit()
    db.refresh(regra)
    return regra


@router.delete(
    "/{regra_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove uma regra"
)
def excluir(regra_id: int, db: Session = Depends(get_db)) -> None:
    regra = db.get(RegraCategorizacao, regra_id)
    if regra is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {regra_id} não existe.",
        )
    db.delete(regra)
    db.commit()
