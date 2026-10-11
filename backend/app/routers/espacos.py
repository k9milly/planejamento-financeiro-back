"""Endpoints do espaço financeiro: quem participa, nome, exportar (ADR-15).

## Por que estas rotas filtram na mão

`Espaco` e `MembroEspaco` **não** herdam `ComEspaco`, logo não entram no
filtro automático de `app/espaco.py`. Isso é de propósito: para trocar de
espaço, a pessoa precisa conseguir listar espaços que **não** são o ativo —
e o filtro automático, por definição, só deixa ver o ativo.

O preço é que a checagem de permissão aqui é explícita, feita pelas
dependências `membro_do_espaco` e `dono_do_espaco`. São as únicas consultas
do sistema que decidem acesso por conta própria; todo o resto confia na
sessão. Quanto menor esse conjunto, menor a superfície para errar.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import usuario_atual
from app.espaco import fixar_espaco, modelos_protegidos
from app.models import Espaco, MembroEspaco, PapelMembro, Usuario

router = APIRouter(prefix="/espacos", tags=["espaços"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class MembroOut(BaseModel):
    usuario_id: int
    email: str
    nome: str | None
    papel: PapelMembro
    entrou_em: dt.datetime


class EspacoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    criado_em: dt.datetime


class EspacoDetalhe(EspacoOut):
    membros: list[MembroOut]


class EspacoAtualizar(BaseModel):
    nome: str = Field(min_length=1, max_length=80)


# --------------------------------------------------------------------------- #
# Permissão
# --------------------------------------------------------------------------- #
def membro_do_espaco(
    espaco_id: int = Path(..., description="Id do espaço"),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> Espaco:
    """Exige que quem está logado participe deste espaço.

    Responde **404**, e não 403, para espaço que existe mas não é seu: um 403
    confirmaria que aquele id existe, o que já é informação sobre outra
    família. Para quem não participa, o espaço simplesmente não existe.
    """
    vinculo = (
        db.query(MembroEspaco)
        .filter(
            MembroEspaco.espaco_id == espaco_id,
            MembroEspaco.usuario_id == usuario.id,
        )
        .one_or_none()
    )
    if vinculo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Espaço não encontrado."
        )
    return vinculo.espaco


def _papel_de(db: Session, espaco_id: int, usuario_id: int) -> PapelMembro | None:
    return (
        db.query(MembroEspaco.papel)
        .filter(
            MembroEspaco.espaco_id == espaco_id,
            MembroEspaco.usuario_id == usuario_id,
        )
        .scalar()
    )


def dono_do_espaco(
    espaco: Espaco = Depends(membro_do_espaco),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> Espaco:
    if _papel_de(db, espaco.id, usuario.id) != PapelMembro.DONO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Só quem é responsável pelo espaço pode fazer isso.",
        )
    return espaco


def montar_membros(db: Session, espaco_id: int) -> list[MembroOut]:
    vinculos = (
        db.query(MembroEspaco, Usuario)
        .join(Usuario, Usuario.id == MembroEspaco.usuario_id)
        .filter(MembroEspaco.espaco_id == espaco_id)
        .order_by(MembroEspaco.entrou_em, MembroEspaco.id)
        .all()
    )
    return [
        MembroOut(
            usuario_id=pessoa.id,
            email=pessoa.email,
            nome=pessoa.nome,
            papel=vinculo.papel,
            entrou_em=vinculo.entrou_em,
        )
        for vinculo, pessoa in vinculos
    ]


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@router.get(
    "/{espaco_id}", response_model=EspacoDetalhe, summary="Detalhes de um espaço"
)
def detalhar(
    espaco: Espaco = Depends(membro_do_espaco), db: Session = Depends(get_db)
) -> EspacoDetalhe:
    return EspacoDetalhe(
        id=espaco.id,
        nome=espaco.nome,
        criado_em=espaco.criado_em,
        membros=montar_membros(db, espaco.id),
    )


@router.get(
    "/{espaco_id}/membros",
    response_model=list[MembroOut],
    summary="Quem participa do espaço",
)
def listar_membros(
    espaco: Espaco = Depends(membro_do_espaco), db: Session = Depends(get_db)
) -> list[MembroOut]:
    """A mesma lista que vem dentro de `GET /espacos/{id}`.

    Existe separada porque é assim que a seção 20 da especificação a declara,
    e a tela de membros não precisa do resto do espaço para se atualizar
    depois de remover alguém.
    """
    return montar_membros(db, espaco.id)


@router.patch("/{espaco_id}", response_model=EspacoOut, summary="Renomeia o espaço")
def renomear(
    dados: EspacoAtualizar,
    espaco: Espaco = Depends(dono_do_espaco),
    db: Session = Depends(get_db),
) -> Espaco:
    espaco.nome = dados.nome.strip()
    db.commit()
    db.refresh(espaco)
    return espaco


@router.delete(
    "/{espaco_id}/membros/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove alguém do espaço",
)
def remover_membro(
    usuario_id: int,
    espaco: Espaco = Depends(dono_do_espaco),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> None:
    """Só quem é dono remove, e nunca a si mesmo.

    É o que a seção 20 da especificação escreve, palavra por palavra. A
    consequência está anotada no `CONTRATO-API.md` como lacuna: **um membro
    não tem como sair de um espaço por conta própria** — ou o dono o remove,
    ou ele apaga a conta inteira em `DELETE /auth/eu`. Implementar "sair" por
    iniciativa própria seria inventar contrato, e isso fica para ela decidir.
    """
    alvo = (
        db.query(MembroEspaco)
        .filter(
            MembroEspaco.espaco_id == espaco.id,
            MembroEspaco.usuario_id == usuario_id,
        )
        .one_or_none()
    )
    if alvo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Essa pessoa não participa deste espaço.",
        )

    if usuario_id == usuario.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Você é responsável por este espaço e não pode se remover. "
                "Transfira a responsabilidade primeiro."
            ),
        )

    # Quem sai não pode continuar com esse espaço selecionado: ficaria logado
    # vendo um espaço a que não pertence mais. Vira `NULL`, e a tela manda
    # escolher outro.
    pessoa = db.get(Usuario, usuario_id)
    if pessoa is not None and pessoa.espaco_atual_id == espaco.id:
        pessoa.espaco_atual_id = None

    db.delete(alvo)
    db.commit()


# --------------------------------------------------------------------------- #
# Exportar (LGPD — direito de acesso)
# --------------------------------------------------------------------------- #
def _converter(valor):
    """Tipos do banco para tipos que viram JSON sem perder exatidão.

    `Decimal` sai como **string**, pela mesma razão do resto da API: `float`
    arredonda dinheiro.
    """
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, (dt.datetime, dt.date)):
        return valor.isoformat()
    return valor


@router.get(
    "/{espaco_id}/exportar",
    summary="Exporta tudo o que existe no espaço (JSON)",
)
def exportar(
    espaco: Espaco = Depends(membro_do_espaco), db: Session = Depends(get_db)
) -> dict:
    """Todas as linhas das catorze tabelas de dinheiro deste espaço.

    Duas coisas importam aqui:

    1. **O espaço da sessão é refixado para o espaço pedido.** Sem isso, pedir
       a exportação de um espaço que não é o ativo devolveria, em silêncio, os
       dados do ativo — com o nome do outro no cabeçalho. É o engano mais
       perigoso possível nesta rota, e o filtro automático o produziria sem
       reclamar. Refixar é seguro porque `membro_do_espaco` já confirmou a
       participação, e a sessão morre no fim da requisição.
    2. **As tabelas vêm de `modelos_protegidos()`**, a mesma descoberta por
       herança que o filtro usa. Uma tabela de dinheiro nova entra na
       exportação sozinha; uma lista escrita à mão aqui ficaria para trás, e a
       exportação sairia incompleta sem ninguém notar.
    """
    fixar_espaco(db, espaco.id)

    dados: dict[str, list[dict]] = {}
    for modelo in sorted(modelos_protegidos(), key=lambda m: m.__tablename__):
        colunas = [coluna.key for coluna in modelo.__mapper__.columns]
        dados[modelo.__tablename__] = [
            {nome: _converter(getattr(linha, nome)) for nome in colunas}
            for linha in db.query(modelo).all()
        ]

    return {
        "espaco": {
            "id": espaco.id,
            "nome": espaco.nome,
            "criado_em": espaco.criado_em.isoformat(),
        },
        "membros": [m.model_dump(mode="json") for m in montar_membros(db, espaco.id)],
        "dados": dados,
    }
