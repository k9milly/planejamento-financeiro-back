"""Endpoints de categorias. São globais: valem para todos os anos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Categoria, Lancamento
from app.schemas import CategoriaAtualizar, CategoriaCriar, CategoriaOut

router = APIRouter(prefix="/categorias", tags=["categorias"])


@router.get("", response_model=list[CategoriaOut], summary="Lista as categorias")
def listar(
    incluir_inativas: bool = False, db: Session = Depends(get_db)
) -> list[Categoria]:
    consulta = db.query(Categoria)
    if not incluir_inativas:
        consulta = consulta.filter(Categoria.ativa.is_(True))
    return consulta.order_by(Categoria.nome).all()


@router.post(
    "", response_model=CategoriaOut, status_code=status.HTTP_201_CREATED,
    summary="Cria uma categoria",
)
def criar(dados: CategoriaCriar, db: Session = Depends(get_db)) -> Categoria:
    if db.query(Categoria).filter(Categoria.nome == dados.nome).one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma categoria chamada '{dados.nome}'.",
        )
    categoria = Categoria(**dados.model_dump())
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return categoria


@router.patch(
    "/{categoria_id}", response_model=CategoriaOut, summary="Edita uma categoria"
)
def atualizar(
    categoria_id: int, dados: CategoriaAtualizar, db: Session = Depends(get_db)
) -> Categoria:
    categoria = _obter(categoria_id, db)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(categoria, campo, valor)
    db.commit()
    db.refresh(categoria)
    return categoria


@router.delete(
    "/{categoria_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui (ou desativa) uma categoria",
)
def excluir(categoria_id: int, db: Session = Depends(get_db)) -> None:
    """Categorias em uso não são apagadas, apenas desativadas.

    Apagar de verdade deixaria lançamentos históricos órfãos e mudaria os
    totais por categoria de meses já fechados.
    """
    categoria = _obter(categoria_id, db)
    em_uso = (
        db.query(Lancamento).filter(Lancamento.categoria_id == categoria_id).count()
    )
    if em_uso:
        categoria.ativa = False
    else:
        db.delete(categoria)
    db.commit()


def _obter(categoria_id: int, db: Session) -> Categoria:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Categoria {categoria_id} não existe.",
        )
    return categoria
