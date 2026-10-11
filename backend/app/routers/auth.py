"""Login, sessão, espaço ativo e exclusão da própria conta.

Não existe endpoint de cadastro **ainda**: usuários são criados pelo script
`scripts/criar_usuario.py`, rodado por quem administra a instalação. O
cadastro aberto é o ADR-16, e depende do ADR-17 (limite de tentativas) estar
no ar antes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import usuario_atual
from app.models import Espaco, MembroEspaco, PapelMembro, Usuario
from app.security import conferir_senha, criar_token

router = APIRouter(prefix="/auth", tags=["autenticação"])


class Credenciais(BaseModel):
    email: EmailStr
    senha: str


class TokenOut(BaseModel):
    token: str
    email: str


class EspacoDoUsuario(BaseModel):
    """Um espaço de que a pessoa participa, com o papel dela nele."""

    id: int
    nome: str
    papel: PapelMembro


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    # `None` = nunca preencheu; a interface cai no e-mail nesse caso (ADR-06).
    nome: str | None
    alertas_email_ativo: bool
    # Se a tela mostra a seção de orçamento por categoria (ADR-11).
    mostrar_orcamento_categoria: bool

    # Qual espaço esta sessão está vendo. `None` significa que a pessoa não
    # escolheu nenhum — e nesse estado **toda** consulta de dado financeiro
    # volta vazia (ver `app/espaco.py`). A tela precisa tratar isso como "pedir
    # para escolher um espaço", não como "não tem nada cadastrado": as duas
    # situações chegam ao frontend com listas vazias e significam coisas
    # opostas.
    espaco_atual_id: int | None = None

    # Todos os espaços de que ela participa, para o seletor. Vem junto do
    # `/auth/eu` porque é a chamada que a tela já faz na abertura — uma rota
    # separada só para isso seria uma ida a mais ao servidor em toda carga.
    espacos: list[EspacoDoUsuario] = []


class EspacoAtualAtualizar(BaseModel):
    espaco_id: int


class ExclusaoDaConta(BaseModel):
    """Senha de novo para apagar a própria conta.

    A ação é irreversível, e um token já aberto pode ter sido sequestrado —
    sessão válida não basta.
    """

    senha: str


class UsuarioAtualizar(BaseModel):
    """Atualização parcial do próprio perfil. Só o que a pessoa pode mudar
    sobre si — e-mail e senha ficam de fora: trocar e-mail é trocar de
    identidade, e senha se muda pelo script de administração."""

    nome: str | None = Field(default=None, max_length=120)
    alertas_email_ativo: bool | None = None
    mostrar_orcamento_categoria: bool | None = None


def _montar_usuario_out(db: Session, usuario: Usuario) -> UsuarioOut:
    """`UsuarioOut` com os espaços da pessoa anexados.

    A consulta é explícita porque `MembroEspaco` e `Espaco` ficam **fora** do
    filtro automático de espaço: é justamente aqui que a pessoa precisa ver
    espaços que não são o ativo, senão nunca conseguiria trocar.
    """
    vinculos = (
        db.query(MembroEspaco, Espaco)
        .join(Espaco, Espaco.id == MembroEspaco.espaco_id)
        .filter(MembroEspaco.usuario_id == usuario.id)
        .order_by(Espaco.nome)
        .all()
    )
    saida = UsuarioOut.model_validate(usuario)
    saida.espacos = [
        EspacoDoUsuario(id=espaco.id, nome=espaco.nome, papel=vinculo.papel)
        for vinculo, espaco in vinculos
    ]
    return saida


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
def eu(
    usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)
) -> UsuarioOut:
    """Usada pelo frontend na abertura, para saber se o token guardado ainda
    vale antes de mostrar a tela principal — e, desde o ADR-15, para saber em
    qual espaço a sessão está e quais existem para escolher."""
    return _montar_usuario_out(db, usuario)


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
    return _montar_usuario_out(db, usuario)


@router.patch(
    "/espaco-atual", response_model=UsuarioOut, summary="Troca o espaço ativo"
)
def trocar_espaco_atual(
    dados: EspacoAtualAtualizar,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> UsuarioOut:
    """Muda qual espaço esta pessoa enxerga, como um seletor de área de trabalho.

    A troca **não** vale para a requisição em curso: o espaço já foi fixado na
    sessão por `usuario_atual` antes deste código rodar, e refixar aqui faria o
    filtro mudar no meio do caminho. Vale do próximo pedido em diante, que é o
    que a tela faz de qualquer forma — ela recarrega os dados depois de trocar.
    """
    e_membro = (
        db.query(MembroEspaco.id)
        .filter(
            MembroEspaco.espaco_id == dados.espaco_id,
            MembroEspaco.usuario_id == usuario.id,
        )
        .first()
    )
    # 422, não 403: para quem não participa, esse id não é um espaço ao qual o
    # acesso foi negado — é um valor inválido para o campo. E a mensagem não
    # distingue "não existe" de "não é seu", para não confirmar a existência de
    # espaços de outras pessoas.
    if e_membro is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Espaço inválido ou você não participa dele.",
        )

    usuario.espaco_atual_id = dados.espaco_id
    db.commit()
    db.refresh(usuario)
    return _montar_usuario_out(db, usuario)


@router.delete(
    "/eu", status_code=status.HTTP_204_NO_CONTENT, summary="Apaga a própria conta"
)
def apagar_eu(
    dados: ExclusaoDaConta,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> None:
    """Exclusão de verdade, não desativação (ADR-15 — direito ao esquecimento).

    Três situações, e a do meio é a que protege outras pessoas:

    - **Dona de um espaço sem mais ninguém dentro:** apaga o espaço inteiro. O
      `ondelete=CASCADE` de `espaco_id` leva as catorze tabelas junto.
    - **Dona de um espaço com outros membros:** `409`. Apagar levaria embora o
      dinheiro de quem ficou; a responsabilidade precisa sair primeiro.
    - **Só membro:** sai dos espaços, e eles continuam existindo para os
      outros.
    """
    if not conferir_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Senha incorreta."
        )

    vinculos = (
        db.query(MembroEspaco)
        .filter(MembroEspaco.usuario_id == usuario.id)
        .all()
    )

    espacos_a_apagar: list[int] = []
    for vinculo in vinculos:
        if vinculo.papel != PapelMembro.DONO:
            continue
        outros = (
            db.query(MembroEspaco.id)
            .filter(
                MembroEspaco.espaco_id == vinculo.espaco_id,
                MembroEspaco.usuario_id != usuario.id,
            )
            .first()
        )
        if outros is not None:
            nome = db.get(Espaco, vinculo.espaco_id).nome
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Você é responsável pelo espaço '{nome}', que tem outras "
                    "pessoas dentro. Transfira a responsabilidade ou remova os "
                    "membros antes de apagar sua conta."
                ),
            )
        espacos_a_apagar.append(vinculo.espaco_id)

    # O usuário sai primeiro: `usuarios.espaco_atual_id` aponta para `espacos`,
    # e apagar o espaço antes dispararia o `SET NULL` numa linha que vai deixar
    # de existir de todo modo.
    db.delete(usuario)
    db.flush()

    for espaco_id in espacos_a_apagar:
        espaco = db.get(Espaco, espaco_id)
        if espaco is not None:
            db.delete(espaco)

    db.commit()
