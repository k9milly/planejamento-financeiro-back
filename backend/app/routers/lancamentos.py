"""Endpoints dos lançamentos — o container principal de cada mês."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Ano, Caixinha, Categoria, Conta, Lancamento, TipoLancamento
from app.deps import obter_ano, obter_ano_editavel
from app.services.caixinhas import exigir_caixinha, garantir_nao_negativas
from app.schemas import (
    LancamentoAtualizar,
    LancamentoCriar,
    LancamentoOut,
    validar_coerencia,
    validar_conta_compativel,
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
    conta = _validar_conta(dados.conta_id, db)
    _validar_conta(dados.conta_destino_id, db)
    _validar_conta_compativel(dados.tipo, dados.forma_pagamento, conta)
    _validar_caixinha(dados.caixinha_id, dados.conta_id, db)
    _validar_caixinha(dados.caixinha_destino_id, dados.conta_id, db)
    _exigir_caixinha(dados.conta_id, dados.tipo, dados.destino, dados.caixinha_id, db)

    lanc = Lancamento(
        ano_id=ano_ref.id,
        # O mês vem da data, nunca é informado à parte: assim eles não divergem.
        mes=dados.data.month,
        **dados.model_dump(),
    )
    db.add(lanc)
    _garantir_caixinhas_positivas(
        db, {dados.caixinha_id, dados.caixinha_destino_id}
    )
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
    # As de antes entram na conferência junto com as novas: tirar um `guardado`
    # de uma caixinha a esvazia tanto quanto retirar dela.
    afetadas = {lanc.caixinha_id, lanc.caixinha_destino_id}

    for campo, valor in alteracoes.items():
        setattr(lanc, campo, valor)

    if "data" in alteracoes:
        _validar_data_no_ano(lanc.data.year, ano_ref)
        lanc.mes = lanc.data.month
    if "categoria_id" in alteracoes:
        _validar_categoria(lanc.categoria_id, db)
    if "conta_destino_id" in alteracoes:
        _validar_conta(lanc.conta_destino_id, db)

    _validar_coerencia(lanc)
    conta = _validar_conta(lanc.conta_id, db)
    _validar_conta_compativel(lanc.tipo, lanc.forma_pagamento, conta)
    # Sempre revalidadas, mesmo sem virem no PATCH: mudar só a `conta_id`
    # deixaria a caixinha antiga apontando para outra conta.
    _validar_caixinha(lanc.caixinha_id, lanc.conta_id, db)
    _validar_caixinha(lanc.caixinha_destino_id, lanc.conta_id, db)
    _exigir_caixinha(lanc.conta_id, lanc.tipo, lanc.destino, lanc.caixinha_id, db)

    _garantir_caixinhas_positivas(
        db, afetadas | {lanc.caixinha_id, lanc.caixinha_destino_id}
    )
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
    """Apagar também precisa ser conferido.

    Apagar o `guardado` que financiou uma retirada posterior deixa a caixinha
    negativa sem que ninguém tenha retirado nada a mais — o saldo é derivado,
    então some o depósito e sobra só a saída.
    """
    lanc = _obter(lancamento_id, ano_ref, db)
    afetadas = {lanc.caixinha_id, lanc.caixinha_destino_id}

    db.delete(lanc)
    _garantir_caixinhas_positivas(db, afetadas)
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


def _validar_conta(conta_id: int | None, db: Session) -> Conta | None:
    if conta_id is None:
        return None
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Conta {conta_id} não existe.",
        )
    return conta


def _validar_conta_compativel(
    tipo: TipoLancamento, forma_pagamento, conta: Conta | None
) -> None:
    if conta is None:
        return

    def erro(mensagem: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=mensagem
        )

    validar_conta_compativel(tipo, forma_pagamento, conta.tipo, erro)


def _erro_422(mensagem: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=mensagem
    )


def _exigir_caixinha(conta_id, tipo, destino, caixinha_id, db: Session) -> None:
    """Conta com caixinhas não aceita guardado nem retirado solto (ADR-10)."""
    exigir_caixinha(conta_id, tipo, destino, caixinha_id, db, _erro_422)


def _garantir_caixinhas_positivas(db: Session, ids: set[int | None]) -> None:
    """Confere o resultado da operação, não a operação em si.

    Roda com a mudança já na sessão (`flush`) e antes do `commit`: se recusar,
    nada é gravado — o `close` da dependência desfaz a transação.
    """
    db.flush()
    garantir_nao_negativas({i for i in ids if i is not None}, db, _erro_422)


def _validar_caixinha(caixinha_id: int | None, conta_id: int, db: Session) -> None:
    """A caixinha precisa existir, estar ativa, e ser da conta do lançamento.

    A regra de "qual tipo aceita caixinha" fica em `validar_coerencia`, no
    schema; aqui só o que exige olhar o banco (ADR-10).
    """
    if caixinha_id is None:
        return

    caixinha = db.get(Caixinha, caixinha_id)
    if caixinha is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Caixinha {caixinha_id} não existe.",
        )
    if caixinha.conta_id != conta_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"A caixinha '{caixinha.nome}' é de outra conta. Uma caixinha "
                "só recebe dinheiro da conta a que pertence."
            ),
        )
    if not caixinha.ativa:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"A caixinha '{caixinha.nome}' está desativada.",
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
        lanc.forma_pagamento,
        erro,
        caixinha_id=lanc.caixinha_id,
        caixinha_destino_id=lanc.caixinha_destino_id,
    )
