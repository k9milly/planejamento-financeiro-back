"""Login e sessão.

Não existe endpoint de cadastro de propósito: usuários são criados pelo script
`scripts/criar_usuario.py`, rodado por quem administra a instalação. Um app de
finanças pessoais publicado na internet não tem motivo para aceitar cadastro
aberto.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import usuario_atual
from app.models import Usuario
from app.security import conferir_senha, criar_token

router = APIRouter(prefix="/auth", tags=["autenticação"])


class Credenciais(BaseModel):
    email: EmailStr
    senha: str


class TokenOut(BaseModel):
    token: str
    email: str


class UsuarioOut(BaseModel):
    id: int
    email: str


@router.post("/login", response_model=TokenOut, summary="Entra no sistema")
def login(dados: Credenciais, db: Session = Depends(get_db)) -> TokenOut:
    usuario = (
        db.query(Usuario)
        .filter(Usuario.email == dados.email.lower().strip())
        .one_or_none()
    )

    # A mesma mensagem para e-mail inexistente e senha errada: dizer qual dos
    # dois falhou entregaria a um atacante a lista de e-mails cadastrados.
    if (
        usuario is None
        or not usuario.ativo
        or not conferir_senha(dados.senha, usuario.senha_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    return TokenOut(token=criar_token(usuario.id), email=usuario.email)


@router.get("/eu", response_model=UsuarioOut, summary="Quem está logado")
def eu(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    """Usada pelo frontend na abertura, para saber se o token guardado ainda
    vale antes de mostrar a tela principal."""
    return usuario
