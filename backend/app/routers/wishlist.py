"""Endpoints da wishlist (lista de desejos)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import obter_ano, obter_ano_editavel
from app.models import Ano, ItemWishlist
from app.schemas import DesejoAtualizar, DesejoCriar, DesejoOut

router = APIRouter(prefix="/anos/{ano}/wishlist", tags=["wishlist"])


class TotalWishlist(BaseModel):
    """Total dos itens marcados — equivale à coluna SOMAR da planilha."""

    total_marcado: Decimal
    total_geral: Decimal
    quantidade_marcada: int


@router.get("", response_model=list[DesejoOut], summary="Lista os desejos")
def listar(
    ano_ref: Ano = Depends(obter_ano), db: Session = Depends(get_db)
) -> list[ItemWishlist]:
    return (
        db.query(ItemWishlist)
        .filter(ItemWishlist.ano_id == ano_ref.id)
        .order_by(ItemWishlist.comprado, ItemWishlist.desejo)
        .all()
    )


@router.get("/total", response_model=TotalWishlist, summary="Soma dos itens marcados")
def total(
    ano_ref: Ano = Depends(obter_ano), db: Session = Depends(get_db)
) -> TotalWishlist:
    itens = (
        db.query(ItemWishlist)
        .filter(ItemWishlist.ano_id == ano_ref.id, ItemWishlist.comprado.is_(False))
        .all()
    )
    marcados = [i for i in itens if i.somar]
    return TotalWishlist(
        total_marcado=sum((Decimal(str(i.valor)) for i in marcados), Decimal("0.00")),
        total_geral=sum((Decimal(str(i.valor)) for i in itens), Decimal("0.00")),
        quantidade_marcada=len(marcados),
    )


@router.post(
    "", response_model=DesejoOut, status_code=status.HTTP_201_CREATED,
    summary="Adiciona um desejo",
)
def criar(
    dados: DesejoCriar,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> ItemWishlist:
    item = ItemWishlist(ano_id=ano_ref.id, **dados.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=DesejoOut, summary="Edita um desejo")
def atualizar(
    item_id: int,
    dados: DesejoAtualizar,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> ItemWishlist:
    item = _obter(item_id, ano_ref, db)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(item, campo, valor)
    db.commit()
    db.refresh(item)
    return item


@router.delete(
    "/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove um desejo"
)
def excluir(
    item_id: int,
    ano_ref: Ano = Depends(obter_ano_editavel),
    db: Session = Depends(get_db),
) -> None:
    db.delete(_obter(item_id, ano_ref, db))
    db.commit()


def _obter(item_id: int, ano_ref: Ano, db: Session) -> ItemWishlist:
    item = (
        db.query(ItemWishlist)
        .filter(ItemWishlist.id == item_id, ItemWishlist.ano_id == ano_ref.id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Desejo {item_id} não existe em {ano_ref.ano}.",
        )
    return item
