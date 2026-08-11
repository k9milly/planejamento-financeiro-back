"""Dependências compartilhadas entre routers."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ano

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def obter_ano(
    ano: int = Path(..., description="Ano-calendário, ex.: 2026"),
    db: Session = Depends(get_db),
) -> Ano:
    registro = db.query(Ano).filter(Ano.ano == ano).one_or_none()
    if registro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"O ano {ano} ainda não foi criado.",
        )
    return registro


def obter_ano_editavel(ano_ref: Ano = Depends(obter_ano)) -> Ano:
    """Como `obter_ano`, mas recusa anos arquivados.

    Arquivar é o gesto de "fechar o livro" do ano: os dados continuam
    consultáveis, mas não devem mudar mais.
    """
    if ano_ref.arquivado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O ano {ano_ref.ano} está arquivado e é somente leitura. "
                "Desarquive-o para poder editar."
            ),
        )
    return ano_ref
