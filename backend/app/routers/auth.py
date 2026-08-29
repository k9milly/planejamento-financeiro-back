"""Login e sessão.

Não existe endpoint de cadastro de propósito: usuários são criados pelo script
`scripts/criar_usuario.py`, rodado por quem administra a instalação. Um app de
finanças pessoais publicado na internet não tem motivo para aceitar cadastro
aberto.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
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
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    # `None` = nunca preencheu; a interface cai no e-mail nesse caso (ADR-06).
    nome: str | None
    alertas_email_ativo: bool


class UsuarioAtualizar(BaseModel):
    """Atualização parcial do próprio perfil. Só o que a pessoa pode mudar
    sobre si — e-mail e senha ficam de fora: trocar e-mail é trocar de
    identidade, e senha se muda pelo script de administração."""

    nome: str | None = Field(default=None, max_length=120)
    alertas_email_ativo: bool | None = None


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


@router.patch("/eu", response_model=UsuarioOut, summary="Edita o próprio perfil")
def atualizar_eu(
    dados: UsuarioAtualizar,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> Usuario:
    """Só mexe em quem está logado — não recebe id, para não existir a rota
    'editar o perfil de outra pessoa' num app sem noção de administrador.

    Nome em branco volta a `None` (e não string vazia), para "não preencheu" e
    "apagou o que tinha" serem o mesmo estado para quem lê.
    """
    alteracoes = dados.model_dump(exclude_unset=True)
    if "nome" in alteracoes:
        nome = (alteracoes["nome"] or "").strip()
        alteracoes["nome"] = nome or None

    for campo, valor in alteracoes.items():
        setattr(usuario, campo, valor)

    db.commit()
    db.refresh(usuario)
    return usuario
