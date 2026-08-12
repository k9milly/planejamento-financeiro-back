"""Dependências compartilhadas entre routers."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ano, Usuario
from app.security import ler_token

# auto_error=False para responder 401 com a nossa mensagem em português em vez
# do texto padrão do FastAPI.
_esquema = HTTPBearer(auto_error=False)


def usuario_atual(
    credencial: HTTPAuthorizationCredentials | None = Depends(_esquema),
    db: Session = Depends(get_db),
) -> Usuario:
    """Exige um token válido. Aplicada a todas as rotas de dados."""
    nao_autorizado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessão inválida ou expirada. Entre novamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credencial is None:
        raise nao_autorizado

    usuario_id = ler_token(credencial.credentials)
    if usuario_id is None:
        raise nao_autorizado

    usuario = db.get(Usuario, usuario_id)
    # Um usuário desativado não pode continuar usando um token já emitido.
    if usuario is None or not usuario.ativo:
        raise nao_autorizado

    return usuario

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
